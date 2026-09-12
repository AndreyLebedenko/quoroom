import sqlite3
import tempfile
import unittest
from pathlib import Path

from sessionchat.store import (
    DuplicateAgent,
    StoreError,
    StoreOpenError,
    StoreSchemaTooNew,
    UnknownRegistration,
    UnknownSubscription,
    add_subscription,
    delete_registration,
    delete_subscription,
    insert_registration,
    load_registrations,
    load_subscriptions,
    open_read_only,
    open_store,
    record_ack,
    update_registration,
)


class StoreTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "state" / "agentschat.db"

    def open(self):
        return open_store(self.path)


class RegistrationRoundTripTests(StoreTestCase):
    def test_registration_written_then_read_back_after_reopen(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
        self.assertEqual(
            self._registrations(),
            [("claude-code", "метка", "tok-1", 100.0, 0)],
        )

    def test_update_registration_changes_label(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "старая", "tok-1", 100.0)
            update_registration(store, "claude-code", label="новая")
        row = self._registrations()[0]
        self.assertEqual(row[1], "новая")
        self.assertEqual(row[2], "tok-1")
        self.assertEqual(row[3], 100.0)
        self.assertEqual(row[4], 0)

    def test_update_registration_changes_depth_only(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            update_registration(store, "claude-code", depth=3)
        row = self._registrations()[0]
        self.assertEqual(row[1], "метка")
        self.assertEqual(row[4], 3)

    def test_update_registration_without_arguments_changes_nothing(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            update_registration(store, "claude-code")
        self.assertEqual(
            self._registrations(),
            [("claude-code", "метка", "tok-1", 100.0, 0)],
        )

    def test_update_registration_for_an_unknown_agent_is_refused(self):
        # Обновление, не нашедшее строки, ничего не сообщило бы вызывающему, а
        # задача 02 меняет метку при переподключении: потеря была бы молчаливой.
        with self.open() as store:
            with self.assertRaises(UnknownRegistration):
                update_registration(store, "нет-такого", label="метка")

    def test_depth_defaults_to_zero_when_not_given(self):
        with self.open() as store:
            insert_registration(store, "opencode", "метка", "tok-2", 200.0)
        self.assertEqual(self._registrations()[0][4], 0)

    def _registrations(self):
        with open_read_only(self.path) as store:
            return load_registrations(store)


class DuplicateRegistrationTests(StoreTestCase):
    def test_second_insert_for_the_same_agent_is_refused(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "первый", "tok-1", 100.0)
            with self.assertRaises(DuplicateAgent):
                insert_registration(store, "claude-code", "второй", "tok-2", 200.0)

    def test_refused_insert_leaves_the_existing_row_untouched(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "первый", "tok-1", 100.0)
            try:
                insert_registration(store, "claude-code", "второй", "tok-2", 200.0)
            except DuplicateAgent:
                pass
            self.assertEqual(
                load_registrations(store),
                [("claude-code", "первый", "tok-1", 100.0, 0)],
            )


class DeleteRegistrationTests(StoreTestCase):
    def test_delete_removes_the_registration_row(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            delete_registration(store, "claude-code")
            self.assertEqual(load_registrations(store), [])

    def test_delete_of_a_missing_registration_is_silent(self):
        # Удаление идемпотентно по смыслу: цель достигнута, строки уже нет.
        # Этим оно и отличается от update_registration и record_ack.
        with self.open() as store:
            delete_registration(store, "нет-такого")
            self.assertEqual(load_registrations(store), [])

    def test_delete_cascades_to_subscriptions(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            add_subscription(store, "claude-code", "@room", 10.0, "$seed")
            add_subscription(store, "claude-code", "claude-code", 10.0, "$seed")
            delete_registration(store, "claude-code")
            self.assertEqual(load_subscriptions(store, "claude-code"), [])


class SubscriptionSeedingTests(StoreTestCase):
    def test_subscription_is_readable_immediately_with_seed_in_place(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            add_subscription(store, "claude-code", "@room", 10.0, "$seed")
            self.assertEqual(
                load_subscriptions(store, "claude-code"),
                [("@room", "$seed", None, 10.0)],
            )

    def test_no_row_ever_has_a_null_acked_event_id(self):
        with self.open() as store:
            insert_registration(store, "a", "метка", "tok-a", 100.0)
            insert_registration(store, "b", "метка", "tok-b", 100.0)
            add_subscription(store, "a", "@room", 10.0, "$seed-a")
            add_subscription(store, "a", "a", 10.0, "$seed-a")
            add_subscription(store, "b", "@room", 10.0, "$seed-b")
            rows = store.execute(
                "SELECT agent, topic, acked_event_id FROM subscriptions"
            ).fetchall()
        self.assertEqual(len(rows), 3)
        for agent, topic, acked_event_id in rows:
            self.assertIsNotNone(acked_event_id, (agent, topic))

    def test_acked_at_is_null_until_record_ack(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            add_subscription(store, "claude-code", "@room", 10.0, "$seed")
            self.assertIsNone(load_subscriptions(store, "claude-code")[0][2])

    def test_seeding_the_same_topic_again_keeps_the_original_position(self):
        # Идемпотентность не может перепосевать позицию: тот же (agent, topic)
        # с другим seed значило бы сбросить ACK-позицию назад и потерять всё,
        # что подписчик уже подтвердил. Повторный вызов ничего не меняет.
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            add_subscription(store, "claude-code", "@room", 10.0, "$seed")
            record_ack(store, "claude-code", "@room", "$real", 20.0)
            add_subscription(store, "claude-code", "@room", 99.0, "$other-seed")
            self.assertEqual(
                load_subscriptions(store, "claude-code"),
                [("@room", "$real", 20.0, 10.0)],
            )


class AckTests(StoreTestCase):
    def setUp(self):
        super().setUp()
        self.store = self.enterContext(self.open())
        insert_registration(self.store, "claude-code", "метка", "tok-1", 100.0)
        add_subscription(self.store, "claude-code", "@room", 10.0, "$seed")

    def tearDown(self):
        self.store.close()

    def test_record_ack_writes_both_fields(self):
        record_ack(self.store, "claude-code", "@room", "$ack", 42.0)
        self.assertEqual(
            load_subscriptions(self.store, "claude-code"),
            [("@room", "$ack", 42.0, 10.0)],
        )

    def test_record_ack_is_durable_across_a_reopen(self):
        record_ack(self.store, "claude-code", "@room", "$ack", 42.0)
        with self.open() as store:
            self.assertEqual(load_subscriptions(store, "claude-code")[0][1], "$ack")

    def test_record_ack_moves_the_position_forward(self):
        record_ack(self.store, "claude-code", "@room", "$first", 42.0)
        record_ack(self.store, "claude-code", "@room", "$second", 43.0)
        self.assertEqual(load_subscriptions(self.store, "claude-code")[0][1], "$second")

    def test_record_ack_for_an_unknown_subscription_is_refused(self):
        with self.assertRaises(UnknownSubscription):
            record_ack(self.store, "claude-code", "other-topic", "$ack", 42.0)


class DeleteSubscriptionTests(StoreTestCase):
    def test_delete_of_a_missing_subscription_is_silent(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            delete_subscription(store, "claude-code", "@room")
            self.assertEqual(load_subscriptions(store, "claude-code"), [])

    def test_delete_removes_only_that_topic(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            add_subscription(store, "claude-code", "@room", 10.0, "$seed")
            add_subscription(store, "claude-code", "claude-code", 10.0, "$seed")
            delete_subscription(store, "claude-code", "@room")
            self.assertEqual(
                [row[0] for row in load_subscriptions(store, "claude-code")],
                ["claude-code"],
            )


class SubscriptionIntegrityTests(StoreTestCase):
    def test_subscription_without_a_registration_is_refused(self):
        with self.open() as store:
            with self.assertRaises(StoreError):
                add_subscription(store, "ghost", "@room", 10.0, "$seed")

    def test_a_refused_reinsert_leaves_the_subscriptions_alone(self):
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            add_subscription(store, "claude-code", "@room", 10.0, "$seed")
            record_ack(store, "claude-code", "@room", "$ack", 20.0)
            with self.assertRaises(DuplicateAgent):
                insert_registration(store, "claude-code", "другая", "tok-2", 200.0)
            self.assertEqual(
                load_subscriptions(store, "claude-code"),
                [("@room", "$ack", 20.0, 10.0)],
            )

    def test_the_schema_refuses_a_null_acked_event_id(self):
        # "Ни одна строка не бывает без позиции" держится ограничением схемы,
        # а не дисциплиной вызывающих: без NOT NULL resume получил бы
        # подписку, от которой нечего отсчитывать.
        with self.open() as store:
            insert_registration(store, "claude-code", "метка", "tok-1", 100.0)
            with self.assertRaises(sqlite3.IntegrityError):
                with store:
                    store.execute(
                        "INSERT INTO subscriptions (agent, topic, acked_event_id,"
                        " acked_at, created_at) VALUES ('claude-code', '@room',"
                        " NULL, NULL, 10.0)"
                    )


class SchemaVersionTests(StoreTestCase):
    def test_schema_version_is_written_on_creation(self):
        with self.open() as store:
            row = store.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
        self.assertEqual(row, ("1",))

    def test_a_newer_schema_version_is_refused(self):
        with self.open() as store:
            with store:
                store.execute(
                    "UPDATE meta SET value = '99' WHERE key = 'schema_version'"
                )
        with self.assertRaises(StoreSchemaTooNew) as raised:
            with self.open():
                pass
        self.assertIn(str(self.path), str(raised.exception))

    def test_reading_after_a_version_refusal_is_impossible(self):
        with self.open() as store:
            with store:
                store.execute(
                    "UPDATE meta SET value = '99' WHERE key = 'schema_version'"
                )
        with self.assertRaises(StoreSchemaTooNew):
            with open_read_only(self.path) as store:
                load_registrations(store)


class CorruptFileTests(StoreTestCase):
    def test_a_truncated_file_is_refused_with_path_and_recovery(self):
        with self.open():
            pass
        data = self.path.read_bytes()
        self.path.write_bytes(data[: len(data) // 2])
        with self.assertRaises(StoreOpenError) as raised:
            with self.open():
                pass
        message = str(raised.exception)
        self.assertIn(str(self.path), message)
        self.assertIn("/chatlogin", message)

    def test_a_non_sqlite_file_is_refused_with_path_and_recovery(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"not a database at all" * 100)
        with self.assertRaises(StoreOpenError) as raised:
            with self.open():
                pass
        message = str(raised.exception)
        self.assertIn(str(self.path), message)
        self.assertIn("/chatlogin", message)

    def test_a_truncated_file_is_not_a_bare_database_error(self):
        with self.open():
            pass
        data = self.path.read_bytes()
        self.path.write_bytes(data[: len(data) // 2])
        try:
            with self.open():
                pass
        except sqlite3.DatabaseError:
            self.fail("bare sqlite3.DatabaseError escaped the store")
        except StoreOpenError:
            pass


class WriteDurabilityTests(StoreTestCase):
    def test_every_write_commits_before_returning(self):
        # Отдельное открытие на каждую операцию: незакоммиченная запись
        # исчезает вместе с соединением, и только commit до возврата делает
        # её видимой следующему.
        with self.open() as store:
            insert_registration(store, "a", "метка", "tok-a", 1.0)
        with self.open() as store:
            add_subscription(store, "a", "@room", 2.0, "$seed")
        with self.open() as store:
            update_registration(store, "a", depth=4)
        with self.open() as store:
            record_ack(store, "a", "@room", "$ack", 3.0)
        with self.open() as store:
            self.assertEqual(
                load_registrations(store),
                [("a", "метка", "tok-a", 1.0, 4)],
            )
            self.assertEqual(
                load_subscriptions(store, "a"),
                [("@room", "$ack", 3.0, 2.0)],
            )


class DirectoryCreationTests(StoreTestCase):
    def test_missing_parent_directories_are_created(self):
        self.assertFalse(self.path.parent.exists())
        with self.open():
            pass
        self.assertTrue(self.path.exists())


class ReadOnlyPathTests(StoreTestCase):
    def test_read_only_connection_refuses_to_write(self):
        with self.open() as store:
            insert_registration(store, "a", "метка", "tok", 1.0)
        with open_read_only(self.path) as store:
            with self.assertRaises(sqlite3.OperationalError):
                store.execute(
                    "INSERT INTO registrations VALUES ('b', 'x', 't', 1.0, 0)"
                )

    def test_a_read_only_load_matches_the_writable_one(self):
        with self.open() as store:
            insert_registration(store, "a", "метка", "tok", 1.0)
            add_subscription(store, "a", "@room", 2.0, "$seed")
            with open_read_only(self.path) as reader:
                self.assertEqual(load_registrations(reader), load_registrations(store))
                self.assertEqual(
                    load_subscriptions(reader, "a"), load_subscriptions(store, "a")
                )

    def test_read_only_open_refuses_a_missing_file(self):
        with self.assertRaises(StoreOpenError):
            with open_read_only(self.path):
                pass


if __name__ == "__main__":
    unittest.main()
