from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import aiohttp


PROTOCOL_VERSION = "2025-11-25"
SERVER_INFO = {
    "name": "mcpguard-demo-adapter",
    "title": "MCPGuard Demo Adapter",
    "version": "1.0.0",
}
MCPGUARD_URL = os.environ.get("MCPGUARD_URL", "http://127.0.0.1:8080")


class MCPDemoAdapter:
    def __init__(self) -> None:
        self._write_lock = asyncio.Lock()
        self._initialized = False
        self._session: aiohttp.ClientSession | None = None

    async def run(self) -> None:
        try:
            while True:
                raw_line = await asyncio.to_thread(sys.stdin.readline)
                if raw_line == "":
                    break

                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                try:
                    message = json.loads(raw_line)
                except json.JSONDecodeError:
                    await self._send_error(None, -32700, "Parse error")
                    continue

                if not isinstance(message, dict):
                    await self._send_error(None, -32600, "Invalid Request")
                    continue

                await self._handle_message(message)
        finally:
            if self._session is not None and not self._session.closed:
                await self._session.close()

    async def _handle_message(self, message: dict[str, Any]) -> None:
        method = message.get("method")
        message_id = message.get("id")
        params = message.get("params", {})

        if not isinstance(method, str):
            await self._send_error(message_id, -32600, "Invalid Request")
            return

        if method == "initialize":
            await self._handle_initialize(message_id, params)
            return

        if method == "notifications/initialized":
            self._initialized = True
            return

        if not self._initialized:
            await self._send_error(message_id, -32002, "Server not initialized")
            return

        if method == "tools/list":
            await self._send_result(
                message_id,
                {
                    "tools": [
                        self._build_read_tool(),
                        self._build_write_tool(),
                    ]
                },
            )
            return

        if method == "tools/call":
            await self._handle_tool_call(message_id, params)
            return

        await self._send_error(message_id, -32601, f"Method not found: {method}")

    async def _handle_initialize(self, message_id: Any, params: Any) -> None:
        if not isinstance(params, dict):
            await self._send_error(message_id, -32602, "Invalid params")
            return

        await self._send_result(
            message_id,
            {
                # Return the protocol version this adapter actually implements
                # instead of blindly echoing whatever the client requested.
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {
                    "tools": {
                        "listChanged": False,
                    }
                },
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "This MCP demo adapter forwards tool calls through MCPGuard "
                    "so the workflow includes validation, routing, redaction, and telemetry."
                ),
            },
        )

    async def _handle_tool_call(self, message_id: Any, params: Any) -> None:
        if not isinstance(params, dict):
            await self._send_error(message_id, -32602, "Invalid params")
            return

        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if not isinstance(tool_name, str) or not tool_name.strip() or not isinstance(arguments, dict):
            await self._send_error(message_id, -32602, "Invalid params")
            return

        agent_id = arguments.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id.strip():
            await self._send_result(
                message_id,
                {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"error": "MALFORMED_REQUEST"}, separators=(",", ":")),
                        }
                    ],
                    "structuredContent": {"error": "MALFORMED_REQUEST"},
                    "isError": True,
                },
            )
            return

        guard_payload = {
            "agent_id": agent_id,
            "tool": tool_name,
            "parameters": {
                key: value
                for key, value in arguments.items()
                if key != "agent_id"
            },
        }

        session = await self._ensure_session()
        try:
            async with session.post(
                MCPGUARD_URL,
                json=guard_payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if "application/json" in response.headers.get("Content-Type", "").lower():
                    body = await response.json()
                else:
                    body = {"body": await response.text()}
                status = response.status
        except aiohttp.ClientError as exc:
            body = {
                "error": "BAD_GATEWAY",
                "message": str(exc),
            }
            status = 502

        is_error = bool(status >= 400 or body.get("status") in {"blocked", "error"})
        await self._send_result(
            message_id,
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(body, separators=(",", ":")),
                    }
                ],
                "structuredContent": body,
                "isError": is_error,
            },
        )

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
        return self._session

    def _build_read_tool(self) -> dict[str, Any]:
        return {
            "name": "read_file",
            "title": "Read File Through MCPGuard",
            "description": "Read a file through MCPGuard with validation and redaction.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Demo identity used for MCPGuard RBAC checks.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative file path inside the demo workspace.",
                    },
                },
                "required": ["agent_id", "file_path"],
            },
        }

    def _build_write_tool(self) -> dict[str, Any]:
        return {
            "name": "write_file",
            "title": "Write File Through MCPGuard",
            "description": "Write a file through MCPGuard with validation and routing.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "Demo identity used for MCPGuard RBAC checks.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative file path inside the demo workspace.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write.",
                    },
                },
                "required": ["agent_id", "file_path", "content"],
            },
        }

    async def _send_result(self, message_id: Any, result: dict[str, Any]) -> None:
        await self._write_json(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "result": result,
            }
        )

    async def _send_error(self, message_id: Any, code: int, message: str) -> None:
        await self._write_json(
            {
                "jsonrpc": "2.0",
                "id": message_id,
                "error": {
                    "code": code,
                    "message": message,
                },
            }
        )

    async def _write_json(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, separators=(",", ":"))
        async with self._write_lock:
            await asyncio.to_thread(sys.stdout.write, raw + "\n")
            await asyncio.to_thread(sys.stdout.flush)


async def main() -> None:
    adapter = MCPDemoAdapter()
    await adapter.run()


if __name__ == "__main__":
    asyncio.run(main())
