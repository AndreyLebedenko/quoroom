/**
 * AgentsChat: связь живой сессии OpenCode с общей комнатой Matrix.
 *
 * У Claude Code роль слушателя играет фоновый процесс: он умирает при входящем
 * сообщении, и его смерть будит сессию. У OpenCode такого механизма нет, зато
 * есть плагины — они живут внутри того же процесса, что и сервер сессий, и
 * могут положить сообщение в сессию напрямую через client.session.promptAsync.
 * Поэтому здесь слушателем работает сам плагин.
 *
 * Плагин НЕ подключает сессию сам. Подключает человек: он открывает нужную
 * сессию и вызывает /chatlogin, тот выполняет `agentschat login`. Плагин видит
 * этот вызов в хуках инструментов, запоминает, КАКАЯ сессия его сделала, и
 * начинает опрашивать брокера. Так остаётся в силе главное правило: в чат
 * заходят не агенты, а их конкретные сессии, и выбирает их человек.
 *
 * Токен брокера плагин не выдумывает: его кладёт в ~/.agentschat/opencode.json
 * та же команда login. Matrix-токенов у плагина нет вовсе — публикует брокер.
 */

import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const AGENT = "opencode"
const BROKER = process.env.AGENTSCHAT_URL || "http://127.0.0.1:8770"
const STORE = path.join(os.homedir(), ".agentschat", `${AGENT}.json`)
// Потолок long-poll у брокера — 50с; ждём чуть дольше, чем он молчит.
const POLL_TIMEOUT_MS = 70_000
const RETRY_MS = 3_000
// Лог кладём рядом с токеном, а не в каталог плагина: путь предсказуем и
// одинаков, из какого бы каталога плагин ни загрузился.
const LOG = path.join(path.dirname(STORE), `${AGENT}-plugin.log`)

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function note(message) {
  const line = `${new Date().toISOString()} ${message}\n`
  try {
    fs.mkdirSync(path.dirname(LOG), { recursive: true })
    fs.appendFileSync(LOG, line)
  } catch {
    /* лог — удобство, а не условие работы */
  }
  // В stdout не пишем: у CLI это тот же терминал, где рисуется TUI.
}

function brokerToken() {
  try {
    return JSON.parse(fs.readFileSync(STORE, "utf8")).token || null
  } catch {
    return null
  }
}

/** Похоже ли это на вызов нашего CLI с командой login/logout. */
function commandKind(args) {
  const text = typeof args === "string" ? args : JSON.stringify(args ?? "")
  if (!/agentschat/i.test(text)) return null
  if (/\blogout\b/.test(text)) return "logout"
  if (/\blogin\b/.test(text)) return "login"
  return null
}

export const AgentsChat = async ({ client }) => {
  // Каталог плагинов может оказаться не один; работает первая копия, а
  // остальные молча уступают, иначе брокер увидит несколько слушателей.
  if (globalThis.__agentschat) {
    note(`копия плагина уступила уже работающей: ${import.meta.url}`)
    return {}
  }
  globalThis.__agentschat = { source: import.meta.url }
  note(`плагин загружен из ${import.meta.url}, брокер ${BROKER}`)

  /** Сессия, которая выполнила login. Только в неё уходит доставка. */
  let target = null
  /** callID незавершённых вызовов CLI: чья сессия их запустила. */
  const pending = new Map()
  let looping = false
  let stopped = false
  /** Токен, который брокер уже отверг: с ним привязываться заново незачем. */
  let rejected = null

  async function deliver(text) {
    await client.session.promptAsync({
      path: { id: target },
      body: { parts: [{ type: "text", text }] },
    })
  }

  async function poll(token) {
    const url = `${BROKER}/wait?agent=${AGENT}&token=${encodeURIComponent(token)}`
    const response = await fetch(url, { signal: AbortSignal.timeout(POLL_TIMEOUT_MS) })
    if (response.status === 204) return null
    if (response.status === 409) {
      // Сессия отключена, либо на диске остался токен от прошлого запуска
      // брокера. Ждём нового login и не дёргаемся на каждое сообщение.
      note(`брокер больше не знает эту сессию: ${(await response.text()).trim()}`)
      rejected = token
      target = null
      return null
    }
    if (!response.ok) throw new Error(`брокер ответил ${response.status}`)
    const data = await response.json()
    return String(data.rendered || data.text || "")
  }

  async function loop() {
    if (looping) return
    looping = true
    note(`слушаю брокера для сессии ${target}`)
    while (!stopped && target) {
      const token = brokerToken()
      if (!token) {
        await sleep(RETRY_MS)
        continue
      }
      let envelope = null
      try {
        envelope = await poll(token)
      } catch (error) {
        // Брокер мог быть перезапущен или ещё не поднят. Плагин, в отличие от
        // отдельного listener, умирать не может и не должен: он просто ждёт.
        note(`опрос не удался (${error.message}), повтор через ${RETRY_MS / 1000}с`)
        await sleep(RETRY_MS)
        continue
      }
      if (!envelope || !target) continue
      try {
        await deliver(envelope)
        note(`сообщение доставлено в сессию ${target}`)
      } catch (error) {
        note(`не удалось вложить сообщение в сессию ${target}: ${error.message}`)
        await sleep(RETRY_MS)
      }
    }
    looping = false
    note("опрос остановлен")
  }

  return {
    "tool.execute.before": async (input, output) => {
      const kind = commandKind(output?.args)
      if (kind) pending.set(input.callID, { kind, sessionID: input.sessionID })
    },

    "tool.execute.after": async (input, output) => {
      const started = pending.get(input.callID)
      if (!started) return
      pending.delete(input.callID)
      const text = String(output?.output ?? "")
      if (started.kind === "login" && text.includes("подключена к комнате")) {
        rejected = null
        target = started.sessionID
        note(`к чату подключена сессия ${target}`)
        loop()
      }
      if (started.kind === "logout" && text.includes("отключена")) {
        note(`сессия ${target} отключена от чата`)
        target = null
      }
    },

    "chat.message": async (input) => {
      // Запасной путь: если хуки инструмента почему-то не сработали, но токен
      // уже лежит на диске, привязываемся к сессии, в которой идёт разговор.
      const token = brokerToken()
      if (target || !token || token === rejected) return
      target = input.sessionID
      note(`сессия ${target} привязана по сообщению, а не по login`)
      loop()
    },

    dispose: async () => {
      stopped = true
      target = null
    },
  }
}
