"""Долговременное хранилище брокера: регистрации и подписки.

SQLite под `bridge/state/`. Хранит только то, что Matrix выразить не может:
кто каким токеном владеет, на что подписан и до чего подтвердил получение.
Тел сообщений здесь нет и быть не может: единственный источник данных - комната.

Обоснование решений - .development/tasks/story-v1.0.0-pubsub-core.md, разделы
"The store" и "What transfers from the Jarvis journal".
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE meta (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE registrations (
        agent TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        token TEXT NOT NULL,
        registered_at REAL NOT NULL,
        depth INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE subscriptions (
        agent TEXT NOT NULL,
        topic TEXT NOT NULL,
        acked_event_id TEXT NOT NULL,
        acked_at REAL,
        created_at REAL NOT NULL,
        PRIMARY KEY (agent, topic),
        FOREIGN KEY (agent) REFERENCES registrations(agent) ON DELETE CASCADE
    )
    """,
)

_RECOVERY = "удалите файл и заново выполните /chatlogin в каждой сессии"


class StoreError(Exception):
    pass


class DuplicateAgent(StoreError):
    pass


class UnknownRegistration(StoreError):
    pass


class StoreOpenError(StoreError):
    pass


class StoreSchemaTooNew(StoreOpenError):
    pass


class UnknownSubscription(StoreError):
    pass


@contextmanager
def open_store(path: Path):
    """Открывает хранилище на запись, создавая схему, если файла ещё нет.

    База новее, чем знает код, не открывается вовсе: таблицы под версию,
    которую мы не понимаем, могут уже содержать то, что мы перезапишем.
    Закрывает соединение при выходе: запись коммитится внутри операций,
    а не при закрытии.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path)
    try:
        _check_schema(connection, path)
        connection.execute("PRAGMA foreign_keys = ON")
        yield connection
    finally:
        connection.close()


@contextmanager
def open_read_only(path: Path):
    """Чтение без права записи: испорченный путь токенов здесь не запишется."""
    path = Path(path)
    if not path.exists():
        raise StoreOpenError(f"{path}: файла нет; {_RECOVERY}.")
    connection = _connect(path, mode="ro")
    try:
        _check_schema(connection, path)
        yield connection
    finally:
        connection.close()


def _connect(path: Path, mode: str = "rwc") -> sqlite3.Connection:
    try:
        if mode == "ro":
            return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        return sqlite3.connect(path)
    except sqlite3.Error as error:
        raise _open_error(path, error) from None


def insert_registration(
    store: sqlite3.Connection,
    agent: str,
    label: str,
    token: str,
    registered_at: float,
    depth: int = 0,
) -> None:
    with store:
        try:
            store.execute(
                "INSERT INTO registrations (agent, label, token, registered_at, depth)"
                " VALUES (?, ?, ?, ?, ?)",
                (agent, label, token, registered_at, depth),
            )
        except sqlite3.IntegrityError:
            raise DuplicateAgent(
                f"агент {agent} уже имеет регистрацию; перезапись запрещена"
            ) from None


def update_registration(
    store: sqlite3.Connection,
    agent: str,
    *,
    label: str | None = None,
    depth: int | None = None,
) -> None:
    with store:
        cursor = store.execute(
            "UPDATE registrations SET label = COALESCE(?, label),"
            " depth = COALESCE(?, depth) WHERE agent = ?",
            (label, depth, agent),
        )
        if cursor.rowcount == 0:
            raise UnknownRegistration(f"регистрации {agent} нет, обновлять нечего")


def load_registrations(store: sqlite3.Connection) -> list[tuple]:
    with store:
        return store.execute(
            "SELECT agent, label, token, registered_at, depth FROM registrations"
            " ORDER BY agent"
        ).fetchall()


def delete_registration(store: sqlite3.Connection, agent: str) -> None:
    with store:
        store.execute("DELETE FROM registrations WHERE agent = ?", (agent,))


def add_subscription(
    store: sqlite3.Connection,
    agent: str,
    topic: str,
    created_at: float,
    seed_event_id: str,
) -> None:
    """Создаёт подпись с позицией, взятой из комнаты в момент подписки.

    Идемпотентность - "уже есть, ничего не делать": перезапись seed затёрла бы
    накопленную ACK-позицию, а это потеря доставленных сообщений. Позиция есть
    у каждой подписи с рождения, поэтому у resume один код пути.
    """
    with store:
        try:
            store.execute(
                "INSERT INTO subscriptions (agent, topic, acked_event_id, acked_at,"
                " created_at) VALUES (?, ?, ?, NULL, ?)",
                (agent, topic, seed_event_id, created_at),
            )
        except sqlite3.IntegrityError as error:
            if store.execute(
                "SELECT 1 FROM subscriptions WHERE agent = ? AND topic = ?",
                (agent, topic),
            ).fetchone():
                return
            raise StoreError(
                f"подписка {agent} на {topic} невозможна: нет регистрации ({error})"
            ) from None


def delete_subscription(store: sqlite3.Connection, agent: str, topic: str) -> None:
    with store:
        store.execute(
            "DELETE FROM subscriptions WHERE agent = ? AND topic = ?",
            (agent, topic),
        )


def load_subscriptions(store: sqlite3.Connection, agent: str) -> list[tuple]:
    with store:
        return store.execute(
            "SELECT topic, acked_event_id, acked_at, created_at FROM subscriptions"
            " WHERE agent = ? ORDER BY topic",
            (agent,),
        ).fetchall()


def record_ack(
    store: sqlite3.Connection, agent: str, topic: str, event_id: str, at: float
) -> None:
    """Подтверждение получения: позиция и её время, один стейтмент, один commit."""
    with store:
        cursor = store.execute(
            "UPDATE subscriptions SET acked_event_id = ?, acked_at = ?"
            " WHERE agent = ? AND topic = ?",
            (event_id, at, agent, topic),
        )
        if cursor.rowcount == 0:
            raise UnknownSubscription(
                f"подписка {agent} на {topic} не существует, подтверждать нечего"
            )


def _check_schema(connection: sqlite3.Connection, path: Path) -> None:
    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
        ).fetchone()
        if row is None:
            connection.execute("BEGIN")
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            connection.commit()
            return
        row = connection.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.DatabaseError as error:
        raise _open_error(path, error) from None
    if row is not None:
        try:
            version = int(row[0])
        except ValueError:
            raise StoreOpenError(
                f"{path}: в meta лежит не версия: {row[0]!r}. {_RECOVERY}."
            ) from None
        if version > SCHEMA_VERSION:
            raise StoreSchemaTooNew(
                f"{path}: схема версии {version} новее, чем знает код "
                f"({SCHEMA_VERSION}); читать её нельзя"
            )


def _open_error(path: Path, error: Exception) -> StoreOpenError:
    return StoreOpenError(
        f"{path}: файл повреждён или не является базой ({error}). {_RECOVERY}."
    )
