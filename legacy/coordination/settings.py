from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .cli import AgentCLI


def mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(k, str) for k in value):
        raise ValueError("Expected a configuration mapping")
    return value


def string(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected a non-empty configuration string")
    return value


@dataclass(frozen=True)
class Account:
    user_id: str
    device_id: str
    access_token: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    project: Path
    database: Path
    homeserver: str
    verify_ssl: bool | str
    general: str
    escalations: str
    humans: set[str]
    accounts: dict[str, Account]
    agents: dict[str, AgentCLI]
    records_port: int

    @classmethod
    def load(cls, path: Path) -> "Settings":
        cfg = mapping(yaml.safe_load(path.read_text(encoding="utf-8")))
        account_file = path.parent / string(cfg.get("accounts_file"))
        legacy = mapping(yaml.safe_load(account_file.read_text(encoding="utf-8")))
        agent_config = mapping(legacy.get("agents"))
        overrides = mapping(cfg.get("agents", {}))
        agents, accounts = {}, {}
        for name, raw in agent_config.items():
            data = mapping(raw)
            command = data.get("command")
            if not isinstance(command, list) or not command:
                raise ValueError(f"Missing command for {name}")
            executable = string(command[0])
            if not Path(executable).is_file():
                raise ValueError(f"CLI path must name an existing file: {executable}")
            options = mapping(overrides.get(name, {}))
            agents[name] = AgentCLI(name, executable, str(options.get("model", "")))
            agents[name].command("")
            accounts[name] = Account(
                string(data.get("user_id")),
                string(data.get("device_id")),
                string(data.get("access_token")),
            )
        if not agents:
            raise ValueError("No agents configured")
        humans = cfg.get("human_users")
        if not isinstance(humans, list) or not humans:
            raise ValueError("human_users must list authorized human Matrix IDs")
        human_ids = {string(v) for v in humans}
        if human_ids.intersection(a.user_id for a in accounts.values()):
            raise ValueError("A bot cannot be a human decision authority")
        general, escalations = (
            string(cfg.get("general_room")),
            string(cfg.get("escalations_room")),
        )
        if (
            not general.startswith("!")
            or not escalations.startswith("!")
            or general == escalations
        ):
            raise ValueError("Configure two different internal room IDs")
        project = Path(string(cfg.get("project_root"))).resolve(strict=True)
        if not project.is_dir():
            raise ValueError("Project root is not a directory")
        verify = legacy.get("verify_ssl", True)
        if not isinstance(verify, (bool, str)):
            raise ValueError("Invalid verify_ssl")
        port = cfg.get("records_port", 8766)
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError("Invalid records_port")
        return cls(
            project,
            (path.parent / string(cfg.get("state_file"))).resolve(),
            string(legacy.get("homeserver_url")),
            verify,
            general,
            escalations,
            human_ids,
            accounts,
            agents,
            port,
        )
