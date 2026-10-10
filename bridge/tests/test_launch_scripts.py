import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.installer_fakes import SH, posix_path

# english-release-16: the start and stop scripts speak the room language

REPO = Path(__file__).resolve().parent.parent.parent
PWSH_51 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
    r"System32\WindowsPowerShell\v1.0\powershell.exe"
)
CYRILLIC = re.compile("[Ѐ-ӿ]")
PRINTABLE_ASCII = re.compile(r"^[\x20-\x7e]*$")
PLACEHOLDER = re.compile(r"\{\d\}|%s")
SECRET = "syt_launch_script_secret_token"
BROKER_PORT = 8770

RUSSIAN_START_PS1 = {
    "docker_missing": "docker не найден в PATH. Установите Docker Desktop (docs/INSTALL.md, шаг 0).",
    "docker_down": "Docker-демон не отвечает. Запустите Docker Desktop и повторите.",
    "no_env": "нет docker/.env - скопируйте docker/.env.example -> docker/.env (docs/INSTALL.md, шаг 3).",
    "no_venv": "нет окружения bridge/.venv - создайте его (docs/INSTALL.md, шаг 5).",
    "no_config": "нет bridge/config.yaml - скопируйте config.example.yaml и впишите токены (docs/INSTALL.md, шаг 7).",
    "stack_up": "==> Поднимаю Docker-стек (Continuwuity, Element, Caddy)...",
    "compose_failed": "docker compose up завершился с ошибкой.",
    "waiting": "==> Жду готовности Matrix-сервера (порт 443)...",
    "port_443": "443 не отвечает за 60с. Проверьте: docker compose -f docker/docker-compose.yml logs continuwuity",
    "already_running": "==> Брокер уже работает (PID {0}) - второй не запускаю.",
    "port_busy": "порт {0} занят, но pid-файла нет - его держит чужой процесс. Остановите прежний брокер и повторите.",
    "starting": "==> Запускаю брокер (лог: bridge/broker.log)...",
    "exited": "брокер завершился при старте. Из лога:`n  {0}`n(полный лог: bridge/broker.log)",
    "ready": "==> Брокер готов (PID {0}, порт {1}).",
    "no_port": "брокер не открыл порт {0} за 10с. Смотрите bridge/broker.log.",
    "done": "Готово. Element Web: https://agentschat.local",
    "next": r"Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: .\stop.ps1",
    "follow": "==> Лог брокера (Ctrl+C - выйти, стенд останется поднятым):",
}
RUSSIAN_STOP_PS1 = {
    "stopping_broker": "==> Останавливаю брокер (PID {0})...",
    "stopping_found": "==> Останавливаю брокер (PID {0}, найден по командной строке)...",
    "not_running": "==> Брокер не запущен.",
    "docker_kept": "==> Docker-контейнеры оставлены поднятыми (-KeepDocker).",
    "no_docker": "docker не найден - контейнеры не тронуты.",
    "stopping_docker": "==> Опускаю Docker-стек (тома с данными сохраняются)...",
    "down_failed": "docker compose down вернул код {0} (возможно, демон не запущен).",
    "done": "Готово.",
}
RUSSIAN_START_SH = {
    "error_label": "ОШИБКА",
    "docker_missing": "docker не найден (docs/INSTALL.md, шаг 0).",
    "docker_down": "Docker-демон не отвечает. Запустите Docker.",
    "no_env": "нет docker/.env (docs/INSTALL.md, шаг 3).",
    "no_config": "нет bridge/config.yaml (docs/INSTALL.md, шаг 7).",
    "stack_up": "==> Поднимаю Docker-стек (Continuwuity, Element, Caddy)...",
    "waiting": "==> Жду готовности Matrix-сервера (порт 443)...",
    "already_running": "==> Брокер уже работает (PID %s) - второй не запускаю.",
    "starting": "==> Запускаю брокер (лог: bridge/broker.log)...",
    "started": "==> Брокер запущен (PID %s, порт %s).",
    "all_done": "Готово. Element Web: https://agentschat.local",
    "next_step": "Дальше в каждой сессии CLI вызвать /chatlogin. Остановить всё: ./stop.sh",
}
RUSSIAN_STOP_SH = {
    "stopping_broker": "==> Останавливаю брокер (PID %s)...",
    "stopping_found": "==> Останавливаю брокер по командной строке: %s",
    "not_running": "==> Брокер не запущен.",
    "docker_kept": "==> Docker оставлен поднятым.",
    "stopping_docker": "==> Опускаю Docker-стек (тома с данными сохраняются)...",
    "down_failed": "ПРЕДУПРЕЖДЕНИЕ: docker compose down вернул ошибку (возможно, демон не запущен).",
    "all_done": "Готово.",
}

CONFIG_FOR_LANGUAGES = (
    (None, [], "en"),
    ("", [], "en"),
    ("language: en\n", [], "en"),
    ("language: ru\n", [], "ru"),
    ('language: "ru"\n', [], "ru"),
    ("language: 'ru'\n", [], "ru"),
    ("language: ru # the room speaks Russian\n", [], "ru"),
    ("language: ru\r\nhomeserver_url: x\r\n", [], "ru"),
    ("homeserver_url: x\nlanguage: ru\n", [], "ru"),
    ("language: fr\n", [], "en"),
    ("language: RU\n", [], "en"),
    ("language:\n", [], "en"),
    ("  language: ru\n", [], "en"),
    ("homeserver_url: x\n", [], "en"),
    ("language: en\n", ["--lang", "ru"], "ru"),
    ("language: en\n", ["--lang=ru"], "ru"),
    ("language: ru\n", ["--lang", "en"], "en"),
    ("language: ru\n", ["--lang=en"], "en"),
    ("language: ru\n", ["--lang", "xx"], "en"),
    ("language: ru\n", ["--lang", "RU"], "en"),
    ("language: ru\n", ["--lang"], "en"),
    ("language: ru\n", ["--lang="], "en"),
    (None, ["--lang", "ru"], "ru"),
)

SHORT_MATRIX = (
    (None, [], "en"),
    ("language: ru\n", [], "ru"),
    ("language: fr\n", [], "en"),
    ("language: en\n", ["--lang", "ru"], "ru"),
    ("language: ru\n", ["--lang=en"], "en"),
    ("language: ru\n", ["--lang", "xx"], "en"),
)

REFUSALS = (
    "docker_missing",
    "docker_down",
    "no_env",
    "no_venv",
    "no_config",
    "compose_failed",
    "port_busy",
)

CALLER = """\
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$target = $args[0]
$rest = @($args | Select-Object -Skip 1)
function docker {
    $code = 0
    if ($args[0] -eq 'info') { $code = [int]$env:FAKE_DOCKER_INFO }
    elseif ($args[1] -eq 'up') { $code = [int]$env:FAKE_DOCKER_UP }
    elseif ($args[1] -eq 'down') { $code = [int]$env:FAKE_DOCKER_DOWN }
    cmd /c "exit $code"
}
if ($env:FAKE_DOCKER_ABSENT) { Remove-Item function:docker }
function Start-Sleep { }
function Get-CimInstance {
    [CmdletBinding()]
    param($ClassName, $Filter)
    $brokers = @($env:FAKE_BROKER_PID)
    if ($env:FAKE_PID_FILE) { $brokers += $PID }
    foreach ($id in $brokers) {
        if ($id -and $Filter -eq "ProcessId = $id") {
            [pscustomobject]@{ ProcessId = [int]$id; CommandLine = 'python -X utf8 -m sessionchat.broker' }
        }
    }
}
function Start-Process { throw 'Start-Process must not run in a test' }
if ($env:FAKE_PID_FILE) {
    New-Item -ItemType Directory -Force -Path (Split-Path $env:FAKE_PID_FILE) | Out-Null
    "$PID" | Out-File -FilePath $env:FAKE_PID_FILE -Encoding ascii
}
& $target SWITCHES @rest
exit $LASTEXITCODE
"""

DOCKER_SHIM = """\
#!/bin/sh
case "$1" in
    info) exit "${FAKE_DOCKER_INFO:-0}" ;;
    compose)
        case "$2" in
            up) exit "${FAKE_DOCKER_UP:-0}" ;;
            down) exit "${FAKE_DOCKER_DOWN:-0}" ;;
        esac
        ;;
esac
exit 0
"""

WRAPPER = """\
#!/bin/sh
echo $$ >"$1"
shift
exec "$@"
"""

SLEEPER_WRAPPER = """\
#!/bin/sh
sleep 60 &
echo $! >"$1"
shift
exec "$@"
"""

STUB_BROKER = "print('stub broker')\n"


def windows() -> str | None:
    return None if PWSH_51.is_file() else f"no Windows PowerShell 5.1: {PWSH_51}"


def shell() -> str | None:
    return None if SH else "posix sh not found in PATH"


def with_values(text: str, *values: object) -> str:
    placeholders = PLACEHOLDER.findall(text)
    if not placeholders:
        return text
    if placeholders[0] == "%s":
        return text % values
    return text.format(*values)


def pattern_of(text: str) -> re.Pattern:
    escaped = re.escape(text)
    return re.compile(re.sub(r"\\\{\d\\\}", lambda _: r"(\d+)", escaped))


def powershell_tables(name: str) -> tuple[dict[str, str], dict[str, str]]:
    source = (REPO / name).read_text(encoding="utf-8-sig")
    blocks = re.findall(r"\$texts = @\{\r?\n(.*?)\r?\n    \}", source, re.S)
    assert len(blocks) == 2, name
    tables = []
    for block in blocks:
        table = {}
        for line in block.splitlines():
            match = re.match(r"\s*(\w+)\s*=\s*(['\"])(.*)\2\s*$", line)
            assert match, line
            table[match.group(1)] = match.group(3)
        tables.append(table)
    return tables[0], tables[1]


def posix_tables(name: str) -> tuple[dict[str, str], dict[str, str]]:
    source = (REPO / name).read_text(encoding="utf-8")
    start = source.index('if [ "$language" = "ru" ]; then')
    middle = source.index("\nelse\n", start)
    end = source.index("\nfi\n", middle)
    tables = []
    for block in (source[start:middle], source[middle:end]):
        table = {}
        for line in block.splitlines():
            match = re.match(r'\s+(\w+)="(.*)"$', line)
            if match:
                table[match.group(1)] = match.group(2)
        tables.append(table)
    return tables[0], tables[1]


class TablesCase(unittest.TestCase):
    def check_tables(self, russian, english, pinned):
        self.assertEqual(russian, pinned)
        self.assertEqual(set(russian), set(english))
        for key in russian:
            with self.subTest(key=key):
                self.assertEqual(
                    sorted(PLACEHOLDER.findall(russian[key])),
                    sorted(PLACEHOLDER.findall(english[key])),
                )
                self.assertIsNone(CYRILLIC.search(english[key]), english[key])
                self.assertRegex(english[key], PRINTABLE_ASCII)


class MessageTableTests(TablesCase):
    def test_the_russian_messages_of_start_ps1_are_what_it_printed_before(self):
        russian, english = powershell_tables("start.ps1")
        self.check_tables(russian, english, RUSSIAN_START_PS1)

    def test_the_russian_messages_of_stop_ps1_are_what_it_printed_before(self):
        russian, english = powershell_tables("stop.ps1")
        self.check_tables(russian, english, RUSSIAN_STOP_PS1)

    def test_the_russian_messages_of_start_sh_are_what_it_printed_before(self):
        russian, english = posix_tables("start.sh")
        self.check_tables(russian, english, RUSSIAN_START_SH)

    def test_the_russian_messages_of_stop_sh_are_what_it_printed_before(self):
        russian, english = posix_tables("stop.sh")
        self.check_tables(russian, english, RUSSIAN_STOP_SH)


class ScriptTextTests(unittest.TestCase):
    def test_the_windows_scripts_are_saved_with_a_bom_for_powershell_51(self):
        for script in ("start.ps1", "stop.ps1"):
            with self.subTest(script=script):
                raw = (REPO / script).read_bytes()
                self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), script)

    def test_the_windows_scripts_have_no_construct_that_powershell_51_lacks(self):
        for script in ("start.ps1", "stop.ps1"):
            source = (REPO / script).read_text(encoding="utf-8-sig")
            for banned in ("&&", "||", "?? ", "?:", "?->"):
                with self.subTest(script=script, banned=banned):
                    self.assertNotIn(banned, source)

    def test_the_windows_scripts_have_no_cyrillic_outside_the_russian_table(self):
        for script in ("start.ps1", "stop.ps1"):
            source = (REPO / script).read_text(encoding="utf-8-sig")
            start = source.index("if ($language -ceq 'ru') {")
            end = source.index("} else {", start)
            outside = source[:start] + source[end:]
            with self.subTest(script=script):
                self.assertIsNone(CYRILLIC.search(outside))

    def test_the_posix_scripts_have_no_cyrillic_outside_the_russian_table(self):
        for script in ("start.sh", "stop.sh"):
            source = (REPO / script).read_text(encoding="utf-8")
            start = source.index('if [ "$language" = "ru" ]; then')
            end = source.index("\nelse\n", start)
            outside = source[:start] + source[end:]
            with self.subTest(script=script):
                self.assertIsNone(CYRILLIC.search(outside))

    def test_the_windows_scripts_keep_comments_only_in_their_help(self):
        for script in ("start.ps1", "stop.ps1"):
            source = (REPO / script).read_text(encoding="utf-8-sig")
            code = re.sub(r"<#.*?#>", "", source, count=1, flags=re.S)
            for line in code.splitlines():
                with self.subTest(script=script, line=line):
                    self.assertFalse(
                        line.strip().startswith("#") and "#Requires" not in line, line
                    )

    def test_the_posix_scripts_keep_comments_only_in_their_header(self):
        for script in ("start.sh", "stop.sh"):
            lines = (REPO / script).read_text(encoding="utf-8").splitlines()
            body = lines[next(i for i, v in enumerate(lines) if v.startswith("set ")) :]
            for line in body:
                with self.subTest(script=script, line=line):
                    self.assertFalse(line.strip().startswith("#"), line)

    def test_the_posix_scripts_are_valid_posix_sh_without_bashisms(self):
        for script in ("start.sh", "stop.sh"):
            source = (REPO / script).read_text(encoding="utf-8")
            for banned in (
                r"\[\[(?!:)",
                r"(?<!:)\]\]",
                r"function ",
                r"source ",
                r"local ",
                r"(?<![=-])==(?!>)",
            ):
                with self.subTest(script=script, banned=banned):
                    self.assertIsNone(re.search(banned, source))
            if SH:
                done = subprocess.run(
                    [SH, "-n", posix_path(REPO / script)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(done.returncode, 0, done.stderr)


class PowerShellCase(unittest.TestCase):
    script = ""

    def setUp(self):
        skipped = windows()
        if skipped:
            self.skipTest(skipped)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.root = self.tmp / "Quoroom stand"
        self.stand()

    def stand(self, env_file=True, venv=True):
        (self.root / "docker").mkdir(parents=True)
        (self.root / "bridge" / "state").mkdir(parents=True)
        shutil.copy(REPO / self.script, self.root / self.script)
        if env_file:
            (self.root / "docker" / ".env").write_text("X=1\n", encoding="utf-8")
        if venv:
            python = self.root / "bridge" / ".venv" / "Scripts" / "python.exe"
            python.parent.mkdir(parents=True)
            python.write_text("", encoding="utf-8")

    def write_config(self, text: str | None) -> None:
        path = self.root / "bridge" / "config.yaml"
        if text is not None:
            path.write_bytes(
                (text + f'bots:\n  - access_token: "{SECRET}"\n').encode("utf-8")
            )

    def run_script(self, args, switches="", absent=False, **faults) -> tuple[int, str]:
        caller = self.tmp / "caller.ps1"
        caller.write_text(CALLER.replace("SWITCHES", switches), encoding="utf-8-sig")
        if absent:
            empty = self.tmp / "empty"
            empty.mkdir(exist_ok=True)
            env = {
                "SystemRoot": os.environ.get("SystemRoot", r"C:\Windows"),
                "PATH": str(empty),
                "FAKE_DOCKER_ABSENT": "1",
            }
        else:
            env = dict(os.environ)
        env.update({name: str(value) for name, value in faults.items()})
        done = subprocess.run(
            [
                str(PWSH_51),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(caller),
                str(self.root / self.script),
                *args,
            ],
            cwd=self.tmp,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return done.returncode, done.stdout.replace("\ufeff", "") + done.stderr


class StartPowerShellTests(PowerShellCase):
    script = "start.ps1"

    def setUp(self):
        super().setUp()
        self.russian, self.english = powershell_tables(self.script)

    def hold_the_broker_port(self):
        holder = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.addCleanup(holder.close)
        try:
            holder.bind(("127.0.0.1", BROKER_PORT))
            holder.listen(1)
        except OSError:
            pass

    def refuse(self, name, args):
        shutil.rmtree(self.root, ignore_errors=True)
        self.stand(env_file=name != "no_env", venv=name != "no_venv")
        if name != "no_config":
            self.write_config("language: en\n")
        if name == "port_busy":
            self.hold_the_broker_port()
        faults = {
            "docker_down": dict(FAKE_DOCKER_INFO=1),
            "compose_failed": dict(FAKE_DOCKER_UP=1),
        }.get(name, {})
        return self.run_script(args, absent=name == "docker_missing", **faults)

    def test_every_refusal_is_printed_in_english_by_default(self):
        for name in REFUSALS:
            with self.subTest(name=name):
                code, said = self.refuse(name, [])
                self.assertEqual(code, 1, said)
                self.assertIn(
                    f"ERROR: {with_values(self.english[name], BROKER_PORT)}", said
                )
                self.assertIsNone(CYRILLIC.search(said), said)

    def test_every_refusal_is_printed_in_russian_on_request(self):
        for name in REFUSALS:
            with self.subTest(name=name):
                code, said = self.refuse(name, ["--lang", "ru"])
                self.assertEqual(code, 1, said)
                self.assertIn(
                    f"ОШИБКА: {with_values(self.russian[name], BROKER_PORT)}", said
                )

    def test_the_language_comes_from_the_flag_then_the_config_then_english(self):
        for config, args, wanted in CONFIG_FOR_LANGUAGES:
            with self.subTest(config=config, args=args):
                shutil.rmtree(self.root, ignore_errors=True)
                self.stand()
                self.write_config(config)
                code, said = self.run_script(args, FAKE_DOCKER_INFO=1)
                table = self.russian if wanted == "ru" else self.english
                label = "ОШИБКА" if wanted == "ru" else "ERROR"
                self.assertEqual(code, 1, said)
                self.assertIn(f"{label}: {table['docker_down']}", said)
                self.assertNotIn(SECRET, said)

    def test_a_running_broker_is_not_started_twice_and_the_progress_is_told(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                shutil.rmtree(self.root, ignore_errors=True)
                self.stand()
                self.write_config("language: en\n")
                pid_file = self.root / "bridge" / "state" / "broker.pid"
                code, said = self.run_script(["--lang", lang], FAKE_PID_FILE=pid_file)
                self.assertNotIn("Start-Process must not run", said)
                wanted = [
                    pattern_of(table["stack_up"]),
                    pattern_of(table["waiting"]),
                    pattern_of(table["already_running"]),
                    pattern_of(table["done"]),
                    pattern_of(table["next"]),
                ]
                position = 0
                for expected in wanted:
                    found = expected.search(said, position)
                    self.assertIsNotNone(found, f"{expected.pattern}\n{said}")
                    position = found.end()
                self.assertNotIn(table["starting"], said)
                if lang == "en":
                    self.assertIsNone(CYRILLIC.search(said), said)


class StopPowerShellTests(PowerShellCase):
    script = "stop.ps1"

    def setUp(self):
        super().setUp()
        self.russian, self.english = powershell_tables(self.script)

    def test_the_stand_is_stopped_in_the_language_of_the_flag_or_the_config(self):
        for config, args, wanted in SHORT_MATRIX:
            with self.subTest(config=config, args=args):
                shutil.rmtree(self.root, ignore_errors=True)
                self.stand()
                self.write_config(config)
                code, said = self.run_script(args, switches="-KeepDocker")
                table = self.russian if wanted == "ru" else self.english
                for key in ("not_running", "docker_kept", "done"):
                    self.assertIn(table[key], said)
                self.assertNotIn(SECRET, said)
                if wanted == "en":
                    self.assertIsNone(CYRILLIC.search(said), said)

    def test_a_broker_found_by_its_pid_file_is_stopped_and_told_about(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                sleeper = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(60)"]
                )
                self.addCleanup(sleeper.kill)
                pid_file = self.root / "bridge" / "state" / "broker.pid"
                pid_file.write_text(str(sleeper.pid), encoding="ascii")
                code, said = self.run_script(
                    ["--lang", lang],
                    switches="-KeepDocker",
                    FAKE_BROKER_PID=sleeper.pid,
                )
                self.assertIn(with_values(table["stopping_broker"], sleeper.pid), said)
                self.assertNotIn(table["not_running"], said)
                sleeper.wait(timeout=20)
                self.assertFalse(pid_file.exists())

    def test_a_pid_file_that_is_not_a_number_is_removed_without_a_crash(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                pid_file = self.root / "bridge" / "state" / "broker.pid"
                pid_file.write_text("12 34", encoding="ascii")
                code, said = self.run_script(["--lang", lang], switches="-KeepDocker")
                self.assertEqual(code, 0, said)
                self.assertIn(table["not_running"], said)
                self.assertFalse(pid_file.exists())

    def test_a_pid_file_naming_another_process_leaves_that_process_alone(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                bystander = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(60)"]
                )
                self.addCleanup(bystander.kill)
                pid_file = self.root / "bridge" / "state" / "broker.pid"
                pid_file.write_text(str(bystander.pid), encoding="ascii")
                code, said = self.run_script(["--lang", lang], switches="-KeepDocker")
                self.assertIsNone(bystander.poll(), said)
                self.assertIn(table["not_running"], said)
                self.assertFalse(pid_file.exists())

    def test_the_docker_stack_is_brought_down_and_a_failure_is_a_warning(self):
        for lang, table, label in (
            ("en", self.english, "WARNING"),
            ("ru", self.russian, "ПРЕДУПРЕЖДЕНИЕ"),
        ):
            with self.subTest(lang=lang):
                code, said = self.run_script(["--lang", lang])
                self.assertIn(table["stopping_docker"], said)
                self.assertNotIn(label, said)
                code, said = self.run_script(["--lang", lang], FAKE_DOCKER_DOWN=3)
                self.assertIn(f"{label}: {with_values(table['down_failed'], 3)}", said)

    def test_a_missing_docker_is_a_warning_not_a_failure(self):
        for lang, table, label in (
            ("en", self.english, "WARNING"),
            ("ru", self.russian, "ПРЕДУПРЕЖДЕНИЕ"),
        ):
            with self.subTest(lang=lang):
                code, said = self.run_script(["--lang", lang], absent=True)
                self.assertEqual(code, 0, said)
                self.assertIn(f"{label}: {table['no_docker']}", said)


class HelpTests(unittest.TestCase):
    def test_the_comment_based_help_is_in_english(self):
        skipped = windows()
        if skipped:
            self.skipTest(skipped)
        for script, phrase in (
            ("start.ps1", "Starts the Docker infrastructure"),
            ("stop.ps1", "Stop only the broker"),
        ):
            with self.subTest(script=script):
                done = subprocess.run(
                    [
                        str(PWSH_51),
                        "-NoProfile",
                        "-Command",
                        f"Get-Help -Full -Name '{REPO / script}'",
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertIn(phrase, " ".join(done.stdout.split()))
                self.assertIsNone(CYRILLIC.search(done.stdout))


class PosixCase(unittest.TestCase):
    script = ""

    def setUp(self):
        skipped = shell()
        if skipped:
            self.skipTest(skipped)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        self.root = self.tmp / "Quoroom stand"
        (self.root / "docker").mkdir(parents=True)
        (self.root / "bridge" / "state").mkdir(parents=True)
        (self.root / "bridge" / "sessionchat").mkdir(parents=True)
        (self.root / "bridge" / "sessionchat" / "__init__.py").write_text("")
        (self.root / "bridge" / "sessionchat" / "broker.py").write_text(STUB_BROKER)
        shutil.copy(REPO / self.script, self.root / self.script)
        (self.root / "docker" / ".env").write_text("X=1\n", encoding="utf-8")
        self.shims = self.tmp / "shims"
        self.shims.mkdir()

    def executable(self, directory: Path, name: str, body: str) -> Path:
        path = directory / name
        path.write_text(body, encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)
        return path

    def dirname_tool(self) -> Path:
        directory = self.tmp / "dirname-tool"
        directory.mkdir(exist_ok=True)
        self.executable(
            directory,
            "dirname",
            '#!/bin/sh\ncase "$1" in\n  */*) printf "%s\\n" "${1%/*}" ;;\n'
            '  *) printf "%s\\n" "." ;;\nesac\n',
        )
        return directory

    def write_config(self, text: str | None) -> None:
        path = self.root / "bridge" / "config.yaml"
        if path.exists():
            path.unlink()
        if text is not None:
            path.write_bytes(
                (text + f'bots:\n  - access_token: "{SECRET}"\n').encode("utf-8")
            )

    def environment(self, with_docker=True, **faults) -> dict[str, str]:
        if with_docker:
            self.executable(self.shims, "docker", DOCKER_SHIM)
        self.executable(self.shims, "pgrep", "#!/bin/sh\nexit 1\n")
        self.executable(self.shims, "curl", "#!/bin/sh\nexit 0\n")
        self.executable(
            self.shims,
            "python3",
            f'#!/bin/sh\nexec "{posix_path(Path(sys.executable))}" "$@"\n',
        )
        utilities = Path(shutil.which("cat") or "/usr/bin/cat").parent
        env = {
            "PATH": os.pathsep.join(
                [
                    posix_path(self.shims),
                    posix_path(self.dirname_tool()),
                    posix_path(utilities),
                ]
            ),
            "FAKE_DOCKER_INFO": "0",
            "FAKE_DOCKER_UP": "0",
            "FAKE_DOCKER_DOWN": "0",
        }
        env.update({name: str(value) for name, value in faults.items()})
        return env

    def bare_environment(self) -> dict[str, str]:
        return {"PATH": posix_path(self.dirname_tool())}

    def run_script(
        self, args, env, wrapper: str | None = None, pid_file: Path | None = None
    ) -> tuple[int, str]:
        script = posix_path(self.root / self.script)
        argv = [SH, script, *args]
        if wrapper:
            helper = self.executable(self.tmp, "wrapper.sh", wrapper)
            argv = [
                SH,
                posix_path(helper),
                posix_path(pid_file),
                posix_path(Path(SH)),
                script,
                *args,
            ]
        done = subprocess.run(
            argv,
            cwd=str(self.tmp),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return done.returncode, done.stdout + done.stderr


class StartPosixTests(PosixCase):
    script = "start.sh"

    def setUp(self):
        super().setUp()
        self.russian, self.english = posix_tables(self.script)

    def refusal_run(self, name, args):
        if name == "docker_missing":
            return self.run_script(args, self.bare_environment())
        self.write_config("language: en\n")
        if name == "docker_down":
            return self.run_script(args, self.environment(FAKE_DOCKER_INFO=1))
        if name == "no_env":
            (self.root / "docker" / ".env").unlink()
            return self.run_script(args, self.environment())
        self.write_config(None)
        return self.run_script(args, self.environment())

    def test_every_refusal_is_printed_in_english_by_default(self):
        for name in ("docker_missing", "docker_down", "no_env", "no_config"):
            with self.subTest(name=name):
                self.setUp()
                code, said = self.refusal_run(name, [])
                self.assertEqual(code, 1, said)
                self.assertIn(f"ERROR: {self.english[name]}", said)
                self.assertIsNone(CYRILLIC.search(said), said)

    def test_every_refusal_is_printed_in_russian_on_request(self):
        for name in ("docker_missing", "docker_down", "no_env", "no_config"):
            with self.subTest(name=name):
                self.setUp()
                code, said = self.refusal_run(name, ["--lang", "ru"])
                self.assertEqual(code, 1, said)
                self.assertIn(f"ОШИБКА: {self.russian[name]}", said)

    def test_the_language_comes_from_the_flag_then_the_config_then_english(self):
        for config, args, wanted in CONFIG_FOR_LANGUAGES:
            with self.subTest(config=config, args=args):
                self.write_config(config)
                code, said = self.run_script(args, self.environment(FAKE_DOCKER_INFO=1))
                table = self.russian if wanted == "ru" else self.english
                label = "ОШИБКА" if wanted == "ru" else "ERROR"
                self.assertEqual(code, 1, said)
                self.assertIn(f"{label}: {table['docker_down']}", said)
                self.assertNotIn(SECRET, said)

    def test_a_running_broker_is_not_started_twice_and_the_progress_is_told(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                self.write_config("language: en\n")
                pid_file = self.root / "bridge" / "state" / "broker.pid"
                code, said = self.run_script(
                    ["--lang", lang],
                    self.environment(),
                    wrapper=WRAPPER,
                    pid_file=pid_file,
                )
                self.assertEqual(code, 0, said)
                wanted = [
                    table["stack_up"],
                    table["waiting"],
                    table["already_running"].split("%s")[0],
                    table["all_done"],
                    table["next_step"],
                ]
                position = 0
                for expected in wanted:
                    found = said.find(expected, position)
                    self.assertNotEqual(found, -1, f"{expected}\n{said}")
                    position = found
                self.assertNotIn(table["starting"], said)

    def test_a_fresh_broker_is_started_and_the_progress_is_told(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                self.write_config("language: en\n")
                pid_file = self.root / "bridge" / "state" / "broker.pid"
                if pid_file.exists():
                    pid_file.unlink()
                code, said = self.run_script(["--lang", lang], self.environment())
                self.assertEqual(code, 0, said)
                self.assertTrue(pid_file.is_file())
                started = pid_file.read_text(encoding="utf-8").strip()
                lines = said.splitlines()
                self.assertEqual(
                    lines,
                    [
                        table["stack_up"],
                        table["waiting"],
                        table["starting"],
                        table["started"] % (started, BROKER_PORT),
                        "",
                        table["all_done"],
                        table["next_step"],
                    ],
                )
                if lang == "en":
                    self.assertIsNone(CYRILLIC.search(said), said)


class StopPosixTests(PosixCase):
    script = "stop.sh"

    def setUp(self):
        super().setUp()
        self.russian, self.english = posix_tables(self.script)

    def test_the_stand_is_stopped_in_the_language_of_the_flag_or_the_config(self):
        for config, args, wanted in CONFIG_FOR_LANGUAGES:
            with self.subTest(config=config, args=args):
                self.write_config(config)
                code, said = self.run_script(
                    [*args, "--keep-docker"], self.environment()
                )
                table = self.russian if wanted == "ru" else self.english
                self.assertEqual(
                    said.splitlines(),
                    [table["not_running"], table["docker_kept"], table["all_done"]],
                )
                self.assertNotIn(SECRET, said)

    def test_the_keep_docker_flag_may_come_before_or_after_the_language(self):
        for args in (
            ["--keep-docker", "--lang", "ru"],
            ["--lang", "ru", "--keep-docker"],
            ["--lang=ru", "--keep-docker"],
        ):
            with self.subTest(args=args):
                code, said = self.run_script(args, self.environment())
                self.assertIn(self.russian["docker_kept"], said)
                self.assertNotIn(self.russian["stopping_docker"], said)

    def test_the_stack_is_brought_down_and_a_failure_is_a_warning(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                code, said = self.run_script(["--lang", lang], self.environment())
                self.assertEqual(
                    said.splitlines(),
                    [table["not_running"], table["stopping_docker"], table["all_done"]],
                )
                code, said = self.run_script(
                    ["--lang", lang], self.environment(FAKE_DOCKER_DOWN=3)
                )
                self.assertIn(table["down_failed"], said)

    def test_a_broker_found_by_its_pid_file_is_stopped_and_told_about(self):
        for lang, table in (("en", self.english), ("ru", self.russian)):
            with self.subTest(lang=lang):
                pid_file = self.root / "bridge" / "state" / "broker.pid"
                code, said = self.run_script(
                    ["--lang", lang, "--keep-docker"],
                    self.environment(),
                    wrapper=SLEEPER_WRAPPER,
                    pid_file=pid_file,
                )
                self.assertEqual(code, 0, said)
                self.assertIn(table["stopping_broker"].split("%s")[0], said)
                self.assertNotIn(table["not_running"], said)
                self.assertFalse(pid_file.exists())


if __name__ == "__main__":
    unittest.main()
