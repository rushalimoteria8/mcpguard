import asyncio
import logging
from typing import Any
from uuid import uuid4

from routing import RoutingError


class MCPGuardProxy:
    """
    The Orchestrator (The Boss).
    Coordinates the flow of data between Transport, Security, Routing, and Telemetry.
    """
    def __init__(
        self,
        transport,
        validator,
        router,
        upstream_client,
        redactor,
        audit_logger,
        background_flusher,
    ):
        # The Boss takes its tools via Dependency Injection
        self.transport = transport
        self.validator = validator
        self.router = router
        self.upstream_client = upstream_client
        self.redactor = redactor
        self.audit_logger = audit_logger
        self.background_flusher = background_flusher
        self._background_tasks: set[asyncio.Task] = set()

    async def run(self):
        """The main 6-step asynchronous event loop."""
        logging.info("MCPGuard Orchestrator started. Listening for requests...")
        await self.transport.start()
        flusher_task = asyncio.create_task(self.background_flusher.flush_loop())

        try:
            while True:
                try:
                    #Listen for a request from AI client via the transport block
                    request_id, request = await self.transport.receive_request()
                    
                    # Secret escape hatch for testing in the terminal
                    if request_id is None and isinstance(request, dict) and request.get("tool") == "exit":
                        logging.info("Shutting down MCPGuard...")
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
            await self.background_flusher.shutdown()
            await flusher_task
            await self.upstream_client.close()
            await self.transport.stop()

    async def process_request(self, request_id: Any | None, request: dict) -> None:
        telemetry_request_id = self._normalize_request_id(request_id)
        agent_id = request.get("agent_id") if isinstance(request, dict) else None
        target_tool = request.get("tool") if isinstance(request, dict) else None
        safe_agent_id = agent_id.strip() if isinstance(agent_id, str) and agent_id.strip() else "unknown"
        safe_target_tool = target_tool.strip() if isinstance(target_tool, str) and target_tool.strip() else "unknown"
        self.audit_logger.start_request(
            telemetry_request_id,
            safe_agent_id,
            safe_target_tool,
        )

        status_code = 500
        error_message: str | None = "Internal proxy error"

        try:
            if not isinstance(agent_id, str) or not agent_id.strip():
                status_code = 400
                error_message = "MALFORMED_REQUEST"
                await self.transport.send_response(
                    {"error": "MALFORMED_REQUEST", "status": "blocked"},
                    request_id=request_id,
                )
                return

            #Security block: validation of the request
            is_safe, message = self.validator.validate(request, agent_id=agent_id)
            if not is_safe:
                logging.warning("Blocked request: %s", message)
                status_code = self._status_code_for_error(message)
                error_message = message
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
            status_code = int(clean_data.get("_http_status", 200))
            error_message = clean_data.get("error") if isinstance(clean_data.get("error"), str) else None

            # --- STEP 5: Log (Block D: Telemetry) ---
            logging.info("Transaction queued for audit logging.")

            # sending response back to AI agent
            await self.transport.send_response(clean_data, request_id=request_id)

        except RoutingError as exc:
            logging.error(f"Routing failed: {exc}")
            status_code = 502
            error_message = str(exc)
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
            status_code = 500
            error_message = "Internal proxy error"
            await self.transport.send_response(
                {
                    "status": "error",
                    "error": "Internal proxy error",
                    "_http_status": 500,
                },
                request_id=request_id,
            )
        finally:
            self.audit_logger.finish_request(
                telemetry_request_id,
                status_code=status_code,
                error_message=error_message,
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

    def _normalize_request_id(self, request_id: Any | None) -> str:
        if request_id is None:
            return f"local-{uuid4().hex}"
        return str(request_id)

    def _status_code_for_error(self, error_code: str) -> int:
        if error_code in {"MALFORMED_REQUEST", "SCHEMA_VALIDATION_FAILED"}:
            return 400
        if error_code in {"RBAC_DENIED", "PATH_TRAVERSAL"}:
            return 403
        return 500
