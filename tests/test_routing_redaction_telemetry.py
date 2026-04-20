import asyncio
import json
import sys
import tempfile
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "mcpguard"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from routing import RouteTarget, RoutingError, ToolRouter, UpstreamClient
from routing.upstream_client import ResponseEnvelope
from security.response_redactor import ResponseRedactor
from telemetry import AuditLogger, BackgroundFlusher


class ToolRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolves_known_tool(self) -> None:
        router = ToolRouter(
            {
                "read_file": {
                    "url": "http://127.0.0.1:3001",
                    "method": "POST",
                    "path": "/read",
                }
            }
        )

        target = await router.resolve({"tool": "read_file"})

        self.assertEqual(target.url, "http://127.0.0.1:3001")
        self.assertEqual(target.method, "POST")
        self.assertEqual(target.path, "/read")

    async def test_raises_for_unknown_tool(self) -> None:
        router = ToolRouter({})

        with self.assertRaises(RoutingError):
            await router.resolve({"tool": "missing_tool"})


class UpstreamClientTests(unittest.IsolatedAsyncioTestCase):
    class _FakeResponse:
        def __init__(self, status: int, body: str, content_type: str) -> None:
            self.status = status
            self.headers = {"Content-Type": content_type}
            self._body = body

        async def text(self) -> str:
            return self._body

    class _FakeRequestContext:
        def __init__(self, response) -> None:
            self._response = response

        async def __aenter__(self):
            return self._response

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class _FakeSession:
        def __init__(self, response) -> None:
            self._response = response

        def request(self, **kwargs):
            return UpstreamClientTests._FakeRequestContext(self._response)

    async def test_normalizes_json_response(self) -> None:
        client = UpstreamClient()
        response = self._FakeResponse(
            status=200,
            body='{"message":"hello"}',
            content_type="application/json",
        )

        async def fake_ensure_session():
            return self._FakeSession(response)

        client._ensure_session = fake_ensure_session  # type: ignore[method-assign]
        try:
            envelope = await client.forward(
                RouteTarget(url="http://backend.local", path="/json", headers={}),
                {"ping": "pong"},
            )
        finally:
            await client.close()

        self.assertEqual(envelope.status_code, 200)
        self.assertTrue(envelope.is_json)
        self.assertEqual(envelope.body, {"message": "hello"})

    async def test_normalizes_plain_text_response(self) -> None:
        client = UpstreamClient()
        response = self._FakeResponse(
            status=200,
            body="plain text body",
            content_type="text/plain",
        )

        async def fake_ensure_session():
            return self._FakeSession(response)

        client._ensure_session = fake_ensure_session  # type: ignore[method-assign]
        try:
            envelope = await client.forward(
                RouteTarget(url="http://backend.local", path="/text", headers={}),
                {"ping": "pong"},
            )
        finally:
            await client.close()

        self.assertEqual(envelope.status_code, 200)
        self.assertFalse(envelope.is_json)
        self.assertEqual(envelope.body, "plain text body")


class ResponseRedactorTests(unittest.IsolatedAsyncioTestCase):
    async def test_redacts_nested_keys_and_secret_patterns(self) -> None:
        redactor = ResponseRedactor()
        envelope = ResponseEnvelope(
            status_code=200,
            is_json=True,
            body={
                "token": "sk-123456789012345678901234",
                "nested": [
                    {"authorization": "Bearer abcdefghijklmnopqrstuvwxyz012345"},
                    {"note": "keep this secret sk-ant-abcdefghijklmnopqrstuvwxyz012345"},
                ],
            },
        )

        cleaned = await redactor.redact(envelope)

        self.assertEqual(cleaned.body["token"], "[REDACTED]")
        self.assertEqual(cleaned.body["nested"][0]["authorization"], "[REDACTED]")
        self.assertIn("[REDACTED_SECRET]", cleaned.body["nested"][1]["note"])


class TelemetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_audit_logger_and_background_flusher_write_jsonl(self) -> None:
        queue: asyncio.Queue[dict[str, object] | object] = asyncio.Queue()
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "mcpguard_audit.log"
            logger = AuditLogger(queue)
            flusher = BackgroundFlusher(queue, log_path=log_path)

            flusher_task = asyncio.create_task(flusher.flush_loop())
            logger.start_request("req-1", "admin_agent", "read_file")
            logger.finish_request("req-1", 200, None)

            await flusher.shutdown()
            await flusher_task

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            event = json.loads(lines[0])
            self.assertEqual(event["request_id"], "req-1")
            self.assertEqual(event["agent_id"], "admin_agent")
            self.assertEqual(event["target_tool"], "read_file")
            self.assertEqual(event["status_code"], 200)
            self.assertIn("latency_ms", event)
