from aiohttp import web
from aiohttp.abc import AbstractAccessLogger


class AccessLogger(AbstractAccessLogger):
    def log(
        self, request: web.BaseRequest, response: web.StreamResponse, time: float
    ) -> None:
        self.logger.info(
            "%s %s status=%s duration=%.3fs",
            request.method,
            request.path,
            response.status,
            time,
        )
