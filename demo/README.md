# MCPGuard Real MCP Demo

This demo shows MCPGuard inside a real MCP workflow.

## Architecture

```text
MCP Client (stdio) -> MCP Adapter (stdio MCP server) -> MCPGuard (HTTP, port 8080) -> Demo Backend (HTTP, port 3001)
```

MCPGuard demonstrates:
- RBAC enforcement
- path traversal blocking
- routing to backend tools
- response redaction
- structured audit logging with latency

## Files

- `backend_service.py`: tiny demo backend with `/read` and `/write`
- `policy.http_demo.yaml`: HTTP-mode policy for the demo
- `mcp_adapter.py`: thin MCP stdio adapter that exposes real MCP tools
- `mcp_client_demo.py`: demo client that performs real MCP `initialize`, `tools/list`, and `tools/call`

## Run the demo

### 1. Start the backend

```bash
python3 demo/backend_service.py
```

### 2. Run MCPGuard with the demo policy

If you want to keep your existing `policy.yaml`, temporarily copy the demo policy over it:

```bash
cp demo/policy.http_demo.yaml policy.yaml
python3 src/mcpguard/main.py
```

### 3. Run the real MCP demo client

```bash
python3 demo/mcp_client_demo.py
```

### 4. Show telemetry

```bash
cat logs/mcpguard_audit.log
```

