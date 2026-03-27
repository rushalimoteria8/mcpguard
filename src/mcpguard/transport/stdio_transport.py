import asyncio
import json
import sys
from typing import Any

from .base_transport import BaseTransport

class StdioTransport(BaseTransport):
    """Production-style stdio transport for machine-to-machine communication."""

    async def receive_request(self) -> dict:
        raw_input = await asyncio.to_thread(sys.stdin.readline)

        # EOF means the client closed stdin; reuse the existing orchestrator exit path.
        if raw_input == "":
            return {"tool": "exit"}

        raw_input = raw_input.strip()

        if not raw_input:
            return {
                "_transport_error": {
                    "code": "EMPTY_INPUT",
                    "raw_input": "",
                }
            }

        try:
            request = json.loads(raw_input)
        except json.JSONDecodeError as exc:
            return {
                "_transport_error": {
                    "code": "INVALID_JSON",
                    "raw_input": raw_input,
                    "details": str(exc),
                }
            }

        if isinstance(request, dict):
            return request

        return {
            "_transport_error": {
                "code": "NON_OBJECT_JSON",
                "raw_input": request,
            }
        }

    async def send_response(self, data: Any) -> None:
        payload = json.dumps(data, default=str, separators=(",", ":"))
        await asyncio.to_thread(sys.stdout.write, payload + "\n")
        await asyncio.to_thread(sys.stdout.flush)
