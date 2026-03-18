import asyncio
import json
from transport.base import BaseTransport  # <--- This looks for base.py!

class StdioTransport(BaseTransport):
    """A simple terminal interface to act as the AI Agent for testing."""
    
    async def receive_request(self) -> dict:
        print("\n🤖 AI Agent (You) - Enter JSON request (or type {\"tool\": \"exit\"}):")
        user_input = await asyncio.to_thread(input, "> ")
        
        try:
            return json.loads(user_input)
        except json.JSONDecodeError:
            return user_input

    async def send_response(self, data) -> None:
        print(f"🛡️ MCPGuard Response: {json.dumps(data, indent=2)}")