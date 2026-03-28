import asyncio
import copy
from typing import Any
from uuid import uuid4

from aiohttp import web

from .base_transport import BaseTransport


class HttpTransport(BaseTransport):
    """
    HTTP-based transport for network clients.

    This transport accepts HTTP POST requests, converts them into request
    envelopes for the orchestrator, and uses request-scoped futures to deliver
    responses back to the correct waiting client.
    """

    def __init__(self, host: str, port: int, request_timeout_seconds: float) -> None:
        self.host = host
        self.port = port
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.request_queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self.pending_futures: dict[str, asyncio.Future[Any]] = {}

        self._app = web.Application()
        self._app.router.add_post("/", self.handle_http_request)
        self._runner = web.AppRunner(self._app)
        self._site: web.TCPSite | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return

        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return

        for future in list(self.pending_futures.values()):
            if not future.done():
                future.cancel()
        self.pending_futures.clear()

        await self._runner.cleanup()
        self._site = None
        self._started = False

    async def handle_http_request(self, request: web.Request) -> web.Response:
        try:
            json_data = await request.json()
        except Exception:
            return web.json_response(
                {"status": "blocked", "error": "INVALID_JSON"},
                status=400,
            )

        if not isinstance(json_data, dict):
            return web.json_response(
                {"status": "blocked", "error": "NON_OBJECT_JSON"},
                status=400,
            )

        request_id = f"req-{uuid4().hex}"
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self.pending_futures[request_id] = future

        await self.request_queue.put((request_id, json_data))

        try:
            safe_data = await asyncio.wait_for(
                future,
                timeout=self.request_timeout_seconds,
            )
        except asyncio.TimeoutError:
            self.pending_futures.pop(request_id, None)
            return web.json_response(
                {"status": "error", "error": "REQUEST_TIMEOUT"},
                status=504,
            )
        except asyncio.CancelledError:
            self.pending_futures.pop(request_id, None)
            raise
        except Exception:
            self.pending_futures.pop(request_id, None)
            return web.json_response(
                {"status": "error", "error": "INTERNAL_PROXY_ERROR"},
                status=500,
            )

        payload, status = self._build_http_response(safe_data)
        return web.json_response(payload, status=status)

    async def receive_request(self) -> tuple[Any | None, dict[str, Any]]:
        request_id, json_data = await self.request_queue.get()
        return request_id, json_data

    async def send_response(self, data: Any, request_id: Any | None = None) -> None:
        if request_id is None:
            raise ValueError("HttpTransport.send_response requires a request_id.")

        future = self.pending_futures.pop(request_id, None)
        if future is None:
            return

        if not future.done():
            future.set_result(data)

    def _build_http_response(self, data: Any) -> tuple[Any, int]:
        if not isinstance(data, dict):
            return data, 200

        payload = copy.deepcopy(data)

        explicit_status = payload.pop("_http_status", None)
        if isinstance(explicit_status, int):
            return payload, explicit_status

        error_code = payload.get("error")
        status_value = payload.get("status")

        if error_code in {"MALFORMED_REQUEST", "INVALID_JSON", "NON_OBJECT_JSON", "SCHEMA_VALIDATION_FAILED"}:
            return payload, 400

        if error_code in {"RBAC_DENIED", "PATH_TRAVERSAL"}:
            return payload, 403

        if error_code in {"REQUEST_TIMEOUT"}:
            return payload, 504

        if error_code in {"Internal proxy error", "INTERNAL_PROXY_ERROR"}:
            return payload, 500

        if status_value == "blocked":
            return payload, 403

        return payload, 200
