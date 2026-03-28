from abc import ABC, abstractmethod
from typing import Any

class BaseTransport(ABC):
    """
    The 'Contract' that all Front Doors must follow.
    """

    async def start(self) -> None:
        """Optional lifecycle hook for transports that need startup work."""
        return None

    async def stop(self) -> None:
        """Optional lifecycle hook for transports that need cleanup work."""
        return None

    @abstractmethod
    async def receive_request(self) -> tuple[Any | None, dict[str, Any]]:
        """Receive a request and return (request_id, payload)."""
        raise NotImplementedError

    @abstractmethod
    async def send_response(self, data: Any, request_id: Any | None = None) -> None:
        """Send the final response back to the client."""
        raise NotImplementedError
