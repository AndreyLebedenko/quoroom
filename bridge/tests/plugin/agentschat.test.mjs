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

async function login(hooks, callID, sessionID, agent, launcher = "agentschat") {
  await hooks["tool.execute.before"](
    { callID, sessionID },
    { args: { command: `${launcher} login --agent ${agent} --label "тест"` } },
  )
  await hooks["tool.execute.after"](
    { callID, sessionID },
    { output: `AGENTSCHAT: сессия ${agent} подключена к комнате !x:y.` },
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
    { output: "AGENTSCHAT: сессия terra отключена." },
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

test.after(() => server.close())
