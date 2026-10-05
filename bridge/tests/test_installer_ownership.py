"""Карточка local-installers-02, гейт 4: удаляет только записанное."""

import unittest
from dataclasses import dataclass
from pathlib import Path

from tests.installer_fakes import (
    FileMarker,
    InstallerTestCase,
    Marker,
    owned_remover,
    recorded,
    role,
)
from sessionchat.installer.confirmation import WORD
from sessionchat.installer.main import CANCELLED, DONE, FAILED, main
from sessionchat.installer.ownership import Entry, Ownership
from sessionchat.installer.roles import Role
from sessionchat.installer.steps import FoundStep, OwnedStep, State


@dataclass
class Owner:
    name: str
    role: str
    kind: str
    target: Path
    log: list[str]
    crash: bool = False

    def check(self, run) -> State:
        return State.DONE if self.target.exists() else State.TODO

    def apply(self, run) -> None:
        run.record(self.role, self.kind, str(self.target))
        self.log.append(f"apply:{self.name}")
        if self.crash:
            raise RuntimeError("убит посреди шага")
        self.target.write_text("создано\n", encoding="utf-8")


class OwnershipRecordTests(InstallerTestCase):
    def ownership(self) -> Ownership:
        return Ownership(self.record("server"))

    def test_a_recorded_resource_survives_a_reload(self):
        ownership = self.ownership()
        ownership.record("file", "C:/Quoroom/bridge/config.yaml")
        ownership.save()
        self.assertEqual(
            Ownership.load(self.record("server")).of_kind("file"),
            ["C:/Quoroom/bridge/config.yaml"],
        )

    def test_an_unrecorded_resource_is_not_owned(self):
        ownership = self.ownership()
        ownership.record("volume", "continuwuity-data")
        self.assertFalse(ownership.owns("volume", "caddy-config"))

    def test_a_resource_without_a_record_file_is_owned_by_nobody(self):
        self.assertEqual(Ownership.load(self.record("server")).entries, [])

    def test_recording_the_same_resource_twice_keeps_one_entry(self):
        ownership = self.ownership()
        ownership.record("volume", "caddy-data")
        ownership.record("volume", "caddy-data")
        self.assertEqual(ownership.entries, [Entry("volume", "caddy-data")])

    def test_of_kind_lists_only_its_kind(self):
        ownership = self.ownership()
        ownership.record("volume", "caddy-data")
        ownership.record("package", "quoroom@uv")
        self.assertEqual(ownership.of_kind("package"), ["quoroom@uv"])

    def test_forgetting_drops_the_resource(self):
        ownership = self.ownership()
        ownership.record("file", "C:/Quoroom/bridge/config.yaml")
        ownership.forget("file", "C:/Quoroom/bridge/config.yaml")
        self.assertFalse(ownership.owns("file", "C:/Quoroom/bridge/config.yaml"))

    def test_the_same_name_under_another_kind_is_a_different_resource(self):
        ownership = self.ownership()
        ownership.record("volume", "state")
        ownership.record("directory", "state")
        ownership.forget("volume", "state")
        self.assertEqual(ownership.entries, [Entry("directory", "state")])

    def test_an_empty_record_deletes_its_file(self):
        ownership = Ownership.load(
            recorded(self.home / "records", "server.json", [("volume", "caddy-data")])
        )
        ownership.save()
        self.assertTrue(self.record("server").is_file())
        ownership.forget("volume", "caddy-data")
        ownership.save()
        self.assertFalse(self.record("server").exists())

    def test_a_path_with_spaces_and_cyrillic_survives_a_reload(self):
        ownership = self.ownership()
        ownership.record("file", "D:\\Мои документы\\Quoroom\\config.yaml")
        ownership.save()
        self.assertEqual(
            Ownership.load(self.record("server")).of_kind("file"),
            ["D:\\Мои документы\\Quoroom\\config.yaml"],
        )

    def test_a_corrupt_record_is_reported_instead_of_crashing(self):
        self.record("server").parent.mkdir(parents=True, exist_ok=True)
        self.record("server").write_text("{не json", encoding="utf-8")
        given = self.boundaries()
        code = main(["--role", "server"], given, (role("server"),))
        self.assertEqual(code, FAILED)
        self.assertIn("подготовка запуска", given.stderr.getvalue())

    def test_a_corrupt_record_does_not_leak_a_traceback(self):
        self.record("server").parent.mkdir(parents=True, exist_ok=True)
        self.record("server").write_text("{не json", encoding="utf-8")
        given = self.boundaries()
        main(["--role", "server"], given, (role("server"),))
        self.assertNotIn("Traceback", given.stderr.getvalue())


class WriteThroughRecordTests(InstallerTestCase):
    def owner(self, crash: bool) -> Owner:
        return Owner(
            "создать конфигурацию",
            "server",
            "config",
            self.home / "config.yaml",
            self.log,
            crash=crash,
        )

    def test_a_resource_recorded_before_a_crash_is_still_owned_afterwards(self):
        given = self.boundaries()
        code = main(
            ["--role", "server"],
            given,
            (role("server", install=(self.owner(True),)),),
        )
        self.assertEqual(code, FAILED)
        self.assertFalse((self.home / "config.yaml").exists())
        self.assertEqual(
            Ownership.load(self.record("server")).of_kind("config"),
            [str(self.home / "config.yaml")],
        )

    def test_a_cancelled_purge_leaves_the_record_byte_identical(self):
        recorded(
            self.home / "records", "server.json", [("volume", "continuwuity-data")]
        )
        before = self.record("server").read_bytes()
        code = main(
            ["--role", "server", "--remove", "--purge"],
            self.boundaries(stdin="нет\n"),
            (role("server", purge=(OwnedStep("удалить тома", "server", "volume"),)),),
        )
        self.assertEqual(code, CANCELLED)
        self.assertEqual(self.record("server").read_bytes(), before)


class ConfirmationWordTests(InstallerTestCase):
    def test_the_word_is_ascii(self):
        self.assertTrue(WORD.isascii())

    def test_the_word_is_purge(self):
        self.assertEqual(WORD, "PURGE")


class PurgeOrderTests(InstallerTestCase):
    def setUp(self):
        super().setUp()
        self.config = self.home / "config.yaml"
        self.config.write_text("sessionchat_port: 8770\n", encoding="utf-8")
        self.hand_made = self.home / "сделано руками.yaml"
        self.hand_made.write_text("keep me\n", encoding="utf-8")
        self.token = self.home / "glm.json"
        self.token.write_text('{"token": "t"}\n', encoding="utf-8")
        recorded(
            self.home / "records",
            "server.json",
            [("config", str(self.config)), ("volume", "continuwuity-data")],
        )
        self.server = role(
            "server",
            remove=(
                owned_remover("убрать конфигурацию", "server", "config", self.log),
            ),
            purge=(
                OwnedStep(
                    "удалить тома",
                    "server",
                    "volume",
                    lambda run, id: self.log.append(f"delete:{id}"),
                ),
            ),
            consequence=lambda targets: "история комнаты исчезнет",
        )

    def participant_role(self):
        def delete(run, id: str) -> None:
            self.log.append(f"delete:{id}")
            Path(id).unlink()

        return role(
            "participant",
            purge=(
                FoundStep(
                    "удалить токены",
                    "participant",
                    "token",
                    lambda run: [
                        str(found) for found in sorted(self.home.glob("*.json"))
                    ],
                    delete,
                ),
            ),
        )

    def run_purge(self, answer: str, roles=None):
        given = self.boundaries(stdin=answer)
        chosen = roles or (self.server,)
        code = main(
            ["--role", _role_flag(chosen), "--remove", "--purge"], given, chosen
        )
        return code, given.stdout.getvalue() + given.stderr.getvalue()

    def test_a_refused_purge_changes_nothing(self):
        code, _ = self.run_purge("нет\n")
        self.assertEqual(code, CANCELLED)
        self.assertTrue(self.config.is_file())
        self.assertEqual(self.log, [])

    def test_an_empty_answer_cancels(self):
        code, _ = self.run_purge("")
        self.assertEqual(code, CANCELLED)
        self.assertTrue(self.config.is_file())

    def test_a_confirmed_purge_removes_first_and_purges_after(self):
        code, _ = self.run_purge(f"{WORD}\n")
        self.assertEqual(code, DONE)
        self.assertEqual(
            self.log,
            [f"delete:{self.config}", "delete:continuwuity-data"],
        )

    def test_the_confirmation_lists_the_exact_targets_and_consequence(self):
        _, said = self.run_purge(f"{WORD}\n")
        self.assertIn(str(self.config), said)
        self.assertIn("continuwuity-data", said)
        self.assertIn("история комнаты исчезнет", said)

    def test_a_resource_without_a_record_is_never_a_target(self):
        _, said = self.run_purge(f"{WORD}\n")
        self.assertNotIn("сделано руками", said)
        self.assertTrue(self.hand_made.is_file())

    def test_a_confirmed_purge_empties_the_record(self):
        self.run_purge(f"{WORD}\n")
        self.assertFalse(self.record("server").exists())

    def test_targets_of_every_selected_role_are_confirmed_together(self):
        code, said = self.run_purge("нет\n", (self.server, self.participant_role()))
        self.assertEqual(code, CANCELLED)
        self.assertEqual(self.log, [])
        self.assertIn("continuwuity-data", said)
        self.assertIn("glm.json", said)
        self.assertIn("server: volume", said)
        self.assertIn("participant: token", said)

    def test_a_discovered_resource_is_listed_without_being_recorded(self):
        _, said = self.run_purge("нет\n", (self.participant_role(),))
        self.assertIn(str(self.token), said)
        self.assertFalse(self.record("participant").exists())

    def test_a_refused_purge_of_a_discovered_resource_leaves_the_file(self):
        code, _ = self.run_purge("нет\n", (self.participant_role(),))
        self.assertEqual(code, CANCELLED)
        self.assertTrue(self.token.is_file())

    def test_a_confirmed_purge_of_a_discovered_resource_deletes_it(self):
        code, said = self.run_purge(f"{WORD}\n", (self.participant_role(),))
        self.assertEqual(code, DONE, said)
        self.assertEqual(self.log, [f"delete:{self.token}"])

    def test_the_question_names_the_exact_word(self):
        _, said = self.run_purge("нет\n")
        self.assertIn(f"введите {WORD}", said)

    def test_removal_without_purge_asks_nothing(self):
        given = self.boundaries()
        code = main(["--role", "server", "--remove"], given, (self.server,))
        self.assertEqual(code, DONE)
        self.assertNotIn(WORD, given.stdout.getvalue())
        self.assertEqual(self.log, [f"delete:{self.config}"])
        self.assertTrue(self.record("server").is_file())

    def test_a_second_removal_has_nothing_left_to_do(self):
        main(["--role", "server", "--remove"], self.boundaries(), (self.server,))
        self.log.clear()
        main(["--role", "server", "--remove"], self.boundaries(), (self.server,))
        self.assertEqual(self.log, [])


class ConfirmedSetTests(InstallerTestCase):
    def setUp(self):
        super().setUp()
        self.token = self.home / "glm.json"
        self.token.write_text('{"token": "t"}\n', encoding="utf-8")

    def participant_role(self, remove=()):
        def delete(run, id: str) -> None:
            Path(id).unlink()

        return role(
            "participant",
            remove=remove,
            purge=(
                FoundStep(
                    "удалить токены",
                    "participant",
                    "token",
                    lambda run: [
                        str(found) for found in sorted(self.home.glob("*.json"))
                    ],
                    delete,
                ),
            ),
        )

    def test_a_confirmed_target_is_deleted(self):
        given = self.boundaries(stdin=f"{WORD}\n")
        code = main(
            ["--role", "participant", "--remove", "--purge"],
            given,
            (self.participant_role(),),
        )
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.assertFalse(self.token.exists())

    def test_a_file_that_appeared_after_the_question_survives(self):
        late = FileMarker("создать поздний файл", self.home / "поздний.json", self.log)
        given = self.boundaries(stdin=f"{WORD}\n")
        code = main(
            ["--role", "participant", "--remove", "--purge"],
            given,
            (self.participant_role(remove=(late,)),),
        )
        said = given.stdout.getvalue() + given.stderr.getvalue()
        self.assertEqual(code, DONE, said)
        self.assertTrue((self.home / "поздний.json").exists())
        self.assertFalse(self.token.exists())
        self.assertIn("поздний.json", said)

    def test_a_purge_step_that_does_not_declare_its_targets_is_refused(self):
        with self.assertRaises(TypeError):
            role("server", purge=(Marker("очистить как-то", self.log),))

    def test_a_removal_step_that_finds_unrecorded_data_is_refused(self):
        with self.assertRaises(TypeError):
            role(
                "server",
                remove=(FoundStep("искать токены", "server", "token", lambda run: []),),
            )


class RecordProtectionTests(InstallerTestCase):
    def setUp(self):
        super().setUp()
        self.token = self.home / "glm.json"
        self.token.write_text('{"token": "t"}\n', encoding="utf-8")
        recorded(
            self.home / "records",
            "server.json",
            [("volume", "continuwuity-data")],
        )
        recorded(self.home / "records", "participant.json", [("token", "glm.json")])

    def greedy_role(self) -> object:
        def delete(run, id: str) -> None:
            Path(id).unlink()

        return role(
            "participant",
            purge=(
                FoundStep(
                    "убрать всё найденное",
                    "participant",
                    "token",
                    lambda run: [
                        str(found) for found in sorted(self.home.glob("**/*.json"))
                    ],
                    delete,
                ),
            ),
        )

    def greedy_purge(self, answer: str = "") -> tuple[int, str]:
        given = self.boundaries(stdin=f"{answer}\n")
        code = main(
            ["--role", "participant", "--remove", "--purge"],
            given,
            (self.greedy_role(), role("server")),
        )
        return code, given.stdout.getvalue() + given.stderr.getvalue()

    def test_a_participant_purge_leaves_the_record_of_another_role(self):
        code, said = self.greedy_purge(WORD)
        self.assertEqual(code, DONE, said)
        self.assertTrue(self.record("server").is_file())

    def test_a_participant_purge_leaves_its_own_record(self):
        code, said = self.greedy_purge(WORD)
        self.assertEqual(code, DONE, said)
        self.assertTrue(self.record("participant").is_file())

    def test_the_confirmed_token_is_deleted(self):
        code, said = self.greedy_purge(WORD)
        self.assertEqual(code, DONE, said)
        self.assertFalse(self.token.exists())

    def test_the_records_left_in_place_are_reported(self):
        _, said = self.greedy_purge(WORD)
        self.assertIn("запись установщика", said)
        self.assertIn(str(self.record("server")), said)

    def test_the_records_are_not_asked_about(self):
        _, said = self.greedy_purge(WORD)
        question = said.split("Чтобы продолжить")[0]
        self.assertIn(str(self.token), question)
        self.assertNotIn(str(self.record("server")), question)

    def test_a_record_named_through_a_dot_dot_path_is_still_a_record(self):
        twisted = self.home / "records" / ".." / "records" / "server.json"

        def delete(run, id: str) -> None:
            Path(id).unlink()

        greedy = role(
            "participant",
            purge=(
                FoundStep(
                    "убрать всё найденное",
                    "participant",
                    "token",
                    lambda run: [str(twisted)],
                    delete,
                ),
            ),
        )
        given = self.boundaries(stdin=f"{WORD}\n")
        code = main(
            ["--role", "participant", "--remove", "--purge"],
            given,
            (greedy, role("server")),
        )
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.assertTrue(self.record("server").is_file())

    def test_a_record_path_written_through_a_dot_dot_is_still_protected(self):
        def delete(run, id: str) -> None:
            Path(id).unlink()

        greedy = role(
            "participant",
            purge=(
                FoundStep(
                    "убрать всё найденное",
                    "participant",
                    "token",
                    lambda run: [str(self.record("server"))],
                    delete,
                ),
            ),
        )
        twisted = Role(
            name="server",
            record_path=lambda b: b.home / "records" / ".." / "records" / "server.json",
        )
        given = self.boundaries(stdin=f"{WORD}\n")
        code = main(
            ["--role", "participant", "--remove", "--purge"],
            given,
            (greedy, twisted),
        )
        self.assertEqual(code, DONE, given.stderr.getvalue())
        self.assertTrue(self.record("server").is_file())


def _role_flag(roles) -> str:
    return "both" if len(roles) > 1 else roles[0].name


if __name__ == "__main__":
    unittest.main()
