import asyncio
import json
import os
import signal
from dataclasses import dataclass
from pathlib import Path

from .model import RunResult


def object_value(text: str) -> dict[str, object]:
    value: object = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("CLI event is not an object")
    return value


def field(data: dict[str, object], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Missing CLI field: {name}")
    return value


def parse_result(provider: str, text: str) -> RunResult:
    if provider == "claude-code":
        data = object_value(text)
        if data.get("is_error") is not False:
            raise ValueError("Claude did not complete successfully")
        return RunResult(field(data, "session_id"), field(data, "result"))
    session, answer, complete = "", "", False
    for line in text.splitlines():
        if not line.strip():
            continue
        data = object_value(line)
        kind = data.get("type")
        if kind in {"error", "turn.failed"}:
            raise ValueError(f"{provider}: {line[:1000]}")
        if provider == "codex":
            if kind == "thread.started":
                session = field(data, "thread_id")
            if kind == "item.completed":
                item = data.get("item")
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    answer = field(item, "text")
            complete = complete or kind == "turn.completed"
        elif provider == "opencode":
            if isinstance(data.get("sessionID"), str):
                session = field(data, "sessionID")
            part = data.get("part")
            if isinstance(part, dict):
                if kind == "text":
                    answer += field(part, "text")
                complete = complete or (
                    kind == "step_finish" and part.get("reason") == "stop"
                )
        else:
            raise ValueError(f"Unknown CLI: {provider}")
    if not session or not answer.strip() or not complete:
        raise ValueError(f"Incomplete {provider} response")
    return RunResult(session, answer.strip())


@dataclass(frozen=True)
class AgentCLI:
    name: str
    executable: str
    model: str = ""
    timeout: float = 600

    def command(self, session: str) -> list[str]:
        if self.name == "claude-code":
            args = [
                "-p",
                "--output-format",
                "json",
                "--permission-mode",
                "auto",
                "--permission-prompts",
                "none",
            ]
            if session:
                args += ["--resume", session]
        elif self.name == "codex":
            args = ["exec", "--sandbox", "workspace-write"]
            if session:
                args += ["resume", session]
            args += ["--skip-git-repo-check", "--json", "-"]
        elif self.name == "opencode":
            args = ["run", "--format", "json"]
            if self.model:
                args += ["--model", self.model]
            if session:
                args += ["--session", session]
        else:
            raise ValueError(f"Unknown CLI: {self.name}")
        return [self.executable, *args]

    async def run(self, project: Path, prompt: str, session: str) -> RunResult:
        process = await asyncio.create_subprocess_exec(
            *self.command(session),
            cwd=project,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(prompt.encode("utf-8")), self.timeout
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            await terminate(process)
            raise
        if process.returncode != 0:
            raise RuntimeError(
                f"{self.name} exit={process.returncode}: {stderr.decode('utf-8', errors='replace')[-2000:]}"
            )
        result = parse_result(self.name, stdout.decode("utf-8"))
        if session and result.session != session:
            raise ValueError("CLI resumed a different session")
        return result


async def terminate(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if os.name == "nt":
        killer = await asyncio.create_subprocess_exec(
            "taskkill.exe",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, error = await killer.communicate()
        if killer.returncode != 0 and process.returncode is None:
            raise RuntimeError(f"Cannot stop CLI process tree: {output!r} {error!r}")
    else:
        os.killpg(process.pid, signal.SIGKILL)
    await process.communicate()
