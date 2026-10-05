# Bug report: the plugin does not strip a trailing slash from AGENTSCHAT_URL

**Detected at:** a1bf72ad075158ceff10ba032fff43da71070de3
**Status:** reported, not fixed, fix deferred.

## Symptom

`AGENTSCHAT_URL` set with a trailing slash, for example
`http://127.0.0.1:8770/`:

- the CLI works: it drops the trailing slash, so it requests
  `http://127.0.0.1:8770/status`;
- the OpenCode plugin does not: it requests
  `http://127.0.0.1:8770//wait?agent=...` with a doubled slash.

What the human sees when only the plugin is on the path: the plugin logs
repeatedly that polling failed, and no incoming message reaches the session,
while `agentschat status` from the same shell answers normally. Nothing points
at the slash.

Not observed live. The doubled slash is read off the plugin source, and the
plugin's own test sets `AGENTSCHAT_URL` without a trailing slash, so no
automated test covers this form. Whether the broker answers the doubled path or
404s it is not recorded here.

## Suspected cause

`bridge/sessionchat/kit/opencode/plugins/agentschat.js` reads the address as

    const BROKER = process.env.AGENTSCHAT_URL || "http://127.0.0.1:8770"

and builds every request path as `${BROKER}/wait?...`. There is no
normalization, so whatever the operator wrote is concatenated literally. The
CLI now ends up with `.rstrip("/")` in `client.base()`, so the two read the
same variable with different rules.

The defaults do not diverge: they are the same string, and
`test_the_default_is_the_same_url_the_plugin_falls_back_to` keeps them that
way. Only an explicitly written trailing slash separates them.

## Temporary decision

Leave it, and report it. Fixed in neither consumer now, because the task card
that owns this change excludes plugin behavior: `task-local-installers-01` says
"No broker change, no plugin behavior change", and the plugin source lives in
the client kit that the card does not touch.

Rejected nearby options:

- Strip the slash in the plugin. Correct, but a plugin behavior change, outside
  the card.
- Reject or normalize the value in the CLI and warn about the plugin. The story
  forbids code that refuses a broker address, and a CLI-side warning cannot
  reach the plugin anyway.
- Document "write the variable without a trailing slash". True, but it leaves
  the operator with a silent trap, and installation docs belong to task 08.

## Future considerations

- A follow-up card should strip the trailing slash where the plugin reads the
  variable, the same way the CLI does, and add a `node --test` case that sets
  `AGENTSCHAT_URL` with a trailing slash and asserts the polled URL has no
  doubled slash. That test is the missing automated coverage on the plugin
  side.
- Whoever writes the participant installer (task 05) sets `AGENTSCHAT_URL` for
  both the CLI and the plugin from one value. Until the plugin normalizes, a
  value ending in a slash produces a half-working installation: the CLI
  connects, the plugin does not. Task 05 can dodge it by writing the value
  without a trailing slash, and that is worth saying out loud there.

## Boundaries

- No change to the plugin, the broker, or the protocol.
- No test that rejects a non-local address.