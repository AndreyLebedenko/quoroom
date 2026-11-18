/**
 * AgentsChat: связь живых сессий OpenCode с общей комнатой Matrix.
 *
 * OpenCode 2 (CLI 2.3.2) не исполняет плагины старой формы (именованная функция,
 * хуки строками): плагин обязан экспортировать default definition с id и
 * setup. Механика осталась прежней: плагин НЕ подключает сессию сам, человек
 * подключает её вызовами `agentschat login --agent ИМЯ`, а плагин видит эти
 * вызовы в хуках инструментов, запоминает пару «имя агента → сессия» и
 * опрашивает брокера. Вложенные сообщения идут в сессию через session.prompt.
 *
 * У Claude Code роль слушателя играет фоновый процесс: он умирает при входящем
 * сообщении, и его смерть будит сессию. У OpenCode такого механизма нет, зато
 * плагин живёт внутри того же процесса, что и сервер сессий.
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

const RESULT_PREFIX = "AGENTSCHAT-RESULT "
const AGENT_NAME = /^[A-Za-z0-9][\w-]*$/
const CODE_NAME = /^[a-z][a-z0-9_]*$/

function lastResultLine(text) {
  const lines = text.split(/\r?\n/).filter((line) => line.startsWith(RESULT_PREFIX))
  return lines.length ? lines[lines.length - 1] : null
}

function resultText(result) {
  if (result == null) return ""
  if (typeof result === "string") return result
  const parts = []
  if (typeof result.content === "string") parts.push(result.content)
  else if (Array.isArray(result.content)) {
    for (const part of result.content) {
      if (part && part.type === "text" && typeof part.text === "string") parts.push(part.text)
    }
  }
  if (typeof result.output === "string") parts.push(result.output)
  else if (result.output != null) parts.push(String(result.output))
  return parts.join("\n")
}

/**
 * Итог команды login или logout из строки AGENTSCHAT-RESULT: решает последняя
 * такая строка вывода, остальной текст не читается. Возвращает null, если
 * привязку или снятие делать нельзя, и записывает причину в лог.
 */
function readResult(text, kind) {
  const line = lastResultLine(text)
  if (!line) {
    note(`${kind}: no result line in the command output, nothing changed`)
    return null
  }
  let result
  try {
    result = JSON.parse(line.slice(RESULT_PREFIX.length))
  } catch (error) {
    note(`${kind}: result line is not valid JSON (${error.message}), nothing changed`)
    return null
  }
  if (result === null || typeof result !== "object" || Array.isArray(result)) {
    note(`${kind}: result line is not a JSON object, nothing changed`)
    return null
  }
  if (result.command !== kind) return null
  if (result.ok === false) {
    const code = typeof result.code === "string" && CODE_NAME.test(result.code) ? result.code : "unknown"
    return { ok: false, code }
  }
  if (result.ok !== true) {
    note(`${kind}: result line has no boolean ok, nothing changed`)
    return null
  }
  if (typeof result.agent !== "string" || !AGENT_NAME.test(result.agent)) {
    note(`${kind}: result line names no valid agent, nothing changed`)
    return null
  }
  return { ok: true, agent: result.agent }
}

/**
 * Состояние общее на весь процесс OpenCode, а не на экземпляр плагина: две
 * сессии в одном процессе делят и карту привязок, и запущенные циклы опроса.
 * Хуки при этом регистрирует КАЖДЫЙ экземпляр — иначе login во второй сессии
 * никто бы не увидел. Повторная обработка безопасна: pending снимается по
 * id, а цикл на имя агента заводится ровно один.
 */
function shared() {
  const state = (globalThis.__agentschat ??= {
    /** имя агента → { sessionID, looping } */
    bindings: new Map(),
    /** id незавершённых вызовов CLI → что именно они делают */
    pending: new Map(),
    /** sessionID → имя, под которым эта сессия входила в чат */
    names: new Map(),
    /** типы событий OpenCode, уже попавшие в лог: пишем каждый один раз */
    seenEvents: new Set(),
    /** сколько экземпляров плагина живо: последний гасит циклы */
    instances: 0,
    stopped: false,
    /** как доставлять конверт: доставщики живых экземпляров, последний — к кому обращаться */
    deliverers: [],
  })
  // Перезагрузка плагина в живом процессе переиспользует globalThis: у
  // состояния прежней версии может не быть новых полей.
  state.bindings ??= new Map()
  state.pending ??= new Map()
  state.names ??= new Map()
  state.seenEvents ??= new Set()
  state.instances ??= 0
  state.stopped ??= false
  state.deliverers ??= []
  return state
}

export default {
  id: "agentschat",
  async setup(ctx) {
    const state = shared()
    state.instances += 1
    state.stopped = false
    // Цикл опроса переживает своих создателей, поэтому доставка ищет живого
    // доставщика в общежитии: каждый экземпляр кладёт свою функцию туда при
    // загрузке и убирает при выгрузке. Последний оставшийся — рабочий.
    const myDeliver = (sessionID, text) => ctx.session.prompt({ sessionID, text })
    state.deliverers.push(myDeliver)
    note(`plugin loaded from ${import.meta.url}, broker ${BROKER}`)

    async function poll(agent, token, bound) {
      const url =
        `${BROKER}/wait?agent=${encodeURIComponent(agent)}` +
        `&token=${encodeURIComponent(token)}`
      const control = new AbortController()
      const timer = setTimeout(() => control.abort(), POLL_TIMEOUT_MS)
      const onBoundAbort = () => control.abort()
      bound.abort?.signal.addEventListener("abort", onBoundAbort)
      try {
        const response = await fetch(url, { signal: control.signal })
        if (response.status === 204) return null
        if (response.status === 409) {
          // Токен не принят: сессия отключена, слот освобождён молчанием или
          // bridge/state удалён. Ждём нового login и не дёргаемся на каждое сообщение.
          note(`${agent}: the broker no longer knows this session: ${(await response.text()).trim()}`)
          state.bindings.delete(agent)
          return null
        }
        if (!response.ok) throw new Error(`broker answered ${response.status}`)
        const data = await response.json()
        return String(data.rendered || data.text || "")
      } finally {
        clearTimeout(timer)
        bound.abort?.signal.removeEventListener("abort", onBoundAbort)
      }
    }

    async function loop(agent) {
      const bound = state.bindings.get(agent)
      if (!bound || bound.looping) return
      bound.looping = true
      note(`${agent}: listening to the broker for session ${bound.sessionID}`)
      // Цикл живёт, пока эта привязка остаётся текущей: logout, отказ брокера
      // или вход другой сессии под тем же именем заменяют её, и цикл выходит.
      while (!state.stopped && state.bindings.get(agent) === bound) {
        const token = brokerToken(agent)
        if (!token) {
          // Файла с токеном нет: login ещё не дописал его — или кто-то снял
          // сессию снаружи. Молчать тут нельзя: однажды такой цикл крутился
          // впустую полчаса, а привязка снаружи выглядела живой.
          bound.tokenless = (bound.tokenless || 0) + 1
          if (bound.tokenless === 1) note(`${agent}: token not found, waiting`)
          if (bound.tokenless > TOKENLESS_LIMIT) {
            note(`${agent}: token still missing, dropping the binding, a new login is needed`)
            state.bindings.delete(agent)
          }
          await sleep(RETRY_MS)
          continue
        }
        bound.tokenless = 0
        let envelope = null
        try {
          envelope = await poll(agent, token, bound)
        } catch (error) {
          if (bound.abort?.signal.aborted || state.stopped) break
          // Брокер мог быть перезапущен или ещё не поднят. Плагин, в отличие от
          // отдельного listener, умирать не может и не должен: он просто ждёт.
          note(`${agent}: poll failed (${error.message}), retry in ${RETRY_MS / 1000}s`)
          await sleep(RETRY_MS)
          continue
        }
        if (!envelope || state.bindings.get(agent) !== bound) continue
        const deliver = state.deliverers[state.deliverers.length - 1]
        if (!deliver) break
        try {
          await deliver(bound.sessionID, envelope)
          note(`${agent}: message delivered to session ${bound.sessionID}`)
        } catch (error) {
          note(
            `${agent}: could not put the message into session ${bound.sessionID}: ${error.message}`,
          )
          await sleep(RETRY_MS)
        }
      }
      bound.looping = false
      note(`${agent}: polling stopped`)
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
        note(`${agent}: slot released (${why}), session ${bound?.sessionID ?? "?"}`)
      } catch (error) {
        note(`${agent}: could not release the slot (${why}): ${error.message}`)
      }
    }

    function bind(agent, sessionID, why) {
      const already = state.bindings.get(agent)
      if (already?.sessionID === sessionID && !already.abort?.signal.aborted) return
      already?.abort?.abort()
      state.bindings.set(agent, { sessionID, looping: false, abort: new AbortController() })
      note(`${why}: agent ${agent}, session ${sessionID}`)
      void loop(agent)
    }

    await ctx.tool.hook("execute.before", (event) => {
      const seen = chatCommand(event?.input)
      if (!seen) return
      state.pending.set(event.id, { ...seen, sessionID: event.sessionID })
      state.names.set(event.sessionID, seen.agent)
    })

    await ctx.tool.hook("execute.after", (event) => {
      const started = state.pending.get(event?.id)
      if (!started) return
      state.pending.delete(event.id)
      if (event.status !== "completed") return
      const result = readResult(resultText(event.result), started.kind)
      if (!result) return
      if (!result.ok) {
        note(`${started.kind} refused for session ${started.sessionID}, code ${result.code}`)
        return
      }
      if (started.kind === "login") {
        state.names.set(started.sessionID, result.agent)
        bind(result.agent, started.sessionID, "session logged in to the chat")
      } else {
        note(`${result.agent}: session ${started.sessionID} logged out of the chat`)
        state.bindings.delete(result.agent)
      }
    })

    // Запасной путь: если хук завершения вызова почему-то не сработал, но имя
    // из команды login мы видели, а токен уже лежит на диске — привязываемся
    // к сессии, в которой идёт разговор. Без виденного имени гадать нельзя:
    // в ~/.agentschat лежат токены и чужих агентов, и чужих сессий.
    await ctx.session.hook("prompt", (event) => {
      const agent = state.names.get(event?.sessionID)
      if (!agent || state.bindings.has(agent)) return
      if (!brokerToken(agent)) return
      bind(agent, event.sessionID, "binding by message, not by login")
    })

    // Горячая перезагрузка плагина выгружает и грузит его заново. Привязки,
    // пережившие перезагрузку в globalThis, отделяем от умирающих циклов
    // свежим AbortController и возобновляем: иначе живая сессия молча
    // выпадала бы из чата при любом сейве файла плагина. Живой цикл
    // (частичная выгрузка одной копии) не трогаем.
    for (const [agent, bound] of [...state.bindings]) {
      if (bound.looping && !bound.abort?.signal.aborted) continue
      bound.abort?.abort()
      state.bindings.set(agent, { sessionID: bound.sessionID, looping: false, abort: new AbortController() })
    }
    for (const agent of state.bindings.keys()) {
      void loop(agent)
    }

    const controller = new AbortController()
    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          const kind = event?.type
          if (typeof kind === "string" && kind.startsWith("session.")) {
            // Как в V1: «убить сессию» в интерфейсе не обязано означать
            // session.deleted. Пишем каждый новый тип один раз за запуск, чтобы
            // следующая проверка отвечала на этот вопрос сама.
            if (!state.seenEvents.has(kind)) {
              state.seenEvents.add(kind)
              note(`OpenCode event: ${kind}`)
            }
          }
          // Сессию закрыли в самом OpenCode. Слот держать больше не за кого.
          if (kind !== "session.deleted") continue
          const sessionID = event?.data?.sessionID
          if (!sessionID) continue
          for (const [agent, bound] of state.bindings) {
            if (bound.sessionID === sessionID) await releaseSlot(agent, "session closed")
          }
          state.names.delete(sessionID)
        }
      } catch (error) {
        if (controller.signal.aborted) return
        note(`event stream ended unexpectedly (${error.message}), session.deleted is not watched until restart`)
      }
    })()

    /**
     * Снять сигнал остановки и выйти. Привязки НЕ снимаются и слоты НЕ
     * отпускаются: выгрузка случается и на каждом горячем сейве файла плагина,
     * а не только при закрытии OpenCode, и выбросила бы живую сессию из
     * чата. При настоящем закрытии процесс умирает раньше, чем cleanup
     * исполнится, — страховкой остаётся счёт молчания брокера.
     *
     * Из списка доставщиков убирается функция этой копии: если она была
     * последней, хвост списка перейдёт к выжившему экземпляру, и конверты
     * не уйдут в мёртвый ctx.
     */
    return async () => {
      controller.abort()
      const deliverIndex = state.deliverers.indexOf(myDeliver)
      if (deliverIndex >= 0) state.deliverers.splice(deliverIndex, 1)
      state.instances -= 1
      if (state.instances > 0) return
      state.stopped = true
      for (const bound of state.bindings.values()) bound.abort?.abort()
      // Подождать выхода циклов опроса, чтобы следующая загрузка не делила
      // брокера с умирающими циклами из прежней жизни плагина.
      const deadline = Date.now() + 2_000
      while (
        Date.now() < deadline &&
        [...state.bindings.values()].some((bound) => bound.looping)
      ) {
        await sleep(5)
      }
    }
  },
}
