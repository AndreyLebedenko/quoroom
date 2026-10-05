/**
 * Проверка плагина без OpenCode и без брокера: вместо них — поддельный клиент
 * и обычный http-сервер. Главное, что здесь проверяется, — две сессии в одном
 * процессе живут под разными именами и не мешают друг другу, а исчезнувшая
 * сессия не оставляет за собой ни занятого слота, ни вечной привязки.
 *
 *     node --test bridge/tests/plugin/agentschat.test.mjs
 *
 * Домашний каталог и адрес брокера плагин читает ОДИН раз, при загрузке
 * модуля. Поэтому и то и другое поднимается здесь до импорта и одно на все
 * проверки: подменять их между тестами бесполезно — плагин этого не заметит.
 */

import assert from "node:assert/strict"
import fs from "node:fs"
import http from "node:http"
import os from "node:os"
import path from "node:path"
import test from "node:test"

const AGENTS = ["terra", "helium"]

// Паузу цикла плагин тоже читает при загрузке. Со штатными тремя секундами
// проверка «привязка без токена не висит вечно» ждала бы минуту.
process.env.AGENTSCHAT_RETRY_MS = "40"

const home = fs.mkdtempSync(path.join(os.tmpdir(), "agentschat-home-"))
process.env.USERPROFILE = home
process.env.HOME = home
const store = path.join(home, ".agentschat")
fs.mkdirSync(store, { recursive: true })

function writeToken(agent) {
  fs.writeFileSync(
    path.join(store, `${agent}.json`),
    JSON.stringify({ agent, token: `tok-${agent}` }),
  )
}
AGENTS.forEach(writeToken)

/** Что брокер видел: строки вида "terra/tok-terra" и "logout/terra". */
let asked = []
/** Кому конверт уже отдан: второй раз тому же имени ничего не приходит. */
let served = new Set()

/**
 * Пустой ответ брокер держит открытым, как настоящий long-poll. Если отвечать
 * 204 немедленно, цикл плагина превращается в гонку без единой паузы, и тест
 * упирается в процессор, а не в поведение — проверено дорогой ценой.
 */
const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1")
  if (url.pathname === "/logout") {
    let body = ""
    req.on("data", (chunk) => (body += chunk))
    req.on("end", () => {
      asked.push(`logout/${JSON.parse(body).agent}`)
      res.writeHead(200, { "content-type": "application/json" }).end("{}")
    })
    return
  }
  const agent = url.searchParams.get("agent")
  asked.push(`${agent}/${url.searchParams.get("token")}`)
  if (served.has(agent)) {
    setTimeout(() => res.writeHead(204).end(), 200)
    return
  }
  served.add(agent)
  res.writeHead(200, { "content-type": "application/json" })
  res.end(JSON.stringify({ rendered: `конверт для ${agent}` }))
})
await new Promise((r) => server.listen(0, "127.0.0.1", r))
process.env.AGENTSCHAT_URL = `http://127.0.0.1:${server.address().port}`

const { AgentsChat } = await import(
  "../../sessionchat/kit/opencode/plugins/agentschat.js"
)

/** Состояние плагина живёт в globalThis, поэтому чистим его между проверками. */
function fresh() {
  delete globalThis.__agentschat
  asked = []
  served = new Set()
  AGENTS.forEach(writeToken)
}

const quiet = { session: { promptAsync: async () => {} } }

const resultLine = (fields) => `AGENTSCHAT-RESULT ${JSON.stringify(fields)}`

const loginOk = (agent) =>
  resultLine({ command: "login", ok: true, agent, mode: "plugin", reconnected: false })

const logoutOk = (agent) => resultLine({ command: "logout", ok: true, agent })

async function runCommand(hooks, callID, sessionID, command, output) {
  await hooks["tool.execute.before"]({ callID, sessionID }, { args: { command } })
  await hooks["tool.execute.after"]({ callID, sessionID }, { output })
}

async function login(hooks, callID, sessionID, agent, launcher = "agentschat") {
  await runCommand(
    hooks,
    callID,
    sessionID,
    `${launcher} login --agent ${agent} --label "тест"`,
    `AGENTSCHAT: сессия ${agent} подключена к комнате !x:y.\n${loginOk(agent)}\n`,
  )
}

test("две сессии под разными именами получают каждая своё", async () => {
  fresh()
  const delivered = []
  const client = {
    session: {
      promptAsync: async ({ path: p, body }) =>
        delivered.push(`${p.id} <- ${body.parts[0].text}`),
    },
  }
  // Два экземпляра плагина — так выглядят две сессии в одном процессе OpenCode.
  const one = await AgentsChat({ client })
  const two = await AgentsChat({ client })

  await login(one, "c1", "ses-terra", "terra")
  await login(two, "c2", "ses-helium", "helium")
  await new Promise((r) => setTimeout(r, 400))

  assert.deepEqual(delivered.sort(), [
    "ses-helium <- конверт для helium",
    "ses-terra <- конверт для terra",
  ])
  // Каждое имя опрашивает брокера своим токеном, чужим не пользуется.
  assert.ok(asked.includes("terra/tok-terra") && asked.includes("helium/tok-helium"))

  const state = globalThis.__agentschat

  // logout одной сессии не глушит соседнюю.
  await one["tool.execute.before"](
    { callID: "c3", sessionID: "ses-terra" },
    { args: { command: "agentschat logout --agent terra" } },
  )
  await one["tool.execute.after"](
    { callID: "c3", sessionID: "ses-terra" },
    { output: `AGENTSCHAT: сессия terra отключена.\n${logoutOk("terra")}\n` },
  )
  assert.equal(state.bindings.has("terra"), false)
  assert.equal(state.bindings.has("helium"), true)

  // Циклы гасит только последний ушедший экземпляр плагина.
  await one.dispose()
  assert.equal(state.stopped, false)
  await two.dispose()
  assert.equal(state.stopped, true)
})

test("закрытая сессия освобождает свой слот", async () => {
  fresh()
  const hooks = await AgentsChat({ client: quiet })
  await login(hooks, "c1", "ses-terra", "terra")
  await login(hooks, "c2", "ses-helium", "helium")

  await hooks.event({
    event: { type: "session.deleted", properties: { info: { id: "ses-terra" } } },
  })

  const state = globalThis.__agentschat
  assert.ok(asked.includes("logout/terra"), "брокеру сказано про закрытую сессию")
  assert.equal(state.bindings.has("terra"), false)
  // Соседняя сессия того же процесса продолжает жить.
  assert.equal(state.bindings.has("helium"), true)
  assert.ok(!asked.includes("logout/helium"))

  // Последний экземпляр уходит — освобождает и остальные слоты.
  await hooks.dispose()
  assert.ok(asked.includes("logout/helium"))
})

test("привязка без токена не висит вечно", async () => {
  // Так выглядит снятая снаружи сессия: файла с токеном больше нет. Раньше
  // цикл молча крутился на нём вхолостую, изображая живую привязку.
  fresh()
  fs.rmSync(path.join(store, "terra.json"))
  const hooks = await AgentsChat({ client: quiet })
  await login(hooks, "c1", "ses-terra", "terra")

  const state = globalThis.__agentschat
  assert.equal(state.bindings.has("terra"), true)
  // Порог — двадцать попыток; паузу задаёт AGENTSCHAT_RETRY_MS, иначе ждать
  // пришлось бы минуту.
  await new Promise((r) => setTimeout(r, 40 * 25))
  assert.equal(state.bindings.has("terra"), false, "привязка снята")
  assert.ok(!asked.some((a) => a.startsWith("terra/")), "брокера не дёргали без токена")

  await hooks.dispose()
})

test("старый вызов по пути bridge\\agentschat.cmd тоже привязывает сессию", async () => {
  fresh()
  const hooks = await AgentsChat({ client: quiet })
  await login(hooks, "c1", "ses-terra", "terra", "bridge\\agentschat.cmd")

  assert.equal(globalThis.__agentschat.bindings.get("terra")?.sessionID, "ses-terra")

  await hooks.dispose()
})

const logFile = path.join(store, "opencode-plugin.log")
const readLog = () => (fs.existsSync(logFile) ? fs.readFileSync(logFile, "utf8") : "")
const bindings = () => globalThis.__agentschat.bindings
const CYRILLIC = /[Ѐ-ӿ]/

async function withPlugin(body) {
  fresh()
  fs.rmSync(logFile, { force: true })
  const hooks = await AgentsChat({ client: quiet })
  try {
    await body(hooks)
  } finally {
    await hooks.dispose()
  }
}

const loginCommand = (agent) => `agentschat login --agent ${agent}`
const logoutCommand = (agent) => `agentschat logout --agent ${agent}`

test("an English login result line binds the session of the call to the agent", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `AGENTSCHAT: session terra is connected to room !x:y.\n${loginOk("terra")}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("the old Russian sentences alone no longer bind a session", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      "AGENTSCHAT: сессия terra подключена к комнате !x:y.\n",
    )
    assert.equal(bindings().has("terra"), false)
    assert.match(readLog(), /login: no result line in the command output/)
  })
})

test("the old Russian logout sentence alone no longer unbinds a session", async () => {
  await withPlugin(async (hooks) => {
    await login(hooks, "c1", "ses-terra", "terra")
    await runCommand(
      hooks,
      "c2",
      "ses-terra",
      logoutCommand("terra"),
      "AGENTSCHAT: сессия terra отключена.\n",
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a refused login changes nothing", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `AGENTSCHAT: slot taken.\n${resultLine({ command: "login", ok: false, agent: "terra", code: "slot_taken" })}\n`,
    )
    assert.equal(bindings().has("terra"), false)
    assert.match(readLog(), /login refused for session ses-terra, code slot_taken/)
  })
})

test("a refused login does not disturb an existing binding of the same agent", async () => {
  await withPlugin(async (hooks) => {
    await login(hooks, "c1", "ses-terra", "terra")
    await runCommand(
      hooks,
      "c2",
      "ses-other",
      loginCommand("terra"),
      `${resultLine({ command: "login", ok: false, agent: "terra", code: "slot_taken" })}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a logout result line unbinds the agent", async () => {
  await withPlugin(async (hooks) => {
    await login(hooks, "c1", "ses-terra", "terra")
    await login(hooks, "c2", "ses-helium", "helium")
    await runCommand(
      hooks,
      "c3",
      "ses-terra",
      logoutCommand("terra"),
      `AGENTSCHAT: session terra is disconnected.\n${logoutOk("terra")}\n`,
    )
    assert.equal(bindings().has("terra"), false)
    assert.equal(bindings().has("helium"), true)
  })
})

test("a refused logout leaves the binding in place", async () => {
  await withPlugin(async (hooks) => {
    await login(hooks, "c1", "ses-terra", "terra")
    await runCommand(
      hooks,
      "c2",
      "ses-terra",
      logoutCommand("terra"),
      `${resultLine({ command: "logout", ok: false, agent: "terra", code: "not_logged_in" })}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a result line among unrelated lines is found, CRLF line ends included", async () => {
  await withPlugin(async (hooks) => {
    const output = [
      "some banner",
      "{\"command\":\"login\",\"ok\":false}",
      "AGENTSCHAT: session terra is connected.",
      loginOk("terra"),
      "",
    ].join("\r\n")
    await runCommand(hooks, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a result line has to start its line to count", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `echo: ${loginOk("terra")}\n`,
    )
    assert.equal(bindings().has("terra"), false)
  })
})

test("a forged ok line above the real refusal does not bind", async () => {
  await withPlugin(async (hooks) => {
    const output = [
      `AGENTSCHAT: slot taken by label ${loginOk("helium")}`,
      loginOk("helium"),
      resultLine({ command: "login", ok: false, agent: "terra", code: "slot_taken" }),
    ].join("\n")
    await runCommand(hooks, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().size, 0)
  })
})

test("a forged refusal above the real success does not stop the binding", async () => {
  await withPlugin(async (hooks) => {
    const output = [
      resultLine({ command: "login", ok: false, agent: "terra", code: "slot_taken" }),
      loginOk("terra"),
    ].join("\n")
    await runCommand(hooks, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a malformed last result line is ignored, logged and never thrown", async () => {
  await withPlugin(async (hooks) => {
    const output = `${loginOk("terra")}\nAGENTSCHAT-RESULT {"command":"login","ok":tru\n`
    await runCommand(hooks, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().has("terra"), false)
    assert.match(readLog(), /login: result line is not valid JSON/)
  })
})

test("a result line that is not a JSON object is ignored", async () => {
  await withPlugin(async (hooks) => {
    for (const [index, body] of ["null", "[1]", "\"text\"", "7"].entries()) {
      await runCommand(
        hooks,
        `c${index}`,
        "ses-terra",
        loginCommand("terra"),
        `AGENTSCHAT-RESULT ${body}\n`,
      )
    }
    assert.equal(bindings().size, 0)
  })
})

test("an ok line for another command does not bind or unbind", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `${resultLine({ command: "status", ok: true, language: "en", sessions: [] })}\n`,
    )
    assert.equal(bindings().has("terra"), false)

    await login(hooks, "c2", "ses-terra", "terra")
    await runCommand(
      hooks,
      "c3",
      "ses-terra",
      logoutCommand("terra"),
      `${loginOk("terra")}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a line without a usable ok changes nothing", async () => {
  await withPlugin(async (hooks) => {
    for (const [index, fields] of [
      { command: "login", agent: "terra" },
      { command: "login", ok: "true", agent: "terra" },
      { command: "login", ok: 1, agent: "terra" },
    ].entries()) {
      await runCommand(
        hooks,
        `c${index}`,
        "ses-terra",
        loginCommand("terra"),
        `${resultLine(fields)}\n`,
      )
    }
    assert.equal(bindings().size, 0)
  })
})

test("an agent that is empty, not a string or not a valid name is not bound", async () => {
  await withPlugin(async (hooks) => {
    const agents = ["", " ", 7, null, ["terra"], "-terra", "../terra", "ter ra", "tërra"]
    for (const [index, agent] of agents.entries()) {
      await runCommand(
        hooks,
        `c${index}`,
        "ses-terra",
        loginCommand("terra"),
        `${loginOk(agent)}\n`,
      )
    }
    await runCommand(
      hooks,
      "c-missing",
      "ses-terra",
      loginCommand("terra"),
      `${resultLine({ command: "login", ok: true })}\n`,
    )
    assert.equal(bindings().size, 0)
    assert.match(readLog(), /login: result line names no valid agent/)
  })
})

test("an invalid agent in a logout line does not unbind anyone", async () => {
  await withPlugin(async (hooks) => {
    await login(hooks, "c1", "ses-terra", "terra")
    await runCommand(
      hooks,
      "c2",
      "ses-terra",
      logoutCommand("terra"),
      `${logoutOk("")}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("the agent of the result line decides, as the CLI reported it", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `${loginOk("terra-2")}\n`,
    )
    assert.equal(bindings().has("terra"), false)
    assert.equal(bindings().get("terra-2")?.sessionID, "ses-terra")
  })
})

test("a code in a refusal that is not a plain code is not copied into the log", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `${resultLine({ command: "login", ok: false, code: "bad code\nwith lines" })}\n`,
    )
    assert.match(readLog(), /login refused for session ses-terra, code unknown/)
  })
})

test("a call that is not a chat command is not read at all", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(hooks, "c1", "ses-terra", "ls -la", `${loginOk("terra")}\n`)
    assert.equal(bindings().size, 0)
  })
})

test("delivery still reaches a session bound by a result line", async () => {
  fresh()
  const delivered = []
  const client = {
    session: {
      promptAsync: async ({ path: p, body }) =>
        delivered.push(`${p.id} <- ${body.parts[0].text}`),
    },
  }
  const hooks = await AgentsChat({ client })
  await runCommand(hooks, "c1", "ses-terra", loginCommand("terra"), `${loginOk("terra")}\n`)
  await new Promise((r) => setTimeout(r, 300))
  assert.deepEqual(delivered, ["ses-terra <- конверт для terra"])
  await hooks.dispose()
})

test("the plugin log is English whatever the CLI printed", async () => {
  await withPlugin(async (hooks) => {
    await runCommand(
      hooks,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      "AGENTSCHAT: сессия terra подключена к комнате !x:y.\n",
    )
    await login(hooks, "c2", "ses-terra", "terra")
    await new Promise((r) => setTimeout(r, 300))
    await runCommand(
      hooks,
      "c3",
      "ses-terra",
      logoutCommand("terra"),
      `${logoutOk("terra")}\n`,
    )
    await hooks.event({
      event: { type: "session.deleted", properties: { info: { id: "ses-terra" } } },
    })
    const log = readLog()
    assert.ok(log.length > 0)
    assert.doesNotMatch(log, CYRILLIC)
  })
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
    new URL("../../sessionchat/kit/opencode/plugins/agentschat.js", import.meta.url),
    "utf8",
  )
  const offending = withoutComments(source)
    .split("\n")
    .filter((line) => CYRILLIC.test(line))
  assert.deepEqual(offending, [])
})

test.after(() => server.close())
