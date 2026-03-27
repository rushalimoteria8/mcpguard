from typing import Any

from .base_transport import BaseTransport


class HttpTransport(BaseTransport):
    """
    HTTP-based transport for network clients.

    This class is intentionally a placeholder for now so the transport layer
    has the full interface planned in the design, even though only stdio mode
    is currently wired up.
    """

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port

    async def receive_request(self) -> dict:
        raise NotImplementedError("HttpTransport is planned but not implemented yet.")

    async def send_response(self, data: Any) -> None:
        raise NotImplementedError("HttpTransport is planned but not implemented yet.")
