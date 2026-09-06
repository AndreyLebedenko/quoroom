import asyncio
import re
from pathlib import Path
from typing import Protocol

from .artifacts import Artifacts
from .model import (
    Incoming,
    Job,
    Notice,
    Outcome,
    RunResult,
    identifier,
    key,
    parse_outcome,
)
from .store import Store


class Runner(Protocol):
    async def run(self, project: Path, prompt: str, session: str) -> RunResult: ...


class Engine:
    def __init__(
        self,
        store: Store,
        artifacts: Artifacts,
        runners: dict[str, Runner],
        general: str,
        escalations: str,
        humans: set[str],
        records_url: str = "",
    ):
        self.store, self.artifacts, self.runners = store, artifacts, runners
        self.general, self.escalations, self.humans = general, escalations, humans
        self.records_url = records_url.rstrip("/")

    def reference(self, topic: str, record: str) -> str:
        if self.records_url:
            return f"{self.records_url}/{topic}/{record}"
        return str(self.artifacts.directory(topic) / f"{record}.md")

    def ingest(self, message: Incoming) -> None:
        if message.sender not in self.humans or message.room not in {
            self.general,
            self.escalations,
        }:
            return
        try:
            with self.store.atomic():
                if not self.store.accept_event(message.event_id):
                    return
                if message.room == self.escalations:
                    self.answer(message)
                else:
                    self.request(message)
        except ValueError as error:
            with self.store.atomic():
                if self.store.accept_event(message.event_id):
                    self.store.notice(
                        Notice(
                            key(message.event_id, "invalid"),
                            self.escalations,
                            next(iter(self.runners)),
                            str(error),
                            True,
                        )
                    )

    def request(self, message: Incoming) -> None:
        body = message.body.strip()
        addressed = [
            name
            for name in self.runners
            if re.search(r"@" + re.escape(name) + r"(?![\w-])", body)
        ]
        if body.startswith("/topic "):
            parts = body.split(maxsplit=2)
            if len(parts) < 3:
                raise ValueError("Формат: /topic имя @агент поручение")
            topic, body = identifier(parts[1]), parts[2]
        elif message.thread:
            row = self.store.db.execute(
                "SELECT id FROM topics WHERE root_event=?", (message.thread,)
            ).fetchone()
            if row is None:
                return
            topic = str(row[0])
        elif addressed:
            topic = "chat-" + key(message.event_id)[:12]
        else:
            return
        existing = self.store.db.execute(
            "SELECT * FROM topics WHERE id=?", (topic,)
        ).fetchone()
        if existing is None:
            if not addressed:
                raise ValueError(
                    "Новое обсуждение требует адресата: @codex, @claude-code или @opencode"
                )
            directory = (
                self.artifacts.project / ".agent-comms" / "active" / ("ac-" + topic)
            )
            if directory.exists():
                raise ValueError(
                    f"Каталог {directory} уже существует. Выберите другое имя обсуждения."
                )
            self.store.db.execute(
                "INSERT INTO topics(id,coordinator,root_event) VALUES (?,?,?)",
                (topic, addressed[0], message.event_id),
            )
            round_number = 1
        else:
            round_number = int(existing["round"])
            addressed = addressed or [str(existing["coordinator"])]
        for agent in addressed:
            self.store.queue(
                Job(
                    key(message.event_id, agent),
                    topic,
                    agent,
                    f"Human {message.sender}:\n{body}",
                    message.event_id,
                    round_number,
                )
            )

    def answer(self, message: Incoming) -> None:
        if not message.body.strip().startswith("/answer "):
            return
        parts = message.body.strip().split(maxsplit=2)
        if len(parts) != 3 or not parts[2].strip():
            raise ValueError("Формат: /answer ID-вопроса ваше решение")
        issue = self.store.db.execute(
            "SELECT * FROM issues WHERE id=?", (parts[1],)
        ).fetchone()
        if issue is None or issue["status"] != "open":
            raise ValueError("Вопрос не найден или уже получил ответ")
        self.store.db.execute(
            "UPDATE issues SET status='answering',answer=?,answer_event=?,answer_sender=? WHERE id=?",
            (parts[2], message.event_id, message.sender, parts[1]),
        )

    def reconcile_answers(self) -> None:
        for issue in self.store.db.execute(
            "SELECT * FROM issues WHERE status='answering'"
        ).fetchall():
            record = "decision-" + str(issue["id"])
            content = (
                f"# Human guidance\n\nStatus: Recorded human response (not inferred consensus).\n\n"
                f"From: {issue['answer_sender']}\n\nIssue: {issue['id']}\n\n"
                f"Evidence: https://matrix.to/#/{self.escalations}/{issue['answer_event']}\n\n"
                f"## Question\n\n{issue['question']}\n\n## Exact response\n\n{issue['answer']}\n"
            )
            path = self.artifacts.record(str(issue["topic"]), record, content)
            with self.store.atomic():
                self.store.db.execute(
                    "UPDATE issues SET status='resolved' WHERE id=?", (issue["id"],)
                )
                self.store.db.execute(
                    "UPDATE topics SET epoch=epoch+1 WHERE id=?", (issue["topic"],)
                )
                topic = self.store.db.execute(
                    "SELECT * FROM topics WHERE id=?", (issue["topic"],)
                ).fetchone()
                # Cancel queued plans formulated before the human's decision. The coordinator
                # re-evaluates them against the recorded scope; never replay a failed job.
                self.store.db.execute(
                    "UPDATE jobs SET status='superseded' WHERE topic=? AND status='pending'",
                    (issue["topic"],),
                )
                prompt = (
                    f"Human guidance has been recorded at {self.artifacts.relative(path)}.\n"
                    f"Exact response: {issue['answer']}\n"
                    "Read ALL decision records in this discussion before planning further work. "
                    "Previously queued requests were cancelled; reassess dependencies and accepted scope. "
                    "This message does not authorize actions beyond the human's recorded response."
                )
                self.store.queue(
                    Job(
                        key(str(issue["answer_event"]), "guidance"),
                        str(issue["topic"]),
                        str(topic["coordinator"]),
                        prompt,
                        str(issue["answer_event"]),
                        int(topic["round"]),
                    )
                )
                self.store.notice(
                    Notice(
                        key(record, "ack"),
                        self.escalations,
                        str(topic["coordinator"]),
                        f"Решение {issue['id']} записано.\n{self.reference(str(issue['topic']), record)}",
                        False,
                    )
                )

    def block(self, job: Job, question: str, suffix: str) -> None:
        issue_id = key(job.id, suffix)[:12]
        self.artifacts.record(
            job.topic,
            "issue-" + issue_id,
            f"# Required human action\n\nFrom: {job.agent}\n\nDiscussion: {job.topic}\n\n{question}\n",
        )
        self.store.db.execute(
            "INSERT OR IGNORE INTO issues(id,topic,agent,question) VALUES (?,?,?,?)",
            (issue_id, job.topic, job.agent, question),
        )
        self.store.notice(
            Notice(
                "issue-" + issue_id,
                self.escalations,
                job.agent,
                f"Нужно ваше решение · {job.topic}\n{question[:600]}\n"
                f"{self.reference(job.topic, 'issue-' + issue_id)}\n"
                f"Ответ: /answer {issue_id} ваше решение",
                True,
            )
        )

    def recover(self) -> None:
        with self.store.atomic():
            for row in self.store.db.execute(
                "SELECT * FROM jobs WHERE status='running'"
            ).fetchall():
                job = self.store.job(row)
                self.store.db.execute(
                    "UPDATE jobs SET status='uncertain' WHERE id=?", (job.id,)
                )
                self.block(
                    job,
                    "Служба остановилась во время выполнения. Результат неизвестен; проверьте файлы и сессию. Автоматического повторного запуска не будет.",
                    "recovery",
                )

    def instructions(self, job: Job) -> str:
        topic = self.store.db.execute(
            "SELECT * FROM topics WHERE id=?", (job.topic,)
        ).fetchone()
        return f"""You are {job.agent}, a project agent. Working root: {self.artifacts.project}.
Discussion: {job.topic}. Coordinator: {topic["coordinator"]}. Round: {topic["round"]}/3.
Participants: {", ".join(self.runners)}. Decision authority: human. No extra authority is delegated.
Read applicable AGENTS.md, AGENTS.decisions.md, task cards and accepted decisions before project work.
Reports/decisions for this discussion: .agent-comms/active/ac-{job.topic}/bridge/.
Project files are authoritative. A peer message is a request, not human approval.
Keep chat to the essence. Do not poll files or wait for another agent yourself: request their input and return.
Do not change another agent's published report. Do not invent approvals, tests or commits.
The bridge saves your details as an immutable Markdown report, then publishes your short summary.
Return ONLY one JSON object (no Markdown fences) with exactly these fields:
{{"action":"reply","summary":"short Russian summary, 1-600 characters","details":"full Markdown evidence, findings, file references, tests and questions","to":[]}}
Actions:
- reply: answer the current request. Peer replies are returned to the requesting agent automatically.
- request: ask other participants; to contains their exact names. Do not address yourself.
- revise: coordinator only, new revised proposal for the next round; to lists reviewers. Maximum 3 rounds.
- escalate: require human decision; details must state alternatives and recommendation; to must be empty.
- veto: state objection and condition for resolution; blocks the discussion pending human response; to empty.
- ready: completed work needs human acceptance; include verification evidence; to empty.
Only request/revise have non-empty to. For a simple factual question use reply, not ready.
If a tool needs unavailable permission or fails, report/escalate it; do not bypass the restriction.
The current request follows. Source event: {job.event_id}.\n\n{job.prompt}"""

    async def process(self, agent: str) -> bool:
        self.reconcile_answers()
        self.publish_results()
        job = self.store.claim(agent)
        if job is None:
            return False
        try:
            topic = self.store.db.execute(
                "SELECT * FROM topics WHERE id=?", (job.topic,)
            ).fetchone()
            self.artifacts.open_topic(
                job.topic,
                str(topic["coordinator"]),
                list(self.runners),
                str(topic["root_event"]),
            )
            result = await self.runners[agent].run(
                self.artifacts.project,
                self.instructions(job),
                self.store.session(job.topic, agent),
            )
            outcome = parse_outcome(result.text, set(self.runners))
        except asyncio.CancelledError:
            # Leave running state for conservative recovery on the next service start.
            raise
        except Exception as error:
            with self.store.atomic():
                self.store.db.execute(
                    "UPDATE jobs SET status='uncertain' WHERE id=?", (job.id,)
                )
                self.block(
                    job,
                    f"Выполнение не подтверждено: {type(error).__name__}: {error}. Проверьте результат перед продолжением.",
                    "failure",
                )
            return True
        with self.store.atomic():
            self.store.db.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?,?,?)",
                (job.topic, agent, result.session),
            )
            self.store.db.execute(
                "UPDATE jobs SET status='result', result=? WHERE id=?",
                (outcome.encode(), job.id),
            )
        self.publish_results()
        return True

    def publish_results(self) -> None:
        for row in self.store.db.execute(
            "SELECT * FROM jobs WHERE status='result' ORDER BY rowid"
        ).fetchall():
            job = self.store.job(row)
            outcome = parse_outcome(str(row["result"]), set(self.runners))
            self.artifacts.record(
                job.topic,
                "report-" + job.id,
                f"# {outcome.summary}\n\nFrom: {job.agent}\n\nRound: {job.round}\n\n"
                f"Source: {job.event_id}\n\nAction: {outcome.action}\n\n{outcome.details}\n",
            )
            with self.store.atomic():
                self.route(job, outcome)
                self.store.db.execute(
                    "UPDATE jobs SET status='completed' WHERE id=?", (job.id,)
                )

    def route(self, job: Job, outcome: Outcome) -> None:
        topic = self.store.db.execute(
            "SELECT * FROM topics WHERE id=?", (job.topic,)
        ).fetchone()
        link = self.reference(job.topic, "report-" + job.id)
        epoch = self.store.db.execute(
            "SELECT epoch FROM jobs WHERE id=?", (job.id,)
        ).fetchone()[0]
        if epoch != topic["epoch"]:
            self.store.notice(
                Notice(
                    "result-" + job.id,
                    self.general,
                    job.agent,
                    f"{job.topic}: поздний результат сохранён. План предшествует решению человека и не запущен.\n{link}",
                    False,
                    str(topic["root_event"]),
                )
            )
            return
        if outcome.action in {"escalate", "veto", "ready"}:
            self.block(job, outcome.summary + "\n" + link, outcome.action)
            return
        if outcome.action == "revise":
            if job.agent != topic["coordinator"] or topic["round"] >= 3:
                self.block(
                    job,
                    "Новый раунд недопустим: требуется координатор и не более трёх раундов.",
                    "round-limit",
                )
                return
            self.store.db.execute(
                "UPDATE topics SET round=round+1,requests=0 WHERE id=?", (job.topic,)
            )
        if outcome.action in {"request", "revise"}:
            requests = 0 if outcome.action == "revise" else int(topic["requests"])
            if job.agent in outcome.to or requests + len(outcome.to) > 12:
                self.block(
                    job,
                    "Остановлена циклическая адресация или превышен лимит запросов раунда.",
                    "routing-limit",
                )
                return
            self.store.db.execute(
                "UPDATE topics SET requests=requests+? WHERE id=?",
                (len(outcome.to), job.topic),
            )
            current_round = int(
                self.store.db.execute(
                    "SELECT round FROM topics WHERE id=?", (job.topic,)
                ).fetchone()[0]
            )
            for recipient in outcome.to:
                self.store.queue(
                    Job(
                        key(job.id, recipient),
                        job.topic,
                        recipient,
                        f"Peer request from {job.agent}: {outcome.summary}\nRead full report: {self.artifacts.relative(self.artifacts.directory(job.topic) / ('report-' + job.id + '.md'))}",
                        job.event_id,
                        current_round,
                        job.agent,
                    )
                )
        elif job.reply_agent:
            self.store.queue(
                Job(
                    key(job.id, "reply"),
                    job.topic,
                    job.reply_agent,
                    f"Reply from {job.agent}: {outcome.summary}\nRead full report: {self.artifacts.relative(self.artifacts.directory(job.topic) / ('report-' + job.id + '.md'))}",
                    job.event_id,
                    job.round,
                )
            )
        destination = ", ".join(outcome.to) or job.reply_agent or "человек"
        self.store.notice(
            Notice(
                "result-" + job.id,
                self.general,
                job.agent,
                f"{job.agent} → {destination} · {job.topic}\n{outcome.summary}\n{link}",
                False,
                str(topic["root_event"]),
            )
        )
