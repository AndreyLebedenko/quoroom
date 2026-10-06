# Battleship: the server

The authoritative game server. Keeps both boards in memory, takes shots and
returns the result, not the state. The opponent's board is never given to the
client, in any form, not even after the game ends.

Run:

```
python demo/battleship/server/main.py --port 8000
```

The client opens at http://127.0.0.1:8000/ - the server serves the static files
from `demo/battleship/web/`. It can also be opened as a file (`web/index.html`):
CORS is allowed for any origin on `/api/*`.

A server restart clears the game: the state is entirely in memory.

## Protocol (HTTP + JSON)

Entry point: `POST /api/game` - create a match or join a waiting one. One match
at a time: a free slot exists only for a game in the `waiting` phase.

All coordinates are `x`, `y` from 0 to 9 (x is the column, y is the row).

### POST /api/game
The body is empty (`{}`). The answer:

```json
{"game_id": "...", "player_id": "...", "phase": "waiting", "your_turn": null}
```

The second one to connect joins the same match; who moves first is decided by
the server with a coin toss (`your_turn: true/false` at the start).

### GET /api/game/{game_id}/state?player_id={player_id}
The full state for one player:

```json
{
  "phase": "waiting | playing | finished",
  "opponent_connected": true,
  "your_turn": true,
  "board": [["ship", "miss", "..."]],
  "enemy_view": [["unknown", "miss", "..."]],
  "enemy_sunk": [3],
  "my_sunk": [],
  "game_over": false,
  "winner": null
}
```

- `board` - only YOUR board: `empty | ship | hit | sunk | miss`.
- `enemy_view` - what you can see of the opponent's board: `unknown | miss | hit
  | sunk`. The opponent's ships are not revealed; `sunk` appears only on the
  cells of a sunk ship, and those were known as hits anyway.
- `winner` - the `player_id` of the winner or `null`. The game cannot end in a
  draw: the turns are strictly alternating.

### POST /api/game/{game_id}/place
`{"player_id": "...", "ships": [[{"x":0,"y":0},{"x":1,"y":0}], ...]}`

The placement of your own board. `ships` may be omitted - the server places them
randomly. The fleet: 1x4, 2x3, 3x2, 4x1, the ships do not touch even at the
corners. You may place again until the first shot of the match is made.

### POST /api/game/{game_id}/fire
`{"player_id": "...", "x": 3, "y": 7}`

The answer:

```json
{"result": "miss | hit | sunk", "sunk_ship": {"size": 3, "cells": [...]},
 "game_over": false, "winner": null, "your_turn": true}
```

`sunk_ship` is present only on `result: "sunk"` and names the size and the cells
of the sunk ship - that is enough to mark the halo of a sunk ship honestly and
to count the ships that are left.

The alternating rule: a hit - you shoot again, a miss - the turn passes.

Errors: JSON `{"error": "text"}` with status 400 (an invalid shot), 403 (a foreign
player_id), 404 (no such match), 409 (not your turn, the match is full, the
placement is locked).

The client learns about the opponent's move by polling `state` (once a second is
enough).
