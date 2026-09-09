/**
 * Проверка плагина без OpenCode и без брокера: вместо них — поддельный клиент
 * и обычный http-сервер. Главное, что здесь проверяется, — две сессии в одном
 * процессе живут под разными именами и не мешают друг другу.
 *
 *     node --test .opencode/plugins/agentschat.test.mjs
 */

import assert from "node:assert/strict"
import fs from "node:fs"
import http from "node:http"
import os from "node:os"
import path from "node:path"
import test from "node:test"

const AGENTS = ["terra", "helium"]

/** Домашний каталог подменяем до импорта плагина: он читает его при загрузке. */
function fakeHome() {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "agentschat-home-"))
  process.env.USERPROFILE = home
  process.env.HOME = home
  fs.mkdirSync(path.join(home, ".agentschat"), { recursive: true })
  for (const agent of AGENTS) {
    fs.writeFileSync(
      path.join(home, ".agentschat", `${agent}.json`),
      JSON.stringify({ agent, token: `tok-${agent}` }),
    )
  }
  return home
}

/** Брокер, который каждому имени отдаёт ровно один конверт, потом молчит. */
async function fakeBroker(asked) {
  const server = http.createServer((req, res) => {
    const url = new URL(req.url, "http://127.0.0.1")
    const agent = url.searchParams.get("agent")
    asked.push(`${agent}/${url.searchParams.get("token")}`)
    if (asked.filter((a) => a.startsWith(`${agent}/`)).length > 1) {
      res.writeHead(204).end()
      return
    }
    res.writeHead(200, { "content-type": "application/json" })
    res.end(JSON.stringify({ rendered: `конверт для ${agent}` }))
  })
  await new Promise((r) => server.listen(0, "127.0.0.1", r))
  process.env.AGENTSCHAT_URL = `http://127.0.0.1:${server.address().port}`
  return server
}

async function login(hooks, callID, sessionID, agent) {
  await hooks["tool.execute.before"](
    { callID, sessionID },
    { args: { command: `bridge\\agentschat.cmd login --agent ${agent} --label "тест"` } },
  )
  await hooks["tool.execute.after"](
    { callID, sessionID },
    { output: `AGENTSCHAT: сессия ${agent} подключена к комнате !x:y.` },
  )
}

test("две сессии под разными именами получают каждая своё", async () => {
  fakeHome()
  const asked = []
  const server = await fakeBroker(asked)
  const delivered = []
  const client = {
    session: {
      promptAsync: async ({ path: p, body }) =>
        delivered.push(`${p.id} <- ${body.parts[0].text}`),
    },
  }

  const { AgentsChat } = await import("./agentschat.js")
  // Два экземпляра плагина — так выглядят две сессии в одном процессе OpenCode.
  const one = await AgentsChat({ client })
  const two = await AgentsChat({ client })

  await login(one, "c1", "ses-terra", "terra")
  await login(two, "c2", "ses-helium", "helium")
  await new Promise((r) => setTimeout(r, 800))

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

  server.close()
})
