import asyncio
import logging

class MCPGuardProxy:
    """
    The Orchestrator (The Boss).
    Coordinates the flow of data between Transport, Security, Routing, and Telemetry.
    """
    def __init__(self, transport, validator):
        # The Boss takes its tools via Dependency Injection
        self.transport = transport
        self.validator = validator
        
        # We will inject these later as we build Blocks C and D!
        # self.router = router
        # self.upstream = upstream
        # self.redactor = redactor
        # self.logger = logger

    async def run(self):
        """The main 6-step asynchronous event loop."""
        print("MCPGuard Orchestrator started. Listening for requests...")
        
        while True:
            try:
                # --- STEP 1: Listen (Block A: Transport) ---
                request = await self.transport.receive_request()
                
                # Secret escape hatch for testing in the terminal
                if isinstance(request, dict) and request.get("tool") == "exit":
                    print("Shutting down MCPGuard...")
                    break

                # --- STEP 2: Check (Block B: Security) ---
                is_safe, message = self.validator.validate(request, agent_id="admin_agent")
                if not is_safe:
                    print(f"Blocked Request: {message}")
                    await self.transport.send_response({"error": message, "status": "blocked"})
                    continue # Skip the rest, go back to listening!
                    
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
                await self.transport.send_response(clean_data)
                
            except Exception as e:
                logging.error(f"Fatal error in proxy loop: {e}")
                await self.transport.send_response({"error": "Internal proxy error"})