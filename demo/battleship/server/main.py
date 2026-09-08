"""Морской бой: авторитетный сервер. Поле противника клиенту не отдаётся."""

import json
import random
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

SHIP_FLEET = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]
BOARD_SIZE = 10

EMPTY, SHIP, HIT, SUNK, MISS = "empty", "ship", "hit", "sunk", "miss"
UNKNOWN = "unknown"

LOCK = threading.Lock()


class GameError(Exception):
    def __init__(self, message, status=409):
        super().__init__(message)
        self.status = status


def neighbors(x, y):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            nx, ny = x + dx, y + dy
            if 0 <= nx < BOARD_SIZE and 0 <= ny < BOARD_SIZE:
                yield nx, ny


def random_fleet():
    board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    ships = []
    for size in SHIP_FLEET:
        for _attempt in range(1000):
            horiz = random.random() < 0.5
            x = random.randint(0, BOARD_SIZE - (size if horiz else 1))
            y = random.randint(0, BOARD_SIZE - (1 if horiz else size))
            cells = [(x + i, y) if horiz else (x, y + i) for i in range(size)]
            if all(board[ny][nx] == EMPTY for cx, cy in cells for nx, ny in neighbors(cx, cy)):
                for cx, cy in cells:
                    board[cy][cx] = SHIP
                ships.append(cells)
                break
        else:
            raise RuntimeError("не удалось расставить флот")
    return board, ships


def validate_fleet(ships):
    if not isinstance(ships, list) or len(ships) != len(SHIP_FLEET):
        raise GameError("флот должен быть списком из 10 кораблей", 400)
    sizes = sorted(len(s) for s in ships)
    if sizes != sorted(SHIP_FLEET):
        raise GameError("неверный состав флота", 400)
    board = [[EMPTY] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    norm = []
    for ship in ships:
        cells = []
        for cell in ship:
            if not isinstance(cell, dict) or not {"x", "y"} <= set(cell):
                raise GameError("клетка корабля: {x, y}", 400)
            x, y = cell["x"], cell["y"]
            if not (isinstance(x, int) and isinstance(y, int)
                    and 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE):
                raise GameError("координаты вне поля", 400)
            cells.append((x, y))
        if len(set(cells)) != len(cells):
            raise GameError("в корабле повторяются клетки", 400)
        cells.sort()
        straight = all(
            (c[0] - cells[0][0], c[1] - cells[0][1]) == (i, 0)
            or (c[0] - cells[0][0], c[1] - cells[0][1]) == (0, i)
            for i, c in enumerate(cells)
        )
        if not straight:
            raise GameError("корабль должен быть прямой линией", 400)
        for x, y in cells:
            if any(board[ny][nx] == SHIP for nx, ny in neighbors(x, y)):
                raise GameError("корабли не должны касаться даже углами", 400)
        for x, y in cells:
            board[y][x] = SHIP
        norm.append(cells)
    return board, norm


class Player:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.board = None
        self.ships = None
        self.connected = True


class Game:
    def __init__(self):
        self.id = uuid.uuid4().hex
        self.players = []
        self.phase = "waiting"
        self.turn = None
        self.shots = {0: set(), 1: set()}
        self.winner = None
        self.shots_fired = 0

    def add_player(self):
        with LOCK:
            if len(self.players) >= 2:
                raise GameError("в этом матче уже двое игроков")
            player = Player()
            player.board, player.ships = random_fleet()
            self.players.append(player)
            if len(self.players) == 2:
                self.phase = "playing"
                self.turn = random.randint(0, 1)
            return player

    def index_of(self, player_id):
        for i, p in enumerate(self.players):
            if p.id == player_id:
                return i
        raise GameError("неизвестный player_id", 403)

    def place(self, player_id, ships=None):
        with LOCK:
            idx = self.index_of(player_id)
            if self.shots_fired > 0:
                raise GameError("расстановка заперта: матч начался")
            if ships is None:
                self.players[idx].board, self.players[idx].ships = random_fleet()
            else:
                self.players[idx].board, self.players[idx].ships = validate_fleet(ships)

    def fire(self, player_id, x, y):
        with LOCK:
            if not (isinstance(x, int) and isinstance(y, int)
                    and 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE):
                raise GameError("координаты вне поля", 400)
            idx = self.index_of(player_id)
            if self.phase != "playing":
                raise GameError("матч не в фазе игры", 409)
            if self.turn != idx:
                raise GameError("не твой ход", 409)
            if (x, y) in self.shots[idx]:
                raise GameError("здесь уже стреляли", 400)
            self.shots[idx].add((x, y))
            self.shots_fired += 1
            enemy = self.players[1 - idx]
            enemy_board = enemy.board
            if enemy_board[y][x] == SHIP:
                enemy_board[y][x] = HIT
                ship = next((s for s in enemy.ships if (x, y) in s), None)
                sunk = ship is not None and all(enemy_board[cy][cx] == HIT for cx, cy in ship)
                if sunk:
                    for cx, cy in ship:
                        enemy_board[cy][cx] = SUNK
                    result, sunk_info = "sunk", {"size": len(ship),
                                                 "cells": [{"x": cx, "y": cy} for cx, cy in ship]}
                    if all(all(enemy_board[cy][cx] == SUNK for cx, cy in s) for s in enemy.ships):
                        self.phase = "finished"
                        self.winner = player_id
                else:
                    result, sunk_info = "hit", None
            else:
                if enemy_board[y][x] == EMPTY:
                    enemy_board[y][x] = MISS
                result, sunk_info = "miss", None
                self.turn = 1 - idx
            return {"result": result, "sunk_ship": sunk_info,
                    "game_over": self.phase == "finished",
                    "winner": self.winner, "your_turn": self.turn == idx and self.phase == "playing"}

    def state_for(self, player_id):
        with LOCK:
            idx = self.index_of(player_id)
            me, enemy = self.players[idx], self.players[1 - idx]
            if self.phase == "waiting":
                return {"phase": self.phase, "opponent_connected": False,
                        "your_turn": None, "board": None, "enemy_view": None,
                        "enemy_sunk": [], "my_sunk": [],
                        "game_over": False, "winner": None}
            enemy_view = [[UNKNOWN] * BOARD_SIZE for _ in range(BOARD_SIZE)]
            for x, y in self.shots[idx]:
                enemy_view[y][x] = enemy.board[y][x] if enemy.board[y][x] in (MISS, HIT, SUNK) else UNKNOWN
            my_sunk = [s for s in me.ships if all(me.board[cy][cx] == SUNK for cx, cy in s)] if me.board else []
            enemy_sunk = []
            if enemy.board is not None:
                for s in enemy.ships:
                    if all(enemy.board[cy][cx] == SUNK for cx, cy in s):
                        enemy_sunk.append(len(s))
            return {"phase": self.phase,
                    "opponent_connected": True,
                    "your_turn": self.turn == idx if self.phase == "playing" else None,
                    "board": [row[:] for row in me.board] if me.board else None,
                    "enemy_view": enemy_view,
                    "enemy_sunk": sorted(enemy_sunk),
                    "my_sunk": [len(s) for s in my_sunk],
                    "game_over": self.phase == "finished",
                    "winner": self.winner}


GAMES = {}


def find_open_game():
    with LOCK:
        for game in GAMES.values():
            if game.phase == "waiting" and len(game.players) < 2:
                return game
        game = Game()
        GAMES[game.id] = game
        return game


class Handler(BaseHTTPRequestHandler):
    server_version = "BattleshipServer/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (ValueError, UnicodeDecodeError):
            raise GameError("тело запроса не JSON", 400)

    def _player_id(self, data=None, query=None):
        pid = (data or {}).get("player_id")
        if pid is None and query:
            (pid,) = query.get("player_id", [None])
        if not pid:
            raise GameError("нет player_id", 400)
        return pid

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            if parsed.path == "/api/game":
                game = find_open_game()
                player = game.add_player()
                self._send(200, {"game_id": game.id, "player_id": player.id,
                                 "phase": game.phase,
                                 "your_turn": game.turn == len(game.players) - 1
                                 if game.phase == "playing" else None})
                return
            parts = parsed.path.strip("/").split("/")
            if (len(parts) == 4 and parts[0] == "api" and parts[1] == "game"
                    and parts[3] == "state"):
                game = GAMES.get(parts[2])
                if game is None:
                    raise GameError("матч не найден", 404)
                self._send(200, game.state_for(self._player_id(query=query)))
                return
            raise GameError("нет такого пути", 404)
        except GameError as e:
            self._send(e.status, {"error": str(e)})

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            data = self._body()
            parts = parsed.path.strip("/").split("/")
            if parsed.path == "/api/game":
                game = find_open_game()
                player = game.add_player()
                self._send(200, {"game_id": game.id, "player_id": player.id,
                                 "phase": game.phase,
                                 "your_turn": game.turn == len(game.players) - 1
                                 if game.phase == "playing" else None})
                return
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "game":
                game = GAMES.get(parts[2])
                if game is None:
                    raise GameError("матч не найден", 404)
                pid = self._player_id(data)
                if parts[3] == "place":
                    game.place(pid, data.get("ships"))
                    self._send(200, {"ok": True})
                    return
                if parts[3] == "fire":
                    self._send(200, game.fire(pid, data.get("x"), data.get("y")))
                    return
            raise GameError("нет такого пути", 404)
        except GameError as e:
            self._send(e.status, {"error": str(e)})


def serve(port=8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Battleship: http://127.0.0.1:{port}/ (static: {WEB_DIR})")
    server.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    serve(parser.parse_args().port)