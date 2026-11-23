import http.client
import socket
import urllib.request
from collections.abc import Callable
from contextlib import closing
from typing import Any

from . import settings
from .broker_status import parse_sessions
from .observation import Observation, SessionLine

Connect = Callable[[tuple[str, int], float], Any]
Fetch = Callable[[str, float], bytes]


def fetch_body(url: str, timeout: float) -> bytes:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return response.read()


class StandProbes:
    def __init__(
        self,
        connect: Connect = socket.create_connection,
        fetch: Fetch = fetch_body,
    ):
        self._connect = connect
        self._fetch = fetch

    def stack_answers(self) -> bool:
        address = (settings.STACK_HOST, settings.STACK_PORT)
        try:
            with closing(self._connect(address, settings.PORT_TIMEOUT_SECONDS)):
                return True
        except OSError:
            return False

    def broker_sessions(self) -> tuple[SessionLine, ...] | None:
        try:
            body = self._fetch(
                settings.BROKER_STATUS_URL, settings.STATUS_TIMEOUT_SECONDS
            )
        except (OSError, http.client.HTTPException, ValueError):
            return None
        return parse_sessions(body)

    def observe(self) -> Observation:
        return Observation(self.stack_answers(), self.broker_sessions())
