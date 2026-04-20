import asyncio
import sys
import tempfile
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "mcpguard"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from orchestrator import MCPGuardProxy
from routing import ToolRouter, UpstreamClient
from routing.upstream_client import ResponseEnvelope
from security.request_validator import RequestValidator
from security.response_redactor import ResponseRedactor
from telemetry import AuditLogger, BackgroundFlusher


class _FakeTransport:
    def __init__(self) -> None:
        self.responses: list[tuple[object | None, dict]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def send_response(self, data, request_id=None) -> None:
        self.responses.append((request_id, data))


class _FakeUpstreamClient:
    def __init__(self, envelope: ResponseEnvelope) -> None:
        self.envelope = envelope
        self.closed = False

    async def forward(self, target, payload):
        return self.envelope

    async def close(self) -> None:
        self.closed = True


class MCPGuardFlowTests(unittest.IsolatedAsyncioTestCase):
    def _build_proxy(
        self,
        routing_rules: dict,
        *,
        upstream_client=None,
    ) -> tuple[MCPGuardProxy, _FakeTransport, asyncio.Queue]:
        transport = _FakeTransport()
        validator = RequestValidator(
            workspace_root=tempfile.gettempdir(),
            agent_permissions={
                "admin_agent": ["read_file", "write_file"],
                "guest_agent": ["read_file"],
            },
            tool_schemas={
                "read_file": {
                    "arguments": {"file_path": "string"},
                    "path_fields": ["file_path"],
                },
                "write_file": {
                    "arguments": {"file_path": "string", "content": "string"},
                    "path_fields": ["file_path"],
                },
            },
        )
        router = ToolRouter(routing_rules)
        upstream_client = upstream_client or UpstreamClient()
        redactor = ResponseRedactor()
        queue: asyncio.Queue[dict[str, object] | object] = asyncio.Queue()
        audit_logger = AuditLogger(queue)
        background_flusher = BackgroundFlusher(
            queue,
            log_path=Path(tempfile.gettempdir()) / "mcpguard_test_audit.log",
        )

        proxy = MCPGuardProxy(
            transport=transport,
            validator=validator,
            router=router,
            upstream_client=upstream_client,
            redactor=redactor,
            audit_logger=audit_logger,
            background_flusher=background_flusher,
        )
        return proxy, transport, queue

    async def test_successful_request_flows_through_routing_redaction_and_telemetry(self) -> None:
        fake_upstream = _FakeUpstreamClient(
            ResponseEnvelope(
                status_code=200,
                is_json=True,
                body={
                    "content": "hello from backend",
                    "token": "sk-123456789012345678901234",
                },
            )
        )
        proxy, transport, queue = self._build_proxy(
            {
                "read_file": {
                    "url": "http://backend.local",
                    "method": "POST",
                    "path": "/read",
                }
            },
            upstream_client=fake_upstream,
        )

        try:
            await proxy.process_request(
                "req-success",
                {
                    "agent_id": "admin_agent",
                    "tool": "read_file",
                    "parameters": {"file_path": "notes.txt"},
                },
            )

            self.assertEqual(len(transport.responses), 1)
            request_id, response = transport.responses[0]
            self.assertEqual(request_id, "req-success")
            self.assertEqual(response["_http_status"], 200)
            self.assertEqual(response["content"], "hello from backend")
            self.assertEqual(response["token"], "[REDACTED]")

            audit_event = await queue.get()
            self.assertEqual(audit_event["request_id"], "req-success")
            self.assertEqual(audit_event["status_code"], 200)
            self.assertIsNone(audit_event["error_message"])
            queue.task_done()
        finally:
            await proxy.upstream_client.close()

    async def test_path_traversal_is_blocked_and_logged(self) -> None:
        proxy, transport, queue = self._build_proxy({})

        try:
            await proxy.process_request(
                "req-path",
                {
                    "agent_id": "admin_agent",
                    "tool": "read_file",
                    "parameters": {"file_path": "../secret.txt"},
                },
            )

            self.assertEqual(len(transport.responses), 1)
            _, response = transport.responses[0]
            self.assertEqual(response["error"], "PATH_TRAVERSAL")
            self.assertEqual(response["status"], "blocked")

            audit_event = await queue.get()
            self.assertEqual(audit_event["request_id"], "req-path")
            self.assertEqual(audit_event["status_code"], 403)
            self.assertEqual(audit_event["error_message"], "PATH_TRAVERSAL")
            queue.task_done()
        finally:
            await proxy.upstream_client.close()

    async def test_routing_failure_returns_error_and_is_logged(self) -> None:
        proxy, transport, queue = self._build_proxy({})

        try:
            await proxy.process_request(
                "req-route",
                {
                    "agent_id": "admin_agent",
                    "tool": "read_file",
                    "parameters": {"file_path": "notes.txt"},
                },
            )

            self.assertEqual(len(transport.responses), 1)
            _, response = transport.responses[0]
            self.assertEqual(response["_http_status"], 502)
            self.assertIn("ROUTE_NOT_FOUND", response["error"])

            audit_event = await queue.get()
            self.assertEqual(audit_event["request_id"], "req-route")
            self.assertEqual(audit_event["status_code"], 502)
            self.assertIn("ROUTE_NOT_FOUND", audit_event["error_message"])
            queue.task_done()
        finally:
            await proxy.upstream_client.close()
