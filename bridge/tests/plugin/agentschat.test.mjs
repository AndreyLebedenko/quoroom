/**
 * Проверка плагина без OpenCode и без брокера: вместо них — поддельный
 * контекст V2 (хуки инструментов, хук промпта, поток событий, session.prompt)
 * и обычный http-сервер. Главное, что здесь проверяется, — две сессии в одном
 * процессе живут под разными именами и не мешают друг другу, а исчезнувшая
 * сессия не оставляет за собой ни занятого слота, ни вечной привязки.
 *
 *     node --test bridge/tests/plugin/agentschat.test.mjs
 *
 * Домашний каталог и адрес брокера плагин читает ОДИН раз, при загрузке
 * модуля. Поэтому и то и другое поднимается здесь до импорта и одно на все
 * проверки: подменять их между тестами бесполезно — плагин этого не заметит.
 *
 * OpenCode 2.0 исполняет плагин, только если тот экспортирует default
 * definition с id и setup. Тесты вызывают setup с поддельным контекстом и
 * получают обратно его функцию выхода.
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

const { default: plugin } = await import(
  "../../sessionchat/kit/common/opencode/plugins/agentschat.js"
)

/** Поддельный контекст V2: хуки и подписка собираются вручную, события толкает тест. */
function setupAgentschat() {
  const delivered = []
  const toolHooks = new Map()
  const sessionHooks = new Map()
  const queue = []
  const waiters = []
  const push = (event) => {
    const waiter = waiters.shift()
    if (waiter) waiter(event)
    else queue.push(event)
  }
  const next = (signal) =>
    new Promise((resolve) => {
      if (signal?.aborted) return resolve(null)
      if (queue.length) return resolve(queue.shift())
      const waiter = (event) => resolve(event)
      waiters.push(waiter)
      signal?.addEventListener(
        "abort",
        () => {
          const index = waiters.indexOf(waiter)
          if (index >= 0) waiters.splice(index, 1)
          resolve(null)
        },
        { once: true },
      )
    })
  const registration = () => ({ dispose: async () => {} })
  const ctx = {
    session: {
      prompt: async ({ sessionID, text }) => {
        delivered.push(`${sessionID} <- ${text}`)
      },
      hook: async (name, callback) => {
        sessionHooks.set(name, callback)
        return registration()
      },
    },
    tool: {
      hook: async (name, callback) => {
        toolHooks.set(name, callback)
        return registration()
      },
    },
    event: {
      subscribe: ({ signal } = {}) =>
        (async function* () {
          for (;;) {
            const event = await next(signal)
            if (!event) return
            yield event
          }
        })(),
    },
  }
  // dispose одноразовый: повторный вызов не должен уменьшать счётчик экземпляров ещё раз.
  let disposed = false
  return plugin.setup(ctx).then((dispose) => ({
    ctx,
    toolHooks,
    sessionHooks,
    delivered,
    push,
    dispose: async () => {
      if (disposed) return
      disposed = true
      await dispose()
    },
  }))
}

/** Состояние плагина живёт в globalThis, поэтому чистим его между проверками. */
function fresh() {
  delete globalThis.__agentschat
  asked = []
  served = new Set()
  AGENTS.forEach(writeToken)
}

const runCommand = async (instance, callID, sessionID, command, output) => {
  const meta = { tool: "bash", sessionID, agent: "build", messageID: "msg", id: callID }
  const input = { command }
  await instance.toolHooks.get("execute.before")({ ...meta, input })
  await instance.toolHooks.get("execute.after")({
    ...meta,
    input,
    status: "completed",
    result: { content: [{ type: "text", text: output }] },
  })
}

const resultLine = (fields) => `AGENTSCHAT-RESULT ${JSON.stringify(fields)}`

const loginOk = (agent) =>
  resultLine({ command: "login", ok: true, agent, mode: "plugin", reconnected: false })

const logoutOk = (agent) => resultLine({ command: "logout", ok: true, agent })

async function login(instance, callID, sessionID, agent, launcher = "agentschat") {
  await runCommand(
    instance,
    callID,
    sessionID,
    `${launcher} login --agent ${agent} --label "тест"`,
    `AGENTSCHAT: сессия ${agent} подключена к комнате !x:y.\n${loginOk(agent)}\n`,
  )
}

test("две сессии под разными именами получают каждая своё", async () => {
  fresh()
  // Два экземпляра плагина — так выглядят две сессии в одном процессе OpenCode.
  const one = await setupAgentschat()
  const two = await setupAgentschat()
  try {
    await login(one, "c1", "ses-terra", "terra")
    await login(two, "c2", "ses-helium", "helium")
    await new Promise((r) => setTimeout(r, 400))

    assert.deepEqual([...one.delivered, ...two.delivered].sort(), [
      "ses-helium <- конверт для helium",
      "ses-terra <- конверт для terra",
    ])
    // Каждое имя опрашивает брокера своим токеном, чужим не пользуется.
    assert.ok(asked.includes("terra/tok-terra") && asked.includes("helium/tok-helium"))

    const state = globalThis.__agentschat

    // logout одной сессии не глушит соседнюю.
    await runCommand(
      one,
      "c3",
      "ses-terra",
      "agentschat logout --agent terra",
      `AGENTSCHAT: сессия terra отключена.\n${logoutOk("terra")}\n`,
    )
    assert.equal(state.bindings.has("terra"), false)
    assert.equal(state.bindings.has("helium"), true)

    // Циклы гасит только последний ушедший экземпляр плагина.
    await one.dispose()
    assert.equal(state.stopped, false)
    await two.dispose()
    assert.equal(state.stopped, true)
  } finally {
    await one.dispose()
    await two.dispose()
  }
})

test("закрытая сессия освобождает свой слот", async () => {
  fresh()
  const instance = await setupAgentschat()
  try {
    await login(instance, "c1", "ses-terra", "terra")
    await login(instance, "c2", "ses-helium", "helium")

    instance.push({ type: "session.deleted", data: { sessionID: "ses-terra" } })
    await new Promise((r) => setTimeout(r, 50))

    const state = globalThis.__agentschat
    assert.ok(asked.includes("logout/terra"), "брокеру сказано про закрытую сессию")
    assert.equal(state.bindings.has("terra"), false)
    // Соседняя сессия того же процесса продолжает жить.
    assert.equal(state.bindings.has("helium"), true)
    assert.ok(!asked.includes("logout/helium"))

    // Последний экземпляр уходит — слот НЕ отпускается намеренно: выгрузка
    // происходит и на горячем сейве файла плагина, а не только при закрытии
    // OpenCode. Отпускать привязку в таком случае значит выбросить живую
    // сессию из чата. Слот остаётся за ней до счёта молчания брокера.
    await instance.dispose()
    assert.equal(asked.includes("logout/helium"), false)
    assert.equal(globalThis.__agentschat.bindings.get("helium")?.sessionID, "ses-helium")
  } finally {
    await instance.dispose()
  }
})

test("привязка без токена не висит вечно", async () => {
  // Так выглядит снятая снаружи сессия: файла с токеном больше нет. Раньше
  // цикл молча крутился на нём вхолостую, изображая живую привязку.
  fresh()
  fs.rmSync(path.join(store, "terra.json"))
  const instance = await setupAgentschat()
  try {
    await login(instance, "c1", "ses-terra", "terra")

    const state = globalThis.__agentschat
    assert.equal(state.bindings.has("terra"), true)
    // Порог — двадцать попыток; паузу задаёт AGENTSCHAT_RETRY_MS, иначе ждать
    // пришлось бы минуту.
    await new Promise((r) => setTimeout(r, 40 * 25))
    assert.equal(state.bindings.has("terra"), false, "привязка снята")
    assert.ok(!asked.some((a) => a.startsWith("terra/")), "брокера не дёргали без токена")
  } finally {
    await instance.dispose()
  }
})

test("старый вызов по пути bridge\\agentschat.cmd тоже привязывает сессию", async () => {
  fresh()
  const instance = await setupAgentschat()
  try {
    await login(instance, "c1", "ses-terra", "terra", "bridge\\agentschat.cmd")

    assert.equal(globalThis.__agentschat.bindings.get("terra")?.sessionID, "ses-terra")
  } finally {
    await instance.dispose()
  }
})

const logFile = path.join(store, "opencode-plugin.log")
const readLog = () => (fs.existsSync(logFile) ? fs.readFileSync(logFile, "utf8") : "")
const bindings = () => globalThis.__agentschat.bindings
const CYRILLIC = /[Ѐ-ӿ]/

async function withPlugin(body) {
  fresh()
  fs.rmSync(logFile, { force: true })
  const instance = await setupAgentschat()
  try {
    await body(instance)
  } finally {
    await instance.dispose()
  }
}

const loginCommand = (agent) => `agentschat login --agent ${agent}`
const logoutCommand = (agent) => `agentschat logout --agent ${agent}`

test("an English login result line binds the session of the call to the agent", async () => {
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `AGENTSCHAT: session terra is connected to room !x:y.\n${loginOk("terra")}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("the old Russian sentences alone no longer bind a session", async () => {
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
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
  await withPlugin(async (instance) => {
    await login(instance, "c1", "ses-terra", "terra")
    await runCommand(
      instance,
      "c2",
      "ses-terra",
      logoutCommand("terra"),
      "AGENTSCHAT: сессия terra отключена.\n",
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a refused login changes nothing", async () => {
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
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
  await withPlugin(async (instance) => {
    await login(instance, "c1", "ses-terra", "terra")
    await runCommand(
      instance,
      "c2",
      "ses-other",
      loginCommand("terra"),
      `${resultLine({ command: "login", ok: false, agent: "terra", code: "slot_taken" })}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a logout result line unbinds the agent", async () => {
  await withPlugin(async (instance) => {
    await login(instance, "c1", "ses-terra", "terra")
    await login(instance, "c2", "ses-helium", "helium")
    await runCommand(
      instance,
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
  await withPlugin(async (instance) => {
    await login(instance, "c1", "ses-terra", "terra")
    await runCommand(
      instance,
      "c2",
      "ses-terra",
      logoutCommand("terra"),
      `${resultLine({ command: "logout", ok: false, agent: "terra", code: "not_logged_in" })}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a result line among unrelated lines is found, CRLF line ends included", async () => {
  await withPlugin(async (instance) => {
    const output = [
      "some banner",
      "{\"command\":\"login\",\"ok\":false}",
      "AGENTSCHAT: session terra is connected.",
      loginOk("terra"),
      "",
    ].join("\r\n")
    await runCommand(instance, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a result line has to start its line to count", async () => {
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `echo: ${loginOk("terra")}\n`,
    )
    assert.equal(bindings().has("terra"), false)
  })
})

test("a forged ok line above the real refusal does not bind", async () => {
  await withPlugin(async (instance) => {
    const output = [
      `AGENTSCHAT: slot taken by label ${loginOk("helium")}`,
      loginOk("helium"),
      resultLine({ command: "login", ok: false, agent: "terra", code: "slot_taken" }),
    ].join("\n")
    await runCommand(instance, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().size, 0)
  })
})

test("a forged refusal above the real success does not stop the binding", async () => {
  await withPlugin(async (instance) => {
    const output = [
      resultLine({ command: "login", ok: false, agent: "terra", code: "slot_taken" }),
      loginOk("terra"),
    ].join("\n")
    await runCommand(instance, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a malformed last result line is ignored, logged and never thrown", async () => {
  await withPlugin(async (instance) => {
    const output = `${loginOk("terra")}\nAGENTSCHAT-RESULT {"command":"login","ok":tru\n`
    await runCommand(instance, "c1", "ses-terra", loginCommand("terra"), output)
    assert.equal(bindings().has("terra"), false)
    assert.match(readLog(), /login: result line is not valid JSON/)
  })
})

test("a result line that is not a JSON object is ignored", async () => {
  await withPlugin(async (instance) => {
    for (const [index, body] of ["null", "[1]", "\"text\"", "7"].entries()) {
      await runCommand(
        instance,
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
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `${resultLine({ command: "status", ok: true, language: "en", sessions: [] })}\n`,
    )
    assert.equal(bindings().has("terra"), false)

    await login(instance, "c2", "ses-terra", "terra")
    await runCommand(
      instance,
      "c3",
      "ses-terra",
      logoutCommand("terra"),
      `${loginOk("terra")}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a line without a usable ok changes nothing", async () => {
  await withPlugin(async (instance) => {
    for (const [index, fields] of [
      { command: "login", agent: "terra" },
      { command: "login", ok: "true", agent: "terra" },
      { command: "login", ok: 1, agent: "terra" },
    ].entries()) {
      await runCommand(
        instance,
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
  await withPlugin(async (instance) => {
    const agents = ["", " ", 7, null, ["terra"], "-terra", "../terra", "ter ra", "tërra"]
    for (const [index, agent] of agents.entries()) {
      await runCommand(
        instance,
        `c${index}`,
        "ses-terra",
        loginCommand("terra"),
        `${loginOk(agent)}\n`,
      )
    }
    await runCommand(
      instance,
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
  await withPlugin(async (instance) => {
    await login(instance, "c1", "ses-terra", "terra")
    await runCommand(
      instance,
      "c2",
      "ses-terra",
      logoutCommand("terra"),
      `${logoutOk("")}\n`,
    )
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("the agent of the result line decides, as the CLI reported it", async () => {
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
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
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      `${resultLine({ command: "login", ok: false, code: "bad code\nwith lines" })}\n`,
    )
    assert.match(readLog(), /login refused for session ses-terra, code unknown/)
  })
})

test("a call that is not a chat command is not read at all", async () => {
  await withPlugin(async (instance) => {
    await runCommand(instance, "c1", "ses-terra", "ls -la", `${loginOk("terra")}\n`)
    assert.equal(bindings().size, 0)
  })
})

test("a tool result split into several text parts is joined before the result line is read", async () => {
  await withPlugin(async (instance) => {
    const meta = { tool: "bash", sessionID: "ses-terra", agent: "build", messageID: "msg", id: "c1" }
    const input = { command: loginCommand("terra") }
    await instance.toolHooks.get("execute.before")({ ...meta, input })
    await instance.toolHooks.get("execute.after")({
      ...meta,
      input,
      status: "completed",
      result: {
        content: [
          { type: "text", text: "AGENTSCHAT: session terra is connected.\n" },
          { type: "text", text: `${loginOk("terra")}\n` },
        ],
      },
    })
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a tool call that ended in error binds nothing", async () => {
  await withPlugin(async (instance) => {
    const meta = { tool: "bash", sessionID: "ses-terra", agent: "build", messageID: "msg", id: "c1" }
    const input = { command: loginCommand("terra") }
    await instance.toolHooks.get("execute.before")({ ...meta, input })
    await instance.toolHooks.get("execute.after")({
      ...meta,
      input,
      status: "error",
      error: { message: "agentschat not found" },
    })
    assert.equal(bindings().has("terra"), false)
  })
})

test("delivery still reaches a session bound by a result line", async () => {
  fresh()
  const instance = await setupAgentschat()
  try {
    await runCommand(instance, "c1", "ses-terra", loginCommand("terra"), `${loginOk("terra")}\n`)
    await new Promise((r) => setTimeout(r, 300))
    assert.deepEqual(instance.delivered, ["ses-terra <- конверт для terra"])
  } finally {
    await instance.dispose()
  }
})

test("a message in a session whose name we saw binds it (prompt-hook fallback)", async () => {
  await withPlugin(async (instance) => {
    // Видим только вызов login, итог его не доходит — привязки ещё нет.
    await instance.toolHooks.get("execute.before")({
      tool: "bash",
      sessionID: "ses-terra",
      agent: "build",
      messageID: "msg",
      id: "c1",
      input: { command: loginCommand("terra") },
    })
    assert.equal(bindings().has("terra"), false)

    // Первое же сообщение в этой сессии привязывает её к имени.
    await instance.sessionHooks.get("prompt")({ sessionID: "ses-terra" })
    assert.equal(bindings().get("terra")?.sessionID, "ses-terra")
  })
})

test("a message in a session we know nothing about binds nothing", async () => {
  await withPlugin(async (instance) => {
    await instance.sessionHooks.get("prompt")({ sessionID: "ses-stranger" })
    assert.equal(bindings().size, 0)
  })
})

test("a fresh instance resumes polling a binding left by the previous one", async () => {
  // Так выглядит горячая перезагрузка плагина: старая копия выгружена,
  // привязка осталась в globalThis. Новый экземпляр обязан возобновить
  // опрос, иначе живой сессии не придёт ни одного сообщения.
  fresh()
  const one = await setupAgentschat()
  await login(one, "c1", "ses-terra", "terra")
  await new Promise((r) => setTimeout(r, 300))
  one.delivered.length = 0
  await one.dispose()
  assert.equal(globalThis.__agentschat.bindings.get("terra")?.sessionID, "ses-terra")

  // Брокер уже отдавал конверт этой секцией процесса — разрешаем ему отдать снова.
  served = new Set()
  asked = []
  const two = await setupAgentschat()
  try {
    await new Promise((r) => setTimeout(r, 400))
    assert.equal(two.delivered.includes("ses-terra <- конверт для terra"), true)
  } finally {
    await two.dispose()
  }
})

test("a partially unloaded instance does not steal the delivery context", async () => {
  // Порядок «загрузили новый, потом выгрузили старый»: привязку обслуживает
  // цикл, запущенный первым экземпляром. Доставка обязана идти через живой
  // (второй) экземпляр, а не через выгруженный первый.
  fresh()
  const first = await setupAgentschat()
  const second = await setupAgentschat()
  try {
    await login(first, "c1", "ses-terra", "terra")
    await new Promise((r) => setTimeout(r, 300))
    first.delivered.length = 0
    second.delivered.length = 0
    // Брокер отдаёт конверт повторно.
    served = new Set()
    asked = []
    await first.dispose()
    assert.equal(globalThis.__agentschat.bindings.get("terra")?.sessionID, "ses-terra")

    await new Promise((r) => setTimeout(r, 400))
    assert.deepEqual(first.delivered, [])
    assert.equal(second.delivered.includes("ses-terra <- конверт для terra"), true)
  } finally {
    await first.dispose()
    await second.dispose()
  }
})

test("the newest instance unloading hands delivery to the surviving one", async () => {
  // Порядок «выгрузили последний загруженный экземпляр, более старый остался
  // жить»: доставка обязана перейти выжившему. Поддельный prompt выгруженного
  // бросает ошибку — если бы хвост остался указывать в неё, конверт бы потерялся.
  fresh()
  const first = await setupAgentschat()
  const second = await setupAgentschat()
  try {
    await login(first, "c1", "ses-terra", "terra")
    await new Promise((r) => setTimeout(r, 300))
    // Кто обслуживает доставку по умолчанию — второй экземпляр (последний загружен).
    assert.equal(second.delivered.length > 0, true)
    first.delivered.length = 0
    second.delivered.length = 0
    served = new Set()
    asked = []

    // Второй выгружается, а его ctx «умирает»: prompt теперь бросает.
    second.ctx.session.prompt = async () => {
      throw new Error("context is dead")
    }
    await second.dispose()
    assert.equal(globalThis.__agentschat.bindings.get("terra")?.sessionID, "ses-terra")

    await new Promise((r) => setTimeout(r, 500))
    assert.equal(first.delivered.includes("ses-terra <- конверт для terra"), true)
    assert.deepEqual(second.delivered, [])
  } finally {
    await first.dispose()
    await second.dispose()
  }
})

test("the plugin log is English whatever the CLI printed", async () => {
  await withPlugin(async (instance) => {
    await runCommand(
      instance,
      "c1",
      "ses-terra",
      loginCommand("terra"),
      "AGENTSCHAT: сессия terra подключена к комнате !x:y.\n",
    )
    await login(instance, "c2", "ses-terra", "terra")
    await new Promise((r) => setTimeout(r, 300))
    await runCommand(
      instance,
      "c3",
      "ses-terra",
      logoutCommand("terra"),
      `${logoutOk("terra")}\n`,
    )
    instance.push({ type: "session.deleted", data: { sessionID: "ses-terra" } })
    await new Promise((r) => setTimeout(r, 50))
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
    new URL("../../sessionchat/kit/common/opencode/plugins/agentschat.js", import.meta.url),
    "utf8",
  )
  const offending = withoutComments(source)
    .split("\n")
    .filter((line) => CYRILLIC.test(line))
  assert.deepEqual(offending, [])
})

test.after(() => server.close())
