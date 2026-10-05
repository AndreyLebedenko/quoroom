# Bugreport: the registration token from `continuwuity.toml` does not work for the first account

**Detected at:** `4047d6b` (branch `task/local-installers-06-server-install`, live
check in the task 04 lab, 2026-10-04)
**Status:** fixed by task local-installers-08 (2026-10-04): `docs/INSTALL.md`
steps 1.5 and 5.4 and the comment in
`docker/continuwuity/continuwuity.toml.example` now say that the first account
must use the token the server prints and that the configured one works from the
second account on. Moved to `closed/` with that change.

## What the human sees

`docs/INSTALL.md` step 3a says: put your own string into `registration_token` in
`docker/continuwuity/continuwuity.toml`, then use that same string in step 5 for
each of the three accounts. Doing exactly that, against the image the compose file
pulls today (`ghcr.io/continuwuity/continuwuity:latest`, which reports itself as
conduwuit 26.9.1), every registration is refused:

```
Регистрация не удалась: 401 {"errcode":"M_FORBIDDEN","error":"Invalid registration token"}
```

`docker/continuwuity/continuwuity.toml.example` repeats the same instruction in
its comment, so a reader has no reason to doubt it.

## Symptoms and cause

The server reads the mounted file - proven twice: an invalid TOML in it stops the
container with a parse error naming `/etc/continuwuity/continuwuity.toml`, and
`allow_registration = false` in it does close registration. But the configured
`registration_token` is not what the server compares against on a fresh database.

At every start with registration enabled the server prints its own token:

```
Open your Matrix client of choice and register an account on agentschat.local
using the registration token <issued-token> . Pick your own username and password!
The registration token you set in your configuration will not function until you
create an account using the token above.
```

A different token is printed at every restart, and each is good only until it is
used, so the values seen during the lab run are written here as `<issued-token>`
and are not reproduced anywhere. Observed sequence in the lab:

1. restart with `allow_registration = true` and a generated `registration_token`
   in the file - the configured token is refused;
2. register the first account with the token from the log - succeeds;
3. register a second account with the configured token - succeeds.

So on a fresh database the first account has to use the server-issued token, and
only then does the configured one start working. Nothing in the repository says
this: not the example file, not `docs/INSTALL.md`, not the compose comments.

The same check found a second gap in the same area, which is only a wording
matter: with registration closed, `GET /_matrix/client/v3/register/available`
still answers `{"available": true}` and the UIA flow list still advertises
`m.login.registration_token`. The only honest signal that registration is closed
is a registration attempt refused with `M_FORBIDDEN` "This server is not
accepting registrations at this time."

## Resolution

Task 06's design reads the server-issued token from `docker compose
logs continuwuity` and uses it for the first account, then keeps using the
configured token; that path was verified in the lab on 2026-10-04, Ubuntu 24.04
container, dind engine, conduwuit 26.9.1. Task 08 closed the documentation gap:
`docs/INSTALL.md` states the first-account behaviour in the one-command section
(1.5) and in the manual path (5.4, with the exact `docker compose logs` command
for the human), the example file repeats it next to `registration_token`, and the
manual registration step (5.6) shows the log token for the first account and the
configured one for the second and third. The second finding of that check -
`/register/available` answering `{"available": true}` on a closed server - is
now stated in `docs/INSTALL.md` 1.5: the only honest signal that registration is
closed is a registration attempt refused with `M_FORBIDDEN`.

## Future considerations

- The installer's step reads the log line rather than assuming a key name, so if
  the image changes this behaviour again it fails loudly instead of silently.
  The manual path depends on the human reading the same line.
- If a future Continuwuity accepts the configured token first, the
  documentation and the installer still hold: the installer reads the log only
  after the configured token has been refused.
- Anyone who followed the old instructions on an already set-up machine never
  noticed, because after the first account the configured token works. That is
  why the owner's live stack looks healthy.
