"""The broker's durable store: registrations and subscriptions.

SQLite under `bridge/state/`. It keeps only what Matrix cannot express: who
owns which token, what each agent is subscribed to and how far it has
acknowledged. Message bodies are not kept here and never can be: the room is
the only source of them.

Rationale: .development/tasks/story-v1.0.0-pubsub-core.md, sections
"The store" and "What transfers from the Jarvis journal".
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

DEVELOPER_SENTENCES = {
    "missing_file": (
        "{path}: the store file does not exist; delete it and run /chatlogin"
        " again in every session."
    ),
    "corrupted": (
        "{path}: the file is damaged or is not a database ({error}); delete it"
        " and run /chatlogin again in every session."
    ),
    "bad_schema_version": (
        "{path}: the meta table holds a value that is not a version: {value!r};"
        " delete the file and run /chatlogin again in every session."
    ),
    "schema_too_new": (
        "{path}: schema version {version} is newer than the supported one"
        " ({supported}); it cannot be read."
    ),
    "duplicate_agent": (
        "Agent {agent} already has a registration; overwriting is refused."
    ),
    "unknown_registration": "There is no registration for {agent}; nothing to update.",
    "unknown_subscription": (
        "There is no subscription of {agent} to {topic}; nothing to acknowledge."
    ),
    "subscription_without_registration": (
        "A subscription of {agent} to {topic} is impossible: the agent has no"
        " registration ({error})."
    ),
}
STORE_ERROR_CODES = tuple(sorted(DEVELOPER_SENTENCES))


class StoreError(Exception):
    code: str | None = None

    def __init__(self, code: str | None = None, **params: object):
        self.code = code or type(self).code
        self.params = params
        super().__init__(DEVELOPER_SENTENCES[self.code].format(**params))


class DuplicateAgent(StoreError):
    code = "duplicate_agent"


class UnknownRegistration(StoreError):
    code = "unknown_registration"


class StoreOpenError(StoreError):
    pass


class StoreSchemaTooNew(StoreOpenError):
    code = "schema_too_new"


class UnknownSubscription(StoreError):
    code = "unknown_subscription"


@contextmanager
def open_store(path: Path):
    """Opens the store for writing, creating the schema if the file is new.

    A database newer than the code is not opened at all: tables of a version
    we do not understand may already hold what we would overwrite. The
    connection is closed on exit: writes are committed inside the operations,
    not on close.
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
    """Reads without the right to write: a damaged token path is not written here."""
    path = Path(path)
    if not path.exists():
        raise StoreOpenError("missing_file", path=str(path))
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
            raise DuplicateAgent(agent=agent) from None


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
            raise UnknownRegistration(agent=agent)


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
    """Creates a subscription at the position taken from the room when it is made.

    Idempotence means "already there, do nothing": overwriting the seed would
    erase the accumulated ACK position, which loses delivered messages. Every
    subscription has a position from birth, so resume has a single code path.
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
                "subscription_without_registration",
                agent=agent,
                topic=topic,
                error=str(error),
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
    """Acknowledgement: the position and its time, one statement, one commit."""
    with store:
        cursor = store.execute(
            "UPDATE subscriptions SET acked_event_id = ?, acked_at = ?"
            " WHERE agent = ? AND topic = ?",
            (event_id, at, agent, topic),
        )
        if cursor.rowcount == 0:
            raise UnknownSubscription(agent=agent, topic=topic)


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
                "bad_schema_version", path=str(path), value=row[0]
            ) from None
        if version > SCHEMA_VERSION:
            raise StoreSchemaTooNew(
                path=str(path), version=version, supported=SCHEMA_VERSION
            )


def _open_error(path: Path, error: Exception) -> StoreOpenError:
    return StoreOpenError("corrupted", path=str(path), error=str(error))
