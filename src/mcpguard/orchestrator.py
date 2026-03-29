import asyncio
import logging
from typing import Any

from routing import RoutingError


class MCPGuardProxy:
    """
    The Orchestrator (The Boss).
    Coordinates the flow of data between Transport, Security, Routing, and Telemetry.
    """
    def __init__(self, transport, validator, router, upstream_client, redactor):
        # The Boss takes its tools via Dependency Injection
        self.transport = transport
        self.validator = validator
        self.router = router
        self.upstream_client = upstream_client
        self.redactor = redactor
        self._background_tasks: set[asyncio.Task] = set()

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
            await self.upstream_client.close()
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

            # route the request to correct upstream client
            target = await self.router.resolve(request)
            upstream_response = await self.upstream_client.forward(target, request)

            # response redactor
            clean_envelope = await self.redactor.redact(upstream_response)
            clean_data = self._build_transport_response(clean_envelope)

            # --- STEP 5: Log (Block D: Telemetry) ---
            # TODO: Replace with async background queue
            print("Transaction logged.")

            # sending response back to AI agent
            await self.transport.send_response(clean_data, request_id=request_id)

        except RoutingError as exc:
            logging.error(f"Routing failed: {exc}")
            await self.transport.send_response(
                {
                    "status": "error",
                    "error": str(exc),
                    "_http_status": 502,
                },
                request_id=request_id,
            )

        except Exception as e:
            logging.error(f"Fatal error while processing request: {e}")
            await self.transport.send_response(
                {
                    "status": "error",
                    "error": "Internal proxy error",
                    "_http_status": 500,
                },
                request_id=request_id,
            )

    def _build_transport_response(self, upstream_response: Any) -> dict[str, Any]:
        if upstream_response.is_json and isinstance(upstream_response.body, dict):
            payload = dict(upstream_response.body)
        else:
            payload = {
                "status": "success" if upstream_response.status_code < 400 else "error",
                "body": upstream_response.body,
            }

        payload["_http_status"] = upstream_response.status_code
        return payload
