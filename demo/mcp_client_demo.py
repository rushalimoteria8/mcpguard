from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_PATH = PROJECT_ROOT / "demo" / "mcp_adapter.py"


class MCPDemoClient:
    def __init__(self) -> None:
        self._next_id = 1

    async def run(self) -> None:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(ADAPTER_PATH),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            await self._request(
                process,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "mcpguard-demo-client",
                        "version": "1.0.0",
                    },
                },
            )

            await self._notify(process, "notifications/initialized")

            print("\n1. MCP tools/list")
            tools_result = await self._request(process, "tools/list", {})
            print(json.dumps(tools_result, indent=2))

            print("\n2. RBAC block: guest tries write_file")
            print(
                json.dumps(
                    await self._call_tool(
                        process,
                        "write_file",
                        {
                            "agent_id": "guest_agent",
                            "file_path": "notes.txt",
                            "content": "hello from guest",
                        },
                    ),
                    indent=2,
                )
            )

            print("\n3. Sandbox block: admin tries path traversal")
            print(
                json.dumps(
                    await self._call_tool(
                        process,
                        "read_file",
                        {
                            "agent_id": "admin_agent",
                            "file_path": "../secret.txt",
                        },
                    ),
                    indent=2,
                )
            )

            print("\n4. Safe write request")
            print(
                json.dumps(
                    await self._call_tool(
                        process,
                        "write_file",
                        {
                            "agent_id": "admin_agent",
                            "file_path": "notes.txt",
                            "content": "Hello from the MCPGuard demo backend",
                        },
                    ),
                    indent=2,
                )
            )

            print("\n5. Safe read request with redaction")
            print(
                json.dumps(
                    await self._call_tool(
                        process,
                        "read_file",
                        {
                            "agent_id": "admin_agent",
                            "file_path": "notes.txt",
                        },
                    ),
                    indent=2,
                )
            )
        finally:
            if process.stdin is not None:
                process.stdin.close()
            await process.wait()

    async def _call_tool(
        self,
        process: asyncio.subprocess.Process,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._request(
            process,
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )

    async def _request(
        self,
        process: asyncio.subprocess.Process,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        message_id = self._next_id
        self._next_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": message_id,
            "method": method,
            "params": params,
        }
        await self._write_message(process, payload)
        response = await self._read_message(process)
        return response

    async def _notify(
        self,
        process: asyncio.subprocess.Process,
        method: str,
    ) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
        }
        await self._write_message(process, payload)

    async def _write_message(
        self,
        process: asyncio.subprocess.Process,
        payload: dict[str, Any],
    ) -> None:
        raw = json.dumps(payload, separators=(",", ":")) + "\n"
        assert process.stdin is not None
        process.stdin.write(raw.encode("utf-8"))
        await process.stdin.drain()

    async def _read_message(self, process: asyncio.subprocess.Process) -> dict[str, Any]:
        assert process.stdout is not None
        line = await process.stdout.readline()
        if not line:
            raise RuntimeError("MCP adapter closed before sending a response.")
        return json.loads(line.decode("utf-8"))


async def main() -> None:
    client = MCPDemoClient()
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
