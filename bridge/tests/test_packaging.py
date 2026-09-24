import importlib
import json
import os
import subprocess
import sys
import tomllib
import unittest
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent.parent
BROKER_ONLY_MODULES = ("nio", "yaml", "aiohttp")


def project_table() -> dict:
    with open(BRIDGE / "pyproject.toml", "rb") as source:
        return tomllib.load(source)["project"]


def requirements_txt_lines() -> set[str]:
    lines = (BRIDGE / "requirements.txt").read_text(encoding="utf-8").splitlines()
    return {
        line.replace(" ", "")
        for line in (raw.strip() for raw in lines)
        if line and not line.startswith("#")
    }


def broker_only_modules_loaded_by_importing(module: str) -> list[str]:
    probe = (
        f"import sys, json, {module}; "
        f"print(json.dumps([m for m in {list(BROKER_ONLY_MODULES)!r} "
        f"if m in sys.modules]))"
    )
    env = dict(os.environ, PYTHONPATH=str(BRIDGE))
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=BRIDGE,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


class AgentschatEntryPointTests(unittest.TestCase):
    def test_agentschat_script_entry_resolves_to_a_callable(self):
        target = project_table()["scripts"]["agentschat"]
        module_name, attribute = target.split(":")
        entry = getattr(importlib.import_module(module_name), attribute)
        self.assertTrue(callable(entry))


class BaseDependenciesServeOnlyTheClientTests(unittest.TestCase):
    def test_importing_the_client_in_a_fresh_interpreter_loads_no_broker_library(
        self,
    ):
        self.assertEqual(
            broker_only_modules_loaded_by_importing("sessionchat.client"), []
        )

    def test_the_fresh_interpreter_probe_does_see_broker_libraries_when_the_broker_is_imported(
        self,
    ):
        self.assertEqual(
            broker_only_modules_loaded_by_importing("sessionchat.broker"),
            list(BROKER_ONLY_MODULES),
        )

    def test_requests_is_the_only_base_dependency(self):
        self.assertEqual(project_table()["dependencies"], ["requests>=2.31.0"])


class BrokerExtraMatchesRequirementsTxtTests(unittest.TestCase):
    def test_every_broker_requirement_in_requirements_txt_is_in_the_broker_extra(
        self,
    ):
        project = project_table()
        broker_requirements = requirements_txt_lines() - set(project["dependencies"])
        missing = broker_requirements - set(project["optional-dependencies"]["broker"])
        self.assertEqual(missing, set())

    def test_broker_extra_declares_nothing_that_requirements_txt_lacks(self):
        extra = set(project_table()["optional-dependencies"]["broker"])
        self.assertEqual(extra - requirements_txt_lines(), set())

    def test_base_dependencies_are_all_listed_in_requirements_txt(self):
        base = set(project_table()["dependencies"])
        self.assertEqual(base - requirements_txt_lines(), set())


if __name__ == "__main__":
    unittest.main()
