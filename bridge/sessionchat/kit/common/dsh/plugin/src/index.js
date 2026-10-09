import fs from "node:fs"
import os from "node:os"
import path from "node:path"
import { spawn } from "node:child_process"
import { randomUUID } from "node:crypto"

const RESULT_PREFIX = "AGENTSCHAT-RESULT "
const AGENT_NAME = /^[A-Za-z0-9][\w-]*$/
const CODE_NAME = /^[a-z][a-z0-9_]*$/
const CMD_SHIM = /\.(cmd|bat)$/i
const PATHED = /[/\\]/
const PATHEXT_DEFAULT = ".COM;.EXE;.BAT;.CMD"

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

function positiveInt(value, name) {
  const n = Number(value)
  if (!Number.isInteger(n) || n <= 0) {
    throw new TypeError(`${name} must be a positive integer, got ${String(value)}`)
  }
  return n
}

export function resolveConfig(config = {}) {
  const env = (name) => {
    const value = process.env[name]
    return value === undefined || value === "" ? null : value
  }
  const url = env("AGENTSCHAT_URL") || config.brokerUrl || "http://127.0.0.1:8770"
  let parsed
  try {
    parsed = new URL(url)
  } catch {
    throw new TypeError(`brokerUrl must be a URL, got ${String(url)}`)
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new TypeError(`brokerUrl must be http or https, got ${String(url)}`)
  }
  const cli = env("AGENTSCHAT_BIN") || config.cli || "agentschat"
  if (typeof cli !== "string" || cli.trim() === "") {
    throw new TypeError("cli must be a non-empty string")
  }
  return {
    brokerUrl: parsed.toString().replace(/\/$/, ""),
    cli,
    retryMs: positiveInt(env("AGENTSCHAT_RETRY_MS") ?? config.retryMs ?? 3000, "retryMs"),
    tokenlessLimit: positiveInt(
      env("AGENTSCHAT_TOKENLESS_LIMIT") ?? config.tokenlessLimit ?? 20,
      "tokenlessLimit",
    ),
    loginTimeoutMs: positiveInt(config.loginTimeoutMs ?? 30000, "loginTimeoutMs"),
    logoutTimeoutMs: positiveInt(config.logoutTimeoutMs ?? 15000, "logoutTimeoutMs"),
    waitTimeoutMs: positiveInt(config.waitTimeoutMs ?? 70000, "waitTimeoutMs"),
  }
}

function shared() {
  if (!globalThis.__dshAgentschat) {
    globalThis.__dshAgentschat = {
      bindings: new Map(),
      instances: 0,
      stopped: false,
    }
  }
  return globalThis.__dshAgentschat
}

function storeDir() {
  return path.join(os.homedir(), ".agentschat")
}

function brokerToken(name) {
  try {
    const data = JSON.parse(fs.readFileSync(path.join(storeDir(), `${name}.json`), "utf8"))
    return typeof data.token === "string" ? data.token : null
  } catch {
    return null
  }
}

function note(message) {
  const line = `${new Date().toISOString()} ${message}\n`
  try {
    fs.mkdirSync(storeDir(), { recursive: true })
    fs.appendFileSync(path.join(storeDir(), "dsh-plugin.log"), line, "utf8")
  } catch {
    return
  }
}

function findOnPath(name) {
  const extensions = String(process.env.PATHEXT || PATHEXT_DEFAULT).split(";")
  for (const dir of String(process.env.PATH || "").split(path.delimiter)) {
    if (!dir) continue
    for (const ext of extensions) {
      const candidate = path.join(dir, `${name}${ext}`)
      try {
        if (fs.statSync(candidate).isFile()) return candidate
      } catch {
        continue
      }
    }
  }
  return null
}

const needsQuotes = (value) => value === "" || /[\s&()^%!"<>|]/.test(value)
const quote = (value) => (needsQuotes(value) ? `"${value}"` : value)

function spawnCli(cli, args, options) {
  if (process.platform !== "win32") return spawn(cli, args, options)
  let command = cli
  if (!PATHED.test(cli) && !CMD_SHIM.test(cli)) {
    command = findOnPath(cli) ?? cli
  }
  if (!CMD_SHIM.test(command)) return spawn(command, args, options)
  const line = [command, ...args].map(quote).join(" ")
  return spawn("cmd.exe", ["/d", "/s", "/c", `"${line}"`], {
    ...options,
    windowsVerbatimArguments: true,
  })
}

function runCli(cli, args, timeoutMs) {
  return new Promise((resolve) => {
    let out = ""
    let settled = false
    let timer
    const finish = (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ code, out })
    }
    const child = spawnCli(cli, args, { windowsHide: true })
    timer = setTimeout(() => {
      try {
        child.kill()
      } catch {
        finish(-1)
      }
    }, timeoutMs)
    child.stdout.on("data", (chunk) => (out += chunk))
    child.stderr.on("data", (chunk) => (out += chunk))
    child.on("close", (code) => finish(code ?? 1))
    child.on("error", () => finish(-1))
  })
}

function lastResultLine(text) {
  const lines = text.split(/\r?\n/).filter((line) => line.startsWith(RESULT_PREFIX))
  return lines.length > 0 ? lines[lines.length - 1] : null
}

function lastPlainLine(text) {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line !== "" && !line.startsWith(RESULT_PREFIX))
  return lines.length > 0 ? lines[lines.length - 1] : ""
}

function readResult(text, kind) {
  const line = lastResultLine(text)
  if (line === null) {
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
    const code =
      typeof result.code === "string" && CODE_NAME.test(result.code) ? result.code : "unknown"
    return { ok: false, code, message: lastPlainLine(text) }
  }
  if (result.ok !== true) {
    note(`${kind}: result line has no boolean ok, nothing changed`)
    return null
  }
  if (typeof result.agent !== "string" || !AGENT_NAME.test(result.agent)) {
    note(`${kind}: result line names no valid agent, nothing changed`)
    return null
  }
  return { ok: true, agent: result.agent, reconnected: result.reconnected === true }
}

async function readCliLogin(args, resolved) {
  const { out } = await runCli(resolved.cli, args, resolved.loginTimeoutMs)
  const result = readResult(out, "login")
  if (result === null) return null
  if (!result.ok) {
    note(`login refused for agent ${result.agent ?? "?"}, code ${result.code}`)
    return result
  }
  note(`login: agent ${result.agent} connected${result.reconnected ? " (reconnected)" : ""}`)
  return result
}

async function login(name, label, resolved) {
  const base = ["login", "--agent", name]
  if (label) base.push("--label", label)
  const first = await readCliLogin(base, resolved)
  if (first !== null && !first.ok && first.code === "slot_taken" && brokerToken(name) !== null) {
    const retry = await readCliLogin([...base, "--reconnect"], resolved)
    if (retry !== null) return retry
  }
  return first
}

async function logoutCli(name, resolved) {
  const { out } = await runCli(resolved.cli, ["logout", "--agent", name], resolved.logoutTimeoutMs)
  const result = readResult(out, "logout")
  if (result === null) return null
  if (!result.ok) {
    note(`logout refused for agent ${name}, code ${result.code}`)
    return result
  }
  note(`logout: agent ${name} disconnected`)
  return result
}

async function poll(name, token, resolved) {
  const url = `${resolved.brokerUrl}/wait?agent=${encodeURIComponent(name)}&token=${encodeURIComponent(token)}`
  const response = await fetch(url, { signal: AbortSignal.timeout(resolved.waitTimeoutMs) })
  if (response.status === 204) return null
  if (response.status === 409) {
    const body = (await response.text()).trim()
    note(`${name}: the broker no longer knows this session: ${body}`)
    shared().bindings.delete(name)
    return null
  }
  if (!response.ok) throw new Error(`broker answered ${response.status}`)
  const data = await response.json()
  const rendered = typeof data.rendered === "string" ? data.rendered : ""
  if (!rendered) throw new Error("envelope without rendered text")
  return rendered
}

function deliver(bound, rendered) {
  bound.agent.followup({
    id: randomUUID(),
    role: "user",
    content: [{ type: "text", text: rendered }],
    source: { kind: "plugin", plugin: "agentschat" },
  })
}

async function loop(bound, resolved) {
  const state = shared()
  bound.looping = true
  while (!state.stopped && state.bindings.get(bound.name) === bound) {
    const token = brokerToken(bound.name)
    if (token === null) {
      bound.tokenless += 1
      if (bound.tokenless === 1) note(`${bound.name}: token not found, waiting`)
      if (bound.tokenless > resolved.tokenlessLimit) {
        note(`${bound.name}: token still missing, dropping the binding, a new login is needed`)
        state.bindings.delete(bound.name)
        break
      }
      await sleep(resolved.retryMs)
      continue
    }
    bound.tokenless = 0
    let envelope
    try {
      envelope = await poll(bound.name, token, resolved)
    } catch (error) {
      note(`${bound.name}: poll failed (${error.message}), retry in ${resolved.retryMs}ms`)
      await sleep(resolved.retryMs)
      continue
    }
    if (envelope === null) continue
    if (state.bindings.get(bound.name) !== bound) continue
    try {
      deliver(bound, envelope)
      note(`${bound.name}: message delivered`)
    } catch (error) {
      note(`${bound.name}: could not deliver the message: ${error.message}`)
      await sleep(resolved.retryMs)
    }
  }
  bound.looping = false
  note(`${bound.name}: polling stopped`)
}

function bind(name, agent, resolved) {
  const state = shared()
  const bound = { name, agent, looping: false, tokenless: 0 }
  state.bindings.set(name, bound)
  note(`${name}: agent bound, listening to the broker`)
  loop(bound, resolved)
}

function unbind(name) {
  const state = shared()
  const bound = state.bindings.get(name)
  state.bindings.delete(name)
  return bound
}

async function releaseSlot(name, why, resolved) {
  const bound = unbind(name)
  if (!bound) return
  note(`${name}: slot released (${why})`)
  const outcome = await logoutCli(name, resolved)
  if (outcome === null || !outcome.ok) {
    note(`${name}: best-effort logout not confirmed (${why})`)
  }
}

function parseInput(rawInput) {
  const text = typeof rawInput === "string" ? rawInput : ""
  const tokens = text.trim().split(/\s+/).filter((t) => t !== "")
  if (tokens.length === 0) return null
  let name = null
  let label = null
  const rest = []
  for (let i = 0; i < tokens.length; i += 1) {
    if (tokens[i] === "--agent" && i + 1 < tokens.length) {
      name = tokens[i + 1]
      i += 1
    } else if (tokens[i] === "--label" && i + 1 < tokens.length) {
      label = tokens[i + 1]
      i += 1
    } else {
      rest.push(tokens[i])
    }
  }
  if (name === null && rest.length > 0) name = rest.shift()
  if (name === null) return null
  if (!AGENT_NAME.test(name)) return null
  if (label === null && rest.length > 0) label = rest.join(" ")
  return { name, label }
}

export const inject = ["commands"]

export function apply(ctx, config = {}) {
  const resolved = resolveConfig(config)
  const state = shared()
  state.instances += 1
  state.stopped = false
  note(`plugin loaded, broker ${resolved.brokerUrl}`)

  const offLogin = ctx.commands.register({
    name: "chatlogin",
    description: "Join the shared room as a named participant",
    input: { hint: "<name> [label]" },
    handler: async (invocation) => {
      const parsed = parseInput(invocation.rawInput)
      if (parsed === null) return { kind: "error", text: "usage: /chatlogin <name> [label]" }
      const { name, label } = parsed
      if (state.bindings.has(name)) {
        return { kind: "error", text: `session ${name} is already connected in this process` }
      }
      const outcome = await login(name, label, resolved)
      if (outcome === null) {
        return { kind: "error", text: "login did not confirm; nothing changed" }
      }
      if (!outcome.ok) {
        return {
          kind: "error",
          text: `login refused, code ${outcome.code}${outcome.message ? `: ${outcome.message}` : ""}`,
        }
      }
      bind(outcome.agent, invocation.agent, resolved)
      return {
        kind: "success",
        text: outcome.reconnected
          ? `session ${outcome.agent} reconnected to the room`
          : `session ${outcome.agent} is connected to the room`,
      }
    },
  })

  const offLogout = ctx.commands.register({
    name: "chatlogout",
    description: "Leave the shared room and release the participant slot",
    input: { hint: "[name]" },
    handler: async (invocation) => {
      const text = (typeof invocation.rawInput === "string" ? invocation.rawInput : "").trim()
      let name = null
      if (text === "") {
        for (const [candidate, bound] of state.bindings) {
          if (bound.agent === invocation.agent) {
            name = candidate
            break
          }
        }
      } else {
        const parsed = parseInput(invocation.rawInput)
        if (parsed === null) return { kind: "error", text: "usage: /chatlogout [name]" }
        name = parsed.name
      }
      if (name === null) {
        return { kind: "error", text: "no session of yours is connected; give the agent name to remove" }
      }
      const outcome = await logoutCli(name, resolved)
      if (outcome === null) {
        return { kind: "error", text: "logout produced no result line; the binding is kept" }
      }
      if (!outcome.ok) {
        return {
          kind: "error",
          text: `logout refused, code ${outcome.code}${outcome.message ? `: ${outcome.message}` : ""}`,
        }
      }
      unbind(name)
      return { kind: "success", text: `session ${name} is disconnected from the room` }
    },
  })

  const offDisposed = ctx.on("agent/disposed", (payload) => {
    try {
      for (const [name, bound] of state.bindings) {
        if (bound.agent === payload.agent) {
          void releaseSlot(name, "agent disposed", resolved)
        }
      }
    } catch (error) {
      note(`agent/disposed handling failed: ${error.message}`)
    }
  })

  return () => {
    offLogin()
    offLogout()
    offDisposed()
    state.instances -= 1
    if (state.instances > 0) return
    state.stopped = true
    for (const name of [...state.bindings.keys()]) {
      void releaseSlot(name, "plugin unloading", resolved)
    }
    state.bindings.clear()
  }
}
