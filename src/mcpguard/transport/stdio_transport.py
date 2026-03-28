import asyncio
import json
import sys
from typing import Any

from .base_transport import BaseTransport

class StdioTransport(BaseTransport):
    """Production-style stdio transport for machine-to-machine communication."""

    def __init__(self) -> None:
        self._write_lock = asyncio.Lock()

    async def receive_request(self) -> tuple[Any | None, dict[str, Any]]:
        raw_input = await asyncio.to_thread(sys.stdin.readline)

        # EOF means the client closed stdin; reuse the existing orchestrator exit path.
        if raw_input == "":
            return None, {"tool": "exit"}

        raw_input = raw_input.strip()

        if not raw_input:
            return None, {
                "_transport_error": {
                    "code": "EMPTY_INPUT",
                    "raw_input": "",
                }
            }

        try:
            request = json.loads(raw_input)
        except json.JSONDecodeError as exc:
            return None, {
                "_transport_error": {
                    "code": "INVALID_JSON",
                    "raw_input": raw_input,
                    "details": str(exc),
                }
            }

        if isinstance(request, dict):
            return request.get("id"), request

        return None, {
            "_transport_error": {
                "code": "NON_OBJECT_JSON",
                "raw_input": request,
            }
        }

    async def send_response(self, data: Any, request_id: Any | None = None) -> None:
        response_payload = data

        if request_id is not None:
            if isinstance(data, dict):
                response_payload = dict(data)
                response_payload["id"] = request_id
            else:
                response_payload = {"id": request_id, "result": data}

        payload = json.dumps(response_payload, default=str, separators=(",", ":"))

        async with self._write_lock:
            await asyncio.to_thread(sys.stdout.write, payload + "\n")
            await asyncio.to_thread(sys.stdout.flush)
