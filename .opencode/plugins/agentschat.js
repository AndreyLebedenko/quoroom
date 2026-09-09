/**
 * AgentsChat: связь живых сессий OpenCode с общей комнатой Matrix.
 *
 * У Claude Code роль слушателя играет фоновый процесс: он умирает при входящем
 * сообщении, и его смерть будит сессию. У OpenCode такого механизма нет, зато
 * есть плагины — они живут внутри того же процесса, что и сервер сессий, и
 * могут положить сообщение в сессию напрямую через client.session.promptAsync.
 * Поэтому здесь слушателем работает сам плагин.
 *
 * Плагин НЕ подключает сессию сам. Подключает человек: он открывает нужную
 * сессию и вызывает /chatlogin, тот выполняет `agentschat login --agent ИМЯ`.
 * Плагин видит этот вызов в хуках инструментов, запоминает, КАКАЯ сессия под
 * КАКИМ именем вошла, и начинает опрашивать брокера. Так остаётся в силе
 * главное правило: в чат заходят не агенты, а их конкретные сессии, и выбирает
 * их человек.
 *
 * Имя агента не зашито. Одна сессия может войти как `terra` (модель OpenAI),
 * другая — как `helium` (модель через Ollama), и в комнате это два разных
 * участника Matrix со своей адресацией, пилюлями и цветом. Поэтому привязка
 * здесь — не одна переменная, а карта «имя агента → сессия», и у каждой
 * привязки свой цикл опроса.
 *
 * Токен брокера плагин не выдумывает: его кладёт в ~/.agentschat/<имя>.json
 * та же команда login. Matrix-токенов у плагина нет вовсе — публикует брокер.
 */

import fs from "node:fs"
import os from "node:os"
import path from "node:path"

const BROKER = process.env.AGENTSCHAT_URL || "http://127.0.0.1:8770"
const HOME = path.join(os.homedir(), ".agentschat")
// Потолок long-poll у брокера — 50с; ждём чуть дольше, чем он молчит.
const POLL_TIMEOUT_MS = 70_000
// Пауза перед повтором. Переменной окружения тут место только ради проверки:
// тест не может ждать минуту, чтобы увидеть, как снимается привязка.
const RETRY_MS = Number(process.env.AGENTSCHAT_RETRY_MS) || 3_000
// Сколько попыток подряд терпеть отсутствие файла с токеном, прежде чем
// признать привязку недействительной. Двадцать попыток — минута.
const TOKENLESS_LIMIT = 20
// Лог кладём рядом с токенами, а не в каталог плагина: путь предсказуем и
// одинаков, из какого бы каталога плагин ни загрузился. Лог один на все
// привязки — каждая строка называет имя агента.
const LOG = path.join(HOME, "opencode-plugin.log")

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function note(message) {
  const line = `${new Date().toISOString()} ${message}\n`
  try {
    fs.mkdirSync(HOME, { recursive: true })
    fs.appendFileSync(LOG, line)
  } catch {
    /* лог — удобство, а не условие работы */
  }
  // В stdout не пишем: у CLI это тот же терминал, где рисуется TUI.
}

function brokerToken(agent) {
  const file = path.join(HOME, `${agent}.json`)
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")).token || null
  } catch {
    return null
  }
}

/**
 * Похоже ли это на вызов нашего CLI с командой login/logout, и под каким
 * именем. Имя берём из той же строки: `--agent terra` или `--agent=terra`.
 * Без имени команда бессмысленна и для самого CLI, значит и привязки нет.
 */
function chatCommand(args) {
  const text = typeof args === "string" ? args : JSON.stringify(args ?? "")
  if (!/agentschat/i.test(text)) return null
  const kind = /\blogout\b/.test(text) ? "logout" : /\blogin\b/.test(text) ? "login" : null
  if (!kind) return null
  const found = text.match(/--agent[=\s]+["']?([A-Za-z0-9][\w-]*)/)
  if (!found) return null
  return { kind, agent: found[1] }
}

/**
 * Состояние общее на весь процесс OpenCode, а не на экземпляр плагина: две
 * сессии в одном процессе делят и карту привязок, и запущенные циклы опроса.
 * Хуки при этом регистрирует КАЖДЫЙ экземпляр — иначе login во второй сессии
 * никто бы не увидел. Повторная обработка безопасна: pending снимается по
 * callID, а цикл на имя агента заводится ровно один.
 */
function shared() {
  if (!globalThis.__agentschat) {
    globalThis.__agentschat = {
      /** имя агента → { sessionID, looping } */
      bindings: new Map(),
      /** callID незавершённых вызовов CLI → что именно они делают */
      pending: new Map(),
      /** sessionID → имя, под которым эта сессия входила в чат */
      names: new Map(),
      /** сколько экземпляров плагина живо: последний гасит циклы */
      instances: 0,
      stopped: false,
    }
  }
  return globalThis.__agentschat
}

export const AgentsChat = async ({ client }) => {
  const state = shared()
  state.instances += 1
  state.stopped = false
  note(`плагин загружен из ${import.meta.url}, брокер ${BROKER}`)

  async function deliver(sessionID, text) {
    await client.session.promptAsync({
      path: { id: sessionID },
      body: { parts: [{ type: "text", text }] },
    })
  }

  async function poll(agent, token) {
    const url =
      `${BROKER}/wait?agent=${encodeURIComponent(agent)}` +
      `&token=${encodeURIComponent(token)}`
    const response = await fetch(url, { signal: AbortSignal.timeout(POLL_TIMEOUT_MS) })
    if (response.status === 204) return null
    if (response.status === 409) {
      // Сессия отключена, либо на диске остался токен от прошлого запуска
      // брокера. Ждём нового login и не дёргаемся на каждое сообщение.
      note(`${agent}: брокер больше не знает эту сессию: ${(await response.text()).trim()}`)
      state.bindings.delete(agent)
      return null
    }
    if (!response.ok) throw new Error(`брокер ответил ${response.status}`)
    const data = await response.json()
    return String(data.rendered || data.text || "")
  }

  async function loop(agent) {
    const bound = state.bindings.get(agent)
    if (!bound || bound.looping) return
    bound.looping = true
    note(`${agent}: слушаю брокера для сессии ${bound.sessionID}`)
    // Цикл живёт, пока эта привязка остаётся текущей: logout, отказ брокера
    // или вход другой сессии под тем же именем заменяют её, и цикл выходит.
    while (!state.stopped && state.bindings.get(agent) === bound) {
      const token = brokerToken(agent)
      if (!token) {
        // Файла с токеном нет: login ещё не дописал его — или кто-то снял
        // сессию снаружи. Молчать тут нельзя: однажды такой цикл крутился
        // впустую полчаса, а привязка снаружи выглядела живой.
        bound.tokenless = (bound.tokenless || 0) + 1
        if (bound.tokenless === 1) note(`${agent}: токен не найден, жду`)
        if (bound.tokenless > TOKENLESS_LIMIT) {
          note(`${agent}: токена так и нет, привязку снимаю — нужен новый login`)
          state.bindings.delete(agent)
        }
        await sleep(RETRY_MS)
        continue
      }
      bound.tokenless = 0
      let envelope = null
      try {
        envelope = await poll(agent, token)
      } catch (error) {
        // Брокер мог быть перезапущен или ещё не поднят. Плагин, в отличие от
        // отдельного listener, умирать не может и не должен: он просто ждёт.
        note(`${agent}: опрос не удался (${error.message}), повтор через ${RETRY_MS / 1000}с`)
        await sleep(RETRY_MS)
        continue
      }
      if (!envelope || state.bindings.get(agent) !== bound) continue
      try {
        await deliver(bound.sessionID, envelope)
        note(`${agent}: сообщение доставлено в сессию ${bound.sessionID}`)
      } catch (error) {
        note(
          `${agent}: не удалось вложить сообщение в сессию ${bound.sessionID}: ${error.message}`,
        )
        await sleep(RETRY_MS)
      }
    }
    bound.looping = false
    note(`${agent}: опрос остановлен`)
  }

  /**
   * Сказать брокеру, что этой сессии больше нет. Слот освободится сразу, а не
   * через три минуты молчания, и человеку не придётся выбивать его руками.
   * Дело это необязательное: закрытое приложение может не успеть ничего, и
   * страховкой остаётся счёт молчания на стороне брокера.
   */
  async function releaseSlot(agent, why) {
    const bound = state.bindings.get(agent)
    state.bindings.delete(agent)
    const token = brokerToken(agent)
    if (!token) return
    try {
      await fetch(`${BROKER}/logout`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ agent, token }),
        signal: AbortSignal.timeout(5_000),
      })
      note(`${agent}: слот освобождён (${why}), сессия ${bound?.sessionID ?? "?"}`)
    } catch (error) {
      note(`${agent}: слот освободить не удалось (${why}): ${error.message}`)
    }
  }

  function bind(agent, sessionID, why) {
    const already = state.bindings.get(agent)
    if (already && already.sessionID === sessionID) return
    state.bindings.set(agent, { sessionID, looping: false })
    note(`${why}: агент ${agent} — сессия ${sessionID}`)
    loop(agent)
  }

  return {
    "tool.execute.before": async (input, output) => {
      const seen = chatCommand(output?.args)
      if (!seen) return
      state.pending.set(input.callID, { ...seen, sessionID: input.sessionID })
      state.names.set(input.sessionID, seen.agent)
    },

    "tool.execute.after": async (input, output) => {
      const started = state.pending.get(input.callID)
      if (!started) return
      state.pending.delete(input.callID)
      const text = String(output?.output ?? "")
      if (started.kind === "login" && text.includes("подключена к комнате")) {
        bind(started.agent, started.sessionID, "к чату подключена сессия")
      }
      if (started.kind === "logout" && text.includes("отключена")) {
        note(`${started.agent}: сессия ${started.sessionID} отключена от чата`)
        state.bindings.delete(started.agent)
      }
    },

    "chat.message": async (input) => {
      // Запасной путь: если хук завершения вызова почему-то не сработал, но имя
      // из команды login мы видели, а токен уже лежит на диске — привязываемся
      // к сессии, в которой идёт разговор. Без виденного имени гадать нельзя:
      // в ~/.agentschat лежат токены и чужих агентов, и чужих сессий.
      const agent = state.names.get(input.sessionID)
      if (!agent || state.bindings.has(agent)) return
      if (!brokerToken(agent)) return
      bind(agent, input.sessionID, "привязка по сообщению, а не по login")
    },

    event: async (input) => {
      // Сессию закрыли в самом OpenCode. Слот держать больше не за кого.
      if (input?.event?.type !== "session.deleted") return
      const sessionID = input.event.properties?.info?.id
      if (!sessionID) return
      for (const [agent, bound] of state.bindings) {
        if (bound.sessionID === sessionID) await releaseSlot(agent, "сессия закрыта")
      }
      state.names.delete(sessionID)
    },

    dispose: async () => {
      state.instances -= 1
      if (state.instances > 0) return
      state.stopped = true
      // Уходит последний экземпляр — значит закрывается сам OpenCode.
      // Успеть освободить слоты получается не всегда: убитый процесс не
      // исполняет ничего. Поэтому это ускорение, а не гарантия.
      for (const agent of [...state.bindings.keys()]) {
        await releaseSlot(agent, "OpenCode закрывается")
      }
      state.bindings.clear()
    },
  }
}
