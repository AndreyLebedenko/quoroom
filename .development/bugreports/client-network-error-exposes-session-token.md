# Client network-error text can expose the session token

**Detected:** 2026-10-06.
**Candidate commit:** 9744e12 with the local broker access-log fix.
**Status:** Open; separate from the broker access-log prerequisite.

## Symptoms and evidence

An isolated request to an unavailable loopback endpoint used a synthetic token.
The resulting requests.ConnectTimeout exception contained that token. Only the
exception type and a boolean presence check were printed; no real credential
was used. The initial probe command had a shell-quoting SyntaxError before any
request ran; the corrected probe supplied Python source through stdin.

client.py passes requests exceptions to human-facing text in wait, inbox and
ask. Its authenticated GET URLs contain token query parameters. Therefore an
unavailable broker can disclose the session credential in the client output.
The client-side rendering itself has not been exercised with a real token or
an outage in this assignment. Successful responses do not exercise this path.

## Suspected current cause

The client interpolates the complete exception into translated messages.
requests includes the request URL in its network exceptions. Selecting a safe
server access logger does not change these client exceptions.

## Temporary decision

Keep the authorized production change limited to the broker access logger.
Record this separate error-path finding rather than silently expanding that
fix into client error handling. Continue the successful-response regression;
do not induce a broker outage. Log out the task sessions before stopping the
broker. A runtime infrastructure failure still requires stopping the task.

## Future considerations and boundaries

Handle authenticated-request diagnostics without rendering query credentials,
while preserving the useful endpoint and failure category. Cover wait, inbox
and ask with synthetic credential tests and both client languages. Do not
change the authentication protocol, grant Matrix tokens to sessions, clean
historical logs, or rotate existing credentials as part of this fix.
