"""Тесты сервера морского боя: протокол, правила, изоляция поля противника."""

import json
import unittest

import main
from main import Game, GameError, random_fleet, validate_fleet


def classic_fleet():
    """Валидная расстановка: 1×4, 2×3, 3×2, 4×1, без касаний."""
    return [[{"x": x, "y": 0} for x in range(4)],
            [{"x": x, "y": 5} for x in range(3)],
            [{"x": x, "y": 9} for x in range(3)],
            [{"x": 6, "y": 5}, {"x": 7, "y": 5}],
            [{"x": 6, "y": 7}, {"x": 7, "y": 7}],
            [{"x": 9, "y": 8}, {"x": 9, "y": 9}],
            [{"x": 8, "y": 2}], [{"x": 5, "y": 9}],
            [{"x": 0, "y": 7}], [{"x": 5, "y": 0}]]


class RandomFleetTests(unittest.TestCase):
    def test_fleet_shape(self):
        board, ships = random_fleet()
        self.assertEqual(sorted(len(s) for s in ships), sorted(main.SHIP_FLEET))
        cells = [c for s in ships for c in s]
        self.assertEqual(len(set(cells)), sum(main.SHIP_FLEET))

    def test_no_touching(self):
        board, ships = random_fleet()
        for i, a in enumerate(ships):
            for b in ships[i + 1:]:
                for ax, ay in a:
                    for bx, by in b:
                        self.assertGreater(max(abs(ax - bx), abs(ay - by)), 1)


class ValidateFleetTests(unittest.TestCase):
    def test_valid_manual(self):
        board, norm = validate_fleet(classic_fleet())
        self.assertEqual(len(norm), 10)
        self.assertEqual(sorted(len(s) for s in norm), sorted(main.SHIP_FLEET))

    def test_wrong_count_rejected(self):
        with self.assertRaises(GameError):
            validate_fleet(classic_fleet()[:9])

    def test_wrong_sizes_rejected(self):
        fleet = classic_fleet()
        fleet[3] = [{"x": 6, "y": 5}]
        with self.assertRaises(GameError):
            validate_fleet(fleet)

    def test_diagonal_rejected(self):
        with self.assertRaises(GameError):
            validate_fleet([[{"x": 0, "y": 0}, {"x": 1, "y": 1}]] + classic_fleet()[1:])

    def test_touching_rejected(self):
        fleet = classic_fleet()
        fleet[6] = [{"x": 4, "y": 0}]
        with self.assertRaises(GameError):
            validate_fleet(fleet)

    def test_out_of_board_rejected(self):
        fleet = classic_fleet()
        fleet[9] = [{"x": 10, "y": 0}]
        with self.assertRaises(GameError):
            validate_fleet(fleet)


class GameFlowTests(unittest.TestCase):
    def setUp(self):
        self.game = Game()
        self.a = self.game.add_player()
        self.b = self.game.add_player()
        self.a.board, self.a.ships = random_fleet()
        self.b.board, self.b.ships = validate_fleet(classic_fleet())
        self.game.turn = 0

    def test_state_hides_enemy_board(self):
        st = self.game.state_for(self.a.id)
        board_json = json.dumps(st["board"])
        self.assertNotIn(json.dumps([{"x": 0, "y": 5}, {"x": 1, "y": 5}, {"x": 2, "y": 5}]),
                         board_json)
        self.assertTrue(all(c in (main.UNKNOWN, main.MISS, main.HIT, main.SUNK)
                            for row in st["enemy_view"] for c in row))
        self.assertTrue(all(c in (main.EMPTY, main.SHIP, main.HIT, main.SUNK, main.MISS)
                            for row in st["board"] for c in row))

    def test_fire_requires_turn(self):
        with self.assertRaises(GameError) as ctx:
            self.game.fire(self.b.id, 0, 0)
        self.assertEqual(ctx.exception.status, 409)

    def test_unknown_player_rejected(self):
        with self.assertRaises(GameError) as ctx:
            self.game.state_for("никто")
        self.assertEqual(ctx.exception.status, 403)

    def test_miss_passes_turn(self):
        spot = next((x, y) for y in range(10) for x in range(10)
                    if self.b.board[y][x] == main.EMPTY)
        resp = self.game.fire(self.a.id, *spot)
        self.assertEqual(resp["result"], "miss")
        self.assertEqual(self.game.turn, 1)
        self.assertFalse(resp["your_turn"])
        self.assertIsNone(resp["sunk_ship"])

    def test_hit_keeps_turn(self):
        spot = self.b.ships[0][0]
        resp = self.game.fire(self.a.id, *spot)
        self.assertIn(resp["result"], ("hit", "sunk"))
        self.assertEqual(self.game.turn, 0)
        self.assertTrue(resp["your_turn"])

    def test_double_fire_rejected(self):
        spot = next((x, y) for y in range(10) for x in range(10)
                    if self.b.board[y][x] == main.EMPTY)
        self.game.fire(self.a.id, *spot)
        self.game.turn = 0
        with self.assertRaises(GameError) as ctx:
            self.game.fire(self.a.id, *spot)
        self.assertEqual(ctx.exception.status, 400)

    def test_fire_out_of_board_rejected(self):
        with self.assertRaises(GameError) as ctx:
            self.game.fire(self.a.id, 10, 0)
        self.assertEqual(ctx.exception.status, 400)

    def test_cannot_fire_before_two_players(self):
        g = Game()
        a = g.add_player()
        with self.assertRaises(GameError):
            g.fire(a.id, 0, 0)

    def test_place_locked_after_first_shot(self):
        spot = next((x, y) for y in range(10) for x in range(10)
                    if self.b.board[y][x] == main.EMPTY)
        self.game.fire(self.a.id, *spot)
        with self.assertRaises(GameError):
            self.game.place(self.b.id, classic_fleet())

    def test_sunk_reports_ship(self):
        resp = self.game.fire(self.a.id, 8, 2)
        self.assertEqual(resp["result"], "sunk")
        self.assertEqual(resp["sunk_ship"], {"size": 1, "cells": [{"x": 8, "y": 2}]})
        st = self.game.state_for(self.a.id)
        self.assertIn(1, st["enemy_sunk"])
        self.assertEqual(st["enemy_view"][2][8], main.SUNK)
        # Ореол потопленного не раскрыт: соседние клетки остались unknown.
        self.assertEqual(st["enemy_view"][1][8], main.UNKNOWN)

    def test_hit_not_sunk_no_cells(self):
        resp = self.game.fire(self.a.id, 0, 0)
        self.assertEqual(resp["result"], "hit")
        self.assertIsNone(resp["sunk_ship"])
        st = self.game.state_for(self.a.id)
        self.assertEqual(st["enemy_view"][0][0], main.HIT)
        self.assertEqual(st["enemy_view"][1][0], main.UNKNOWN)

    def test_win_ends_game(self):
        resp = None
        for x in range(4):
            resp = self.game.fire(self.a.id, x, 0)
        for x in range(3):
            resp = self.game.fire(self.a.id, x, 5)
            resp = self.game.fire(self.a.id, x, 9)
        for x, y in [(6, 5), (7, 5), (6, 7), (7, 7), (9, 8), (9, 9),
                     (8, 2), (5, 9), (0, 7), (5, 0)]:
            resp = self.game.fire(self.a.id, x, y)
        self.assertTrue(resp["game_over"])
        self.assertEqual(resp["winner"], self.a.id)
        self.assertEqual(self.game.phase, "finished")
        self.assertEqual(sorted(self.game.state_for(self.a.id)["enemy_sunk"]),
                         sorted(main.SHIP_FLEET))
        # После конца матча выстрелы запрещены.
        with self.assertRaises(GameError):
            self.game.fire(self.a.id, 4, 4)

    def test_winner_only_by_sinking_all(self):
        resp = self.game.fire(self.a.id, 5, 0)
        self.assertFalse(resp["game_over"])
        self.assertIsNone(resp["winner"])
        self.assertEqual(self.game.phase, "playing")


if __name__ == "__main__":
    unittest.main()