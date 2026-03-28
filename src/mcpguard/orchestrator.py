import asyncio
import logging
from typing import Any

class MCPGuardProxy:
    """
    The Orchestrator (The Boss).
    Coordinates the flow of data between Transport, Security, Routing, and Telemetry.
    """
    def __init__(self, transport, validator):
        # The Boss takes its tools via Dependency Injection
        self.transport = transport
        self.validator = validator
        self._background_tasks: set[asyncio.Task] = set()
        
        # We will inject these later as we build Blocks C and D!
        # self.router = router
        # self.upstream = upstream
        # self.redactor = redactor
        # self.logger = logger

    async def run(self):
        """The main 6-step asynchronous event loop."""
        print("MCPGuard Orchestrator started. Listening for requests...")
        await self.transport.start()

        try:
            while True:
                try:
                    #Listen for a request from AI client via the transport block
                    request_id, request = await self.transport.receive_request()
                    
                    # Secret escape hatch for testing in the terminal
                    if request_id is None and isinstance(request, dict) and request.get("tool") == "exit":
                        print("Shutting down MCPGuard...")
                        break
                    
                    # creating independent workers to handle each request concurrently
                    task = asyncio.create_task(self.process_request(request_id, request))
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
                    
                except Exception as e:
                    logging.error(f"Fatal error in proxy loop: {e}")
        #gracefully handling the shtu down of the proxy
        finally:
            if self._background_tasks:
                for task in list(self._background_tasks):
                    task.cancel()
                await asyncio.gather(*self._background_tasks, return_exceptions=True)
            await self.transport.stop()

    async def process_request(self, request_id: Any | None, request: dict) -> None:
        try:
            #Security block: validation of the request
            is_safe, message = self.validator.validate(request, agent_id="admin_agent")
            if not is_safe:
                print(f"Blocked Request: {message}")
                await self.transport.send_response(
                    {"error": message, "status": "blocked"},
                    request_id=request_id,
                )
                return

            # --- STEP 3: Fetch (Block C: Routing) ---
            # TODO: Replace with actual routing and HTTP client logic
            print(f"Request safe. Routing to tool: {request.get('tool')}")
            raw_data = {"status": "success", "data": "Mocked backend response from tool!"}

            # --- STEP 4: Clean (Block B: Redactor) ---
            # TODO: Replace with streaming regex redactor
            clean_data = raw_data

            # --- STEP 5: Log (Block D: Telemetry) ---
            # TODO: Replace with async background queue
            print("Transaction logged.")

            # --- STEP 6: Send (Block A: Transport) ---
            await self.transport.send_response(clean_data, request_id=request_id)

        except Exception as e:
            logging.error(f"Fatal error while processing request: {e}")
            await self.transport.send_response(
                {"error": "Internal proxy error"},
                request_id=request_id,
            )
