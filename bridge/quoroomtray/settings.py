from pathlib import Path

APP_NAME = "Quoroom"
ELEMENT_URL = "https://agentschat.local/"

STACK_HOST = "127.0.0.1"
STACK_PORT = 443
BROKER_STATUS_URL = "http://127.0.0.1:8770/status"

POLL_INTERVAL_SECONDS = 5
PORT_TIMEOUT_SECONDS = 1.0
STATUS_TIMEOUT_SECONDS = 2.0
TOOLTIP_LIMIT = 127
MENU_ITEM_LIMIT = 64

BRIDGE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BRIDGE_DIR.parent
START_SCRIPT = REPO_ROOT / "start.ps1"
STOP_SCRIPT = REPO_ROOT / "stop.ps1"
BROKER_LOG = BRIDGE_DIR / "broker.log"
CONFIG_FILE = BRIDGE_DIR / "config.yaml"

PYTHONW = BRIDGE_DIR / ".venv" / "Scripts" / "pythonw.exe"
AUTOSTART_SHORTCUT_NAME = "Quoroom Tray.lnk"
AUTOSTART_ARGUMENTS = "-m quoroomtray"
AUTOSTART_DESCRIPTION = "Quoroom tray launcher"
STARTUP_FOLDER_UNDER_APPDATA = Path("Microsoft/Windows/Start Menu/Programs/Startup")

LOGIN_RULE_WINDOW_SECONDS = 300
LOGIN_RULE_CONFIRMING_POLLS = 2
