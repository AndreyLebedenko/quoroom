/**
 * Проверка DSH-плагина без DeepSeek Harness и без брокера: вместо них —
 * поддельный ctx, поддельные агенты, поддельный CLI agentschat и обычный
 * http-сервер. Главное, что здесь проверяется: две сессии в одном процессе
 * живут под разными именами и не мешают друг другу, /chatlogin и /chatlogout
 * работают как хендлеры команд (а не хуки инструментов), а умершая сессия не
 * оставляет за собой ни занятого слота, ни вечной привязки.
 *
 *     node --test bridge/tests/plugin/dsh-agentschat.test.mjs
 *
 * Домашний каталог, адрес брокера и путь к CLI плагин читает в resolveConfig
 * и в storeDir при каждом использовании, поэтому всё это поднимается здесь
 * до импорта и одно на все проверки.
 */

import assert from "node:assert/strict"
import fs from "node:fs"
import http from "node:http"
import os from "node:os"
import path from "node:path"
import test from "node:test"

const AGENTS = ["terra", "helium"]

// Паузу цикла плагин читает из конфига/окружения. Со штатными тремя секундами
// проверка «привязка без токена не висит вечно» ждала бы минуту.
process.env.AGENTSCHAT_RETRY_MS = "40"

const home = fs.mkdtempSync(path.join(os.tmpdir(), "agentschat-dsh-home-"))
process.env.USERPROFILE = home
process.env.HOME = home
const store = path.join(home, ".agentschat")
fs.mkdirSync(store, { recursive: true })

const cliDir = fs.mkdtempSync(path.join(os.tmpdir(), "agentschat-dsh-cli-"))
fs.writeFileSync(
  path.join(cliDir, "agentschat.cmd"),
  '@echo off\r\nnode "%~dp0fake-agentschat.mjs" %*\r\n',
)
process.env.AGENTSCHAT_BIN = path.join(cliDir, "agentschat.cmd")

function writeToken(agent) {
  fs.writeFileSync(
    path.join(store, `${agent}.json`),
    JSON.stringify({ agent, token: `tok-${agent}` }),
  )
}
AGENTS.forEach(writeToken)

/** Что брокер видел: строки вида "terra/tok-terra". */
let asked = []
/** Кому конверт уже отдан: второй раз тому же имени ничего не приходит. */
let served = new Set()
/** Имена, которым следующий long-poll отвечает 409. */
let wait409 = new Set()
/** Готовый текст конверта на имя; по умолчанию «конверт для <имя>». */
let envelopes = {}

/**
 * Пустой ответ брокера держим открытым, как настоящий long-poll. Если отвечать
 * 204 немедленно, цикл плагина превращается в гонку без единой паузы, и тест
 * упирается в процессор, а не в поведение.
 */
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1")
  if (url.pathname === "/wait") {
    const agent = url.searchParams.get("agent")
    asked.push(`${agent}/${url.searchParams.get("token")}`)
    if (wait409.has(agent)) {
      wait409.delete(agent)
      res.writeHead(409, { "content-type": "text/plain" }).end("session unknown")
      return
    }
    if (served.has(agent)) {
      setTimeout(() => res.writeHead(204).end(), 200)
      return
    }
    served.add(agent)
    res.writeHead(200, { "content-type": "application/json" })
    res.end(JSON.stringify({ rendered: envelopes[agent] ?? `конверт для ${agent}` }))
    return
  }
  res.writeHead(404).end()
})
await new Promise((r) => server.listen(0, "127.0.0.1", r))
process.env.AGENTSCHAT_URL = `http://127.0.0.1:${server.address().port}`

/**
 * Поддельный CLI: login кладёт токен в ~/.agentschat/<имя>.json и печатает
 * строку AGENTSCHAT-RESULT, logout убирает токен. Поведение управляется
 * файлами-контрольками в том же каталоге: refuse-login-<имя> (always/first),
 * refuse-logout-<имя> (код отказа), output-login-<имя>/output-logout-<имя>
 * (готовый вывод). Все попытки записываются в attempts-login/attempts-logout.
 */
fs.writeFileSync(
  path.join(cliDir, "fake-agentschat.mjs"),
  [
    'import fs from "node:fs"',
    'import os from "node:os"',
    'import path from "node:path"',
    "",
    'const store = path.join(os.homedir(), ".agentschat")',
    "const args = process.argv.slice(2)",
    "const command = args[0]",
    "const flag = (name) => {",
    "  const i = args.indexOf(name)",
    "  return i >= 0 && i + 1 < args.length ? args[i + 1] : null",
    "}",
    "const agent = flag(\"--agent\")",
    "const label = flag(\"--label\")",
    "const reconnect = args.includes(\"--reconnect\")",
    "",
    "const control = (name) => {",
    "  try {",
    "    return fs.readFileSync(path.join(store, name), \"utf8\")",
    "  } catch {",
    "    return null",
    "  }",
    "}",
    "",
    "const countAttempts = (file, who) => {",
    "  try {",
    '    return fs.readFileSync(path.join(store, file), "utf8")',
    '      .split("\\n")',
    '      .filter((l) => l.includes(`"agent":"${who}"`)).length',
    "  } catch {",
    "    return 0",
    "  }",
    "}",
    "",
    "const record = (file, entry) => {",
    "  fs.mkdirSync(store, { recursive: true })",
    '  fs.appendFileSync(path.join(store, file), JSON.stringify(entry) + "\\n")',
    "}",
    "",
    "const finish = (text, code) => {",
    "  process.stdout.write(text)",
    "  process.exit(code)",
    "}",
    "",
    "if (command === \"login\") {",
    '  record("attempts-login", { agent, label, reconnect })',
    "  const scripted = control(`output-login-${agent}`)",
    "  if (scripted !== null) {",
    "    finish(scripted.endsWith(\"\\n\") ? scripted : scripted + \"\\n\", scripted.includes('\"ok\":false') ? 1 : 0)",
    "  }",
    "  const refusal = control(`refuse-login-${agent}`)",
    "  if (refusal !== null) {",
    "    const mode = refusal.trim()",
    '    if (mode === "always" || (mode === "first" && countAttempts("attempts-login", agent) === 1)) {',
    "      finish(",
    '        `AGENTSCHAT: слот занят.\\nAGENTSCHAT-RESULT ${JSON.stringify({ command: "login", ok: false, agent, code: "slot_taken", message: "slot taken" })}\\n`,',
    "        1,",
    "      )",
    "    }",
    "  }",
    "  fs.mkdirSync(store, { recursive: true })",
    "  fs.writeFileSync(path.join(store, `${agent}.json`), JSON.stringify({ agent, token: `tok-${agent}` }))",
    "  finish(",
    '    `AGENTSCHAT: сессия ${agent} подключена к комнате !x:y.\\nAGENTSCHAT-RESULT ${JSON.stringify({ command: "login", ok: true, agent, mode: "plugin", reconnected: reconnect })}\\n`,',
    "    0,",
    "  )",
    "}",
    "",
    "if (command === \"logout\") {",
    '  record("attempts-logout", { agent })',
    "  const scripted = control(`output-logout-${agent}`)",
    "  if (scripted !== null) {",
    "    finish(scripted.endsWith(\"\\n\") ? scripted : scripted + \"\\n\", scripted.includes('\"ok\":false') ? 1 : 0)",
    "  }",
    "  const refusal = control(`refuse-logout-${agent}`)",
    "  if (refusal !== null) {",
    "    finish(",
    '      `AGENTSCHAT: сессия не найдена.\\nAGENTSCHAT-RESULT ${JSON.stringify({ command: "logout", ok: false, agent, code: refusal.trim(), message: "not logged in" })}\\n`,',
    "      1,",
    "    )",
    "  }",
    "  fs.rmSync(path.join(store, `${agent}.json`), { force: true })",
    "  finish(",
    '    `AGENTSCHAT: сессия ${agent} отключена.\\nAGENTSCHAT-RESULT ${JSON.stringify({ command: "logout", ok: true, agent })}\\n`,',
    "    0,",
    "  )",
    "}",
    "",
    "finish(`fake agentschat: unknown command ${command}\\n`, 2)",
    "",
  ].join("\n"),
)

const { apply, resolveConfig, inject } = await import(
  "../../sessionchat/kit/common/dsh/plugin/src/index.js"
)

/** Состояние плагина живёт в globalThis, поэтому чистим его между проверками. */
function fresh() {
  delete globalThis.__dshAgentschat
  asked = []
  served = new Set()
  wait409 = new Set()
  envelopes = {}
  const files = [
    "attempts-login",
    "attempts-logout",
    "dsh-plugin.log",
    ...AGENTS.flatMap((a) => [
      `${a}.json`,
      `refuse-login-${a}`,
      `refuse-logout-${a}`,
      `output-login-${a}`,
      `output-logout-${a}`,
    ]),
  ]
  for (const name of files) {
    fs.rmSync(path.join(store, name), { force: true, recursive: true })
  }
  AGENTS.forEach(writeToken)
}

/** Поддельный ctx DSH: команды регистрируются, события слушаются. */
function makeCtx() {
  const registered = []
  const listeners = new Map()
  const ctx = {
    commands: {
      register: (definition) => {
        registered.push(definition)
        return () => {
          const i = registered.indexOf(definition)
          if (i >= 0) registered.splice(i, 1)
        }
      },
    },
    on: (name, listener) => {
      const list = listeners.get(name) ?? []
      list.push(listener)
      listeners.set(name, list)
      return () => {
        const l = listeners.get(name)
        const i = l.indexOf(listener)
        if (i >= 0) l.splice(i, 1)
      }
    },
    logger: { info: () => {}, warn: () => {}, error: () => {} },
  }
  return { ctx, registered, listeners }
}

/** Поддельный агент DSH: followup кладёт сообщение в delivered. */
function makeAgent(id, delivered) {
  return {
    id,
    followup: (message) => delivered.push(message),
  }
}

function invoke(registered, name, rawInput, agent) {
  const definition = registered.find((d) => d.name === name)
  assert.ok(definition, `command ${name} is registered`)
  return definition.handler({
    commandId: `cmd-${name}`,
    agent,
    rawInput,
    attachments: [],
    signal: new AbortController().signal,
  })
}

async function waitFor(predicate, timeoutMs = 5000) {
  const start = Date.now()
  while (!predicate()) {
    if (Date.now() - start > timeoutMs) throw new Error("timeout waiting")
    await new Promise((r) => setTimeout(r, 25))
  }
}

function readAttempts(file) {
  try {
    return fs
      .readFileSync(path.join(store, file), "utf8")
      .split("\n")
      .filter((l) => l !== "")
      .map((l) => JSON.parse(l))
  } catch {
    return []
  }
}

const logFile = path.join(store, "dsh-plugin.log")
const readLog = () => (fs.existsSync(logFile) ? fs.readFileSync(logFile, "utf8") : "")
const state = () => globalThis.__dshAgentschat

test("the plugin registers the chatlogin and chatlogout commands", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const dispose = apply(ctx, {})
  assert.deepEqual(registered.map((d) => d.name), ["chatlogin", "chatlogout"])
  dispose()
  assert.deepEqual(registered, [])
})

// Настоящий cordis отдаёт плагину только сервисы, объявленные в inject,
// и на любой другой свойство отвечает ошибкой "cannot get property without
// inject". Поддельный ctx воспроизводит этот шлюз, чтобы проверка шла по
// собственному объявлению плагина, а не по щедрости фейка.
test("apply works against a ctx gated by the plugin's own inject declaration", async () => {
  fresh()
  const declared = Array.isArray(inject) ? inject : []
  const { ctx, registered } = makeCtx()
  const gated = new Proxy({}, {
    get: (_target, prop) => {
      if (prop === "on") return ctx.on
      if (!declared.includes(prop)) {
        throw new Error(`cannot get property "${String(prop)}" without inject`)
      }
      return ctx[prop]
    },
  })
  const dispose = apply(gated, {})
  assert.deepEqual(registered.map((d) => d.name), ["chatlogin", "chatlogout"])
  dispose()
  assert.deepEqual(registered, [])
})

test("a successful login binds the calling agent and delivers the broker envelope", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const delivered = []
  const agent = makeAgent("agent-terra", delivered)
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra my label", agent)
    assert.equal(result.kind, "success")
    assert.equal(state().bindings.get("terra")?.agent, agent)

    await waitFor(() => delivered.length > 0)
    assert.equal(delivered[0].role, "user")
    assert.equal(delivered[0].content[0].type, "text")
    assert.equal(delivered[0].content[0].text, "конверт для terra")
    assert.deepEqual(delivered[0].source, { kind: "plugin", plugin: "agentschat" })
    assert.equal(typeof delivered[0].id, "string")
    assert.ok(asked.includes("terra/tok-terra"))
  } finally {
    dispose()
  }
})

test("two sessions under different names each receive their own envelope", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const delivered = []
  const terra = makeAgent("agent-terra", delivered)
  const helium = makeAgent("agent-helium", delivered)
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", terra)).kind, "success")
    assert.equal((await invoke(registered, "chatlogin", "helium", helium)).kind, "success")
    await waitFor(() => delivered.length === 2)
    assert.deepEqual(
      delivered.map((m) => m.content[0].text).sort(),
      ["конверт для helium", "конверт для terra"],
    )
    assert.ok(asked.includes("terra/tok-terra") && asked.includes("helium/tok-helium"))

    const result = await invoke(registered, "chatlogout", "terra", terra)
    assert.equal(result.kind, "success")
    assert.equal(state().bindings.has("terra"), false)
    assert.equal(state().bindings.has("helium"), true)
  } finally {
    dispose()
  }
})

test("a refused login changes nothing and reports the refusal", async () => {
  fresh()
  fs.writeFileSync(path.join(store, "refuse-login-terra"), "always")
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "error")
    assert.match(result.text, /slot_taken/)
    assert.equal(state().bindings.has("terra"), false)
  } finally {
    dispose()
  }
})

test("a slot_taken refusal with a stored token retries the login with --reconnect", async () => {
  fresh()
  fs.writeFileSync(path.join(store, "refuse-login-terra"), "first")
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "success")
    assert.equal(state().bindings.get("terra")?.agent, agent)
    const attempts = readAttempts("attempts-login")
    assert.equal(attempts.length, 2)
    assert.equal(attempts[0].reconnect, false)
    assert.equal(attempts[1].reconnect, true)
  } finally {
    dispose()
  }
})

test("a logout command unbinds the agent and the CLI logout runs", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", agent)).kind, "success")
    const result = await invoke(registered, "chatlogout", "terra", agent)
    assert.equal(result.kind, "success")
    assert.equal(state().bindings.has("terra"), false)
    assert.equal(fs.existsSync(path.join(store, "terra.json")), false)
    assert.ok(readAttempts("attempts-logout").some((a) => a.agent === "terra"))
  } finally {
    dispose()
  }
})

test("a logout without a name unbinds the session of the calling agent", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const terra = makeAgent("agent-terra", [])
  const helium = makeAgent("agent-helium", [])
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", terra)).kind, "success")
    assert.equal((await invoke(registered, "chatlogin", "helium", helium)).kind, "success")
    const result = await invoke(registered, "chatlogout", "", terra)
    assert.equal(result.kind, "success")
    assert.equal(state().bindings.has("terra"), false)
    assert.equal(state().bindings.has("helium"), true)
  } finally {
    dispose()
  }
})

test("a refused logout leaves the binding in place", async () => {
  fresh()
  fs.writeFileSync(path.join(store, "refuse-logout-terra"), "not_logged_in")
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", agent)).kind, "success")
    const result = await invoke(registered, "chatlogout", "terra", agent)
    assert.equal(result.kind, "error")
    assert.match(result.text, /not_logged_in/)
    assert.equal(state().bindings.get("terra")?.agent, agent)
  } finally {
    dispose()
  }
})

test("a disposed agent releases exactly its own slot", async () => {
  fresh()
  const { ctx, registered, listeners } = makeCtx()
  const terra = makeAgent("agent-terra", [])
  const helium = makeAgent("agent-helium", [])
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", terra)).kind, "success")
    assert.equal((await invoke(registered, "chatlogin", "helium", helium)).kind, "success")

    listeners.get("agent/disposed").forEach((l) => l({ agent: terra }))
    await waitFor(() => !fs.existsSync(path.join(store, "terra.json")))

    assert.equal(state().bindings.has("terra"), false)
    assert.equal(state().bindings.has("helium"), true)
    assert.equal(fs.existsSync(path.join(store, "terra.json")), false)
    assert.equal(fs.existsSync(path.join(store, "helium.json")), true)
  } finally {
    dispose()
  }
})

test("a binding without a token does not hang forever", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", agent)).kind, "success")
    fs.rmSync(path.join(store, "terra.json"))
    await new Promise((r) => setTimeout(r, 100))
    const pollsBefore = asked.filter((a) => a.startsWith("terra/")).length

    // Порог — двадцать попыток; паузу задаёт AGENTSCHAT_RETRY_MS, иначе ждать
    // пришлось бы минуту.
    await new Promise((r) => setTimeout(r, 40 * 30))
    assert.equal(state().bindings.has("terra"), false, "привязка снята")
    assert.equal(
      asked.filter((a) => a.startsWith("terra/")).length,
      pollsBefore,
      "брокера не дёргали без токена",
    )
  } finally {
    dispose()
  }
})

test("the last instance to dispose stops the loops and releases the remaining slots", async () => {
  fresh()
  const one = makeCtx()
  const two = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const disposeOne = apply(one.ctx, {})
  const disposeTwo = apply(two.ctx, {})
  try {
    assert.equal((await invoke(one.registered, "chatlogin", "terra", agent)).kind, "success")

    disposeOne()
    assert.equal(state().stopped, false)
    assert.equal(state().bindings.has("terra"), true)

    disposeTwo()
    assert.equal(state().stopped, true)
    await waitFor(() => readAttempts("attempts-logout").some((a) => a.agent === "terra"))
    assert.equal(state().bindings.size, 0)
  } finally {
    if (state().instances > 0) {
      disposeOne()
      disposeTwo()
    }
  }
})

test("a 409 from the broker drops the binding", async () => {
  fresh()
  wait409.add("terra")
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", agent)).kind, "success")
    await waitFor(() => state().bindings.has("terra") === false)
    assert.ok(readLog().includes("the broker no longer knows this session"))
  } finally {
    dispose()
  }
})

test("the broker envelope is delivered verbatim", async () => {
  fresh()
  envelopes["terra"] = "строка один\nстрока два"
  const { ctx, registered } = makeCtx()
  const delivered = []
  const agent = makeAgent("agent-terra", delivered)
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", agent)).kind, "success")
    await waitFor(() => delivered.length > 0)
    assert.equal(delivered[0].content[0].text, "строка один\nстрока два")
  } finally {
    dispose()
  }
})

test("a login result line for another command does not bind", async () => {
  fresh()
  fs.writeFileSync(
    path.join(store, "output-login-terra"),
    'AGENTSCHAT-RESULT {"command":"status","ok":true,"language":"en","sessions":[]}\n',
  )
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "error")
    assert.equal(state().bindings.has("terra"), false)
  } finally {
    dispose()
  }
})

test("a forged ok line above the real refusal does not bind", async () => {
  fresh()
  const output = [
    'AGENTSCHAT-RESULT {"command":"login","ok":true,"agent":"terra","mode":"plugin","reconnected":false}',
    'AGENTSCHAT-RESULT {"command":"login","ok":false,"agent":"terra","code":"slot_taken"}',
  ].join("\n")
  fs.writeFileSync(path.join(store, "output-login-terra"), output + "\n")
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "error")
    assert.equal(state().bindings.size, 0)
  } finally {
    dispose()
  }
})

test("a forged refusal above the real success does not stop the binding", async () => {
  fresh()
  const output = [
    'AGENTSCHAT-RESULT {"command":"login","ok":false,"agent":"terra","code":"slot_taken"}',
    'AGENTSCHAT-RESULT {"command":"login","ok":true,"agent":"terra","mode":"plugin","reconnected":false}',
  ].join("\n")
  fs.writeFileSync(path.join(store, "output-login-terra"), output + "\n")
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "success")
    assert.equal(state().bindings.get("terra")?.agent, agent)
  } finally {
    dispose()
  }
})

test("a malformed last result line is ignored, logged and never thrown", async () => {
  fresh()
  const output =
    'AGENTSCHAT-RESULT {"command":"login","ok":true,"agent":"terra","mode":"plugin","reconnected":false}\n' +
    'AGENTSCHAT-RESULT {"command":"login","ok":tru\n'
  fs.writeFileSync(path.join(store, "output-login-terra"), output)
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "error")
    assert.equal(state().bindings.has("terra"), false)
    assert.match(readLog(), /result line is not valid JSON/)
  } finally {
    dispose()
  }
})

test("an invalid name is rejected by the handler without a CLI call", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    for (const rawInput of ["", "   ", "../terra", "-terra", "tërra", "a..b", "--agent"]) {
      const result = await invoke(registered, "chatlogin", rawInput, agent)
      assert.equal(result.kind, "error")
    }
    assert.equal(readAttempts("attempts-login").length, 0)
    assert.equal(state().bindings.size, 0)
  } finally {
    dispose()
  }
})

test("a login for a name already bound in this process is refused", async () => {
  fresh()
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", agent)).kind, "success")
    const attemptsBefore = readAttempts("attempts-login").length
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "error")
    assert.match(result.text, /already connected/)
    assert.equal(readAttempts("attempts-login").length, attemptsBefore)
  } finally {
    dispose()
  }
})

test("the plugin log is English whatever the CLI printed", async () => {
  fresh()
  const { ctx, registered, listeners } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  const CYRILLIC = /[Ѐ-ӿ]/
  try {
    assert.equal((await invoke(registered, "chatlogin", "terra", agent)).kind, "success")
    await new Promise((r) => setTimeout(r, 300))
    assert.equal((await invoke(registered, "chatlogout", "terra", agent)).kind, "success")
    listeners.get("agent/disposed").forEach((l) => l({ agent: agent }))
    await new Promise((r) => setTimeout(r, 500))
    const log = readLog()
    assert.ok(log.length > 0)
    assert.doesNotMatch(log, CYRILLIC)
  } finally {
    dispose()
  }
})

test("a broken log file never breaks the login", async () => {
  fresh()
  fs.mkdirSync(logFile, { recursive: true })
  const { ctx, registered } = makeCtx()
  const agent = makeAgent("agent-terra", [])
  const dispose = apply(ctx, {})
  try {
    const result = await invoke(registered, "chatlogin", "terra", agent)
    assert.equal(result.kind, "success")
    assert.equal(state().bindings.get("terra")?.agent, agent)
  } finally {
    dispose()
  }
})

function withEnv(cleared, fn) {
  const saved = {}
  for (const name of cleared) {
    saved[name] = process.env[name]
    delete process.env[name]
  }
  try {
    fn()
  } finally {
    for (const name of cleared) {
      if (saved[name] === undefined) delete process.env[name]
      else process.env[name] = saved[name]
    }
  }
}

test("resolveConfig rejects a non-URL brokerUrl", () => {
  withEnv(["AGENTSCHAT_URL"], () => {
    assert.throws(() => resolveConfig({ brokerUrl: "not a url" }), TypeError)
  })
})

test("resolveConfig rejects a non-http protocol", () => {
  withEnv(["AGENTSCHAT_URL"], () => {
    assert.throws(() => resolveConfig({ brokerUrl: "ftp://x" }), TypeError)
  })
})

test("resolveConfig rejects a non-positive retryMs", () => {
  withEnv(["AGENTSCHAT_RETRY_MS"], () => {
    assert.throws(() => resolveConfig({ retryMs: 0 }), TypeError)
    assert.throws(() => resolveConfig({ retryMs: "many" }), TypeError)
  })
})

test("resolveConfig reads env overrides and defaults", () => {
  process.env.AGENTSCHAT_BIN = "custom-cli"
  try {
    const resolved = resolveConfig({})
    assert.equal(resolved.cli, "custom-cli")
    assert.equal(resolved.retryMs, 40)
    assert.equal(resolved.tokenlessLimit, 20)
    assert.equal(resolved.loginTimeoutMs, 30000)
    assert.equal(resolved.logoutTimeoutMs, 15000)
    assert.equal(resolved.waitTimeoutMs, 70000)
    assert.ok(resolved.brokerUrl.startsWith("http://127.0.0.1:"))
  } finally {
    delete process.env.AGENTSCHAT_BIN
  }
})

function withoutComments(source) {
  let i = 0
  const quoted = (quote) => {
    let text = source[i++]
    while (i < source.length && source[i] !== quote) {
      if (source[i] === "\\") text += source[i++]
      text += source[i++]
    }
    return text + source[i++]
  }
  const regex = () => {
    let text = source[i++]
    let inClass = false
    while (i < source.length && (inClass || source[i] !== "/")) {
      if (source[i] === "\\") text += source[i++]
      else if (source[i] === "[") inClass = true
      else if (source[i] === "]") inClass = false
      text += source[i++]
    }
    return text + source[i++]
  }
  const template = () => {
    let text = source[i++]
    while (i < source.length && source[i] !== "`") {
      if (source[i] === "\\") text += source[i++]
      else if (source[i] === "$" && source[i + 1] === "{") {
        text += source.slice(i, i + 2)
        i += 2
        text += code(true) + "}"
        continue
      }
      text += source[i++]
    }
    return text + source[i++]
  }
  const code = (insideTemplate) => {
    let out = ""
    let depth = 0
    let previous = ";"
    while (i < source.length) {
      const c = source[i]
      const next = source[i + 1]
      if (c === "/" && next === "/") {
        while (i < source.length && source[i] !== "\n") i++
        continue
      }
      if (c === "/" && next === "*") {
        i = source.indexOf("*/", i + 2) + 2
        continue
      }
      if (insideTemplate && c === "}" && depth === 0) {
        i++
        return out
      }
      if (c === "{") depth++
      if (c === "}") depth--
      if (c === '"' || c === "'") out += quoted(c)
      else if (c === "`") out += template()
      else if (c === "/" && "(,=:[!&|?{};".includes(previous)) out += regex()
      else out += source[i++]
      if (!/\s/.test(c)) previous = c
    }
    return out
  }
  return code(false)
}

test("the comment stripper keeps strings, templates and regular expressions", () => {
  const kept = withoutComments(
    [
      "// comment жжж",
      "const a = 'http://x' // tail жжж",
      "/* block жжж */ const b = `t ${ \"ж\" /* inner жжж */ } end`",
      "const c = /[/']ж/.test(a)",
    ].join("\n"),
  )
  assert.equal(kept.match(/[Ѐ-ӿ]/g).length, 2)
  assert.ok(kept.includes("http://x"))
  assert.ok(!kept.includes("comment"))
  assert.ok(!kept.includes("block"))
  assert.ok(!kept.includes("inner"))
  assert.ok(!kept.includes("tail"))
})

test("the plugin source has no Cyrillic outside comments", () => {
  const source = fs.readFileSync(
    new URL("../../sessionchat/kit/common/dsh/plugin/src/index.js", import.meta.url),
    "utf8",
  )
  const offending = withoutComments(source)
    .split("\n")
    .filter((line) => /[Ѐ-ӿ]/.test(line))
  assert.deepEqual(offending, [])
})

test.after(() => server.close())
