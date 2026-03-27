from abc import ABC, abstractmethod
from typing import Any

class BaseTransport(ABC):
    """
    The 'Contract' that all Front Doors must follow.
    """

    @abstractmethod
    async def receive_request(self) -> dict:
        """Receive a request from the client and return it as a Python dictionary."""
        raise NotImplementedError

    @abstractmethod
    async def send_response(self, data: Any) -> None:
        """Send the final response back to the client."""
        raise NotImplementedError
