import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .model import Job, Notice


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY, coordinator TEXT NOT NULL, root_event TEXT NOT NULL,
                round INTEGER NOT NULL DEFAULT 1, requests INTEGER NOT NULL DEFAULT 0,
                epoch INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions (
                topic TEXT NOT NULL, agent TEXT NOT NULL, session TEXT NOT NULL,
                PRIMARY KEY(topic, agent));
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, topic TEXT NOT NULL REFERENCES topics(id), agent TEXT NOT NULL,
                prompt TEXT NOT NULL, event_id TEXT NOT NULL, round INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending', result TEXT NOT NULL DEFAULT '',
                reply_agent TEXT NOT NULL DEFAULT '', epoch INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS issues (
                id TEXT PRIMARY KEY, topic TEXT NOT NULL REFERENCES topics(id), agent TEXT NOT NULL,
                question TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
                answer TEXT NOT NULL DEFAULT '', answer_event TEXT NOT NULL DEFAULT '',
                answer_sender TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS outbox (
                id TEXT PRIMARY KEY, room TEXT NOT NULL, agent TEXT NOT NULL,
                body TEXT NOT NULL, human INTEGER NOT NULL, thread TEXT NOT NULL,
                event_id TEXT NOT NULL DEFAULT '');
        """)

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def atomic(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def accept_event(self, event_id: str) -> bool:
        return (
            self.db.execute(
                "INSERT OR IGNORE INTO events VALUES (?)", (event_id,)
            ).rowcount
            == 1
        )

    def get_meta(self, name: str) -> str:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (name,)).fetchone()
        return str(row[0]) if row else ""

    def set_meta(self, name: str, value: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (name, value))

    def session(self, topic: str, agent: str) -> str:
        row = self.db.execute(
            "SELECT session FROM sessions WHERE topic=? AND agent=?", (topic, agent)
        ).fetchone()
        return str(row[0]) if row else ""

    def queue(self, job: Job) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO jobs(id,topic,agent,prompt,event_id,round,reply_agent,epoch) VALUES (?,?,?,?,?,?,?,(SELECT epoch FROM topics WHERE id=?))",
            (
                job.id,
                job.topic,
                job.agent,
                job.prompt,
                job.event_id,
                job.round,
                job.reply_agent,
                job.topic,
            ),
        )

    def claim(self, agent: str) -> Job | None:
        with self.atomic():
            row = self.db.execute(
                """SELECT j.* FROM jobs j WHERE j.agent=? AND j.status='pending'
                AND NOT EXISTS (SELECT 1 FROM issues i WHERE i.topic=j.topic AND i.status!='resolved')
                AND NOT EXISTS (SELECT 1 FROM jobs b WHERE b.agent=j.agent AND b.status IN ('running','result'))
                ORDER BY j.rowid LIMIT 1""",
                (agent,),
            ).fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE jobs SET status='running' WHERE id=?", (row["id"],))
            return self.job(row)

    @staticmethod
    def job(row: sqlite3.Row) -> Job:
        return Job(
            str(row["id"]),
            str(row["topic"]),
            str(row["agent"]),
            str(row["prompt"]),
            str(row["event_id"]),
            int(row["round"]),
            str(row["reply_agent"]),
        )

    def notice(self, notice: Notice) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO outbox(id,room,agent,body,human,thread) VALUES (?,?,?,?,?,?)",
            (
                notice.id,
                notice.room,
                notice.agent,
                notice.body,
                int(notice.human),
                notice.thread,
            ),
        )

    def pending_notices(self) -> list[Notice]:
        return [
            Notice(
                str(r["id"]),
                str(r["room"]),
                str(r["agent"]),
                str(r["body"]),
                bool(r["human"]),
                str(r["thread"]),
            )
            for r in self.db.execute(
                "SELECT * FROM outbox WHERE event_id='' ORDER BY rowid"
            )
        ]

    def sent(self, notice_id: str, event_id: str) -> None:
        self.db.execute(
            "UPDATE outbox SET event_id=? WHERE id=?", (event_id, notice_id)
        )
