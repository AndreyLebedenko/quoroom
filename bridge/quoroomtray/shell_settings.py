from . import settings

INSTANCE_MUTEX_NAME = "Local\\QuoroomTray"
ERROR_LOG = settings.BRIDGE_DIR / "state" / "tray-errors.log"
ICON_SIZE = 64
ICON_MARGIN = 4
NOTIFICATION_TITLE = settings.APP_NAME
ERROR_LOG_MAX_BYTES = 256 * 1024
