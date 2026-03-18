from abc import ABC, abstractmethod

class BaseTransport(ABC):
    """
    The 'Contract' that all Front Doors must follow.
    """
    @abstractmethod
    async def receive_request(self) -> dict:
        """Listen for the AI Agent to send a tool request."""
        pass

    @abstractmethod
    async def send_response(self, data) -> None:
        """Send the response back to the AI Agent."""
        pass