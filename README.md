# MCPGuard

MCPGuard is an asynchronous security and observability layer for MCP-style AI tool workflows.

It sits between a client and backend tools, validates incoming requests, blocks unsafe operations, routes safe requests to the correct backend service, redacts sensitive data from responses, and writes structured audit logs with latency information.

## What MCPGuard Does

MCPGuard is designed to protect tool-enabled AI workflows by adding a guard layer before requests reach backend systems.

Core capabilities:
- request validation
- role-based access control (RBAC)
- path traversal and sandbox protection
- tool-to-backend routing
- upstream HTTP forwarding
- response redaction
- structured audit logging
- latency tracking

## High-Level Architecture

At a high level, the project looks like this:

```text
MCP Client -> MCP Adapter -> MCPGuard -> Backend Tool Service
```

Inside MCPGuard, the main blocks are:

- `Transport`
  - `StdioTransport`
  - `HttpTransport`
- `Orchestrator`
  - `MCPGuardProxy`
- `Security`
  - `PolicyLoader`
  - `RequestValidator`
  - `ResponseRedactor`
- `Routing`
  - `ToolRouter`
  - `UpstreamClient`
- `Telemetry`
  - `AuditLogger`
  - `BackgroundFlusher`

## Project Structure

```text
src/mcpguard/
  main.py
  orchestrator.py
  security/
  routing/
  telemetry/
  transport/

demo/
  backend_service.py
  mcp_adapter.py
  mcp_client_demo.py
  policy.http_demo.yaml
  README.md

tests/
  test_policy_and_validator.py
  test_routing_redaction_telemetry.py
  test_flow.py
```

## Main Components

### Transport

MCPGuard supports two transport modes:

- `stdio`
  - useful for local machine-to-machine workflows
  - uses atomic writes so concurrent responses do not corrupt stdout
- `http`
  - uses `aiohttp`
  - supports concurrent requests through a queue and request-scoped futures
  - includes request timeout handling and clean shutdown

### Security

The security block is responsible for making sure unsafe requests do not reach the backend.

- `PolicyLoader`
  - loads and validates the YAML policy file
- `RequestValidator`
  - validates request shape
  - enforces RBAC
  - validates tool arguments
  - blocks path traversal outside the allowed workspace
- `ResponseRedactor`
  - removes secret-like values from backend responses
  - supports both built-in regex patterns and policy-driven patterns

### Routing

- `ToolRouter`
  - maps a tool name such as `read_file` to the correct backend route
- `UpstreamClient`
  - sends the validated request to the backend over HTTP
  - normalizes backend responses
  - handles timeouts and network failures

### Telemetry

- `AuditLogger`
  - records request start/end timing
  - builds structured audit events
- `BackgroundFlusher`
  - writes audit events to `logs/mcpguard_audit.log`
  - uses JSON Lines format and log rotation

## Request Lifecycle

A request moves through MCPGuard in this order:

1. transport receives the request
2. orchestrator starts request processing
3. validator checks request safety
4. router resolves the backend target
5. upstream client forwards the request
6. backend returns a response
7. redactor scrubs secrets if needed
8. transport returns the final response
9. telemetry records status and latency

## Real MCP Demo

This project includes a real MCP-style demo in the [`demo/`](./demo) folder.

The demo uses:

- [`demo/mcp_client_demo.py`](./demo/mcp_client_demo.py)
  - a demo MCP client
- [`demo/mcp_adapter.py`](./demo/mcp_adapter.py)
  - a thin MCP stdio adapter
  - behaves like a small MCP server
  - exposes `read_file` and `write_file`
- [`demo/backend_service.py`](./demo/backend_service.py)
  - a demo backend with `/read` and `/write`

In the demo, the adapter translates MCP tool calls into MCPGuard HTTP requests. MCPGuard then performs validation, routing, redaction, and telemetry before calling the backend.

## Installation

Create and activate a virtual environment, then install the project.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

Optional but useful for MCP validation:

```bash
.venv/bin/pip install "mcp[cli]"
```

## Configuration

MCPGuard reads its configuration from `policy.yaml`.

Important sections in the policy file:

- `workspace_root`
- `transport`
- `routing_endpoints`
- `redaction_patterns`
- `agent_permissions`
- `allowed_tools`

Example fields:

```yaml
transport:
  type: http
  host: "127.0.0.1"
  port: 8080
  request_timeout_seconds: 30
```

```yaml
allowed_tools:
  read_file:
    arguments:
      file_path: string
    path_fields:
      - file_path
```

## Running MCPGuard

From the project root:

```bash
python3 src/mcpguard/main.py
```

MCPGuard will start using whatever transport and policy are defined in `policy.yaml`.

## Running the Real MCP Demo

Open three terminals and activate the virtual environment in each one.

### Terminal 1: Start the demo backend

```bash
cd "/Users/rushalimoteria/Desktop/NYU/SEM 4/mcpguard_project"
source .venv/bin/activate
python3 demo/backend_service.py
```

### Terminal 2: Start MCPGuard in HTTP mode

```bash
cd "/Users/rushalimoteria/Desktop/NYU/SEM 4/mcpguard_project"
source .venv/bin/activate
cp demo/policy.http_demo.yaml policy.yaml
python3 src/mcpguard/main.py
```

### Terminal 3: Run the MCP demo client

```bash
cd "/Users/rushalimoteria/Desktop/NYU/SEM 4/mcpguard_project"
source .venv/bin/activate
python3 demo/mcp_client_demo.py
```

### View the audit log

```bash
cat logs/mcpguard_audit.log
```

## Demo Requests

The demo client performs:

1. MCP initialization handshake
2. `tools/list`
3. blocked guest `write_file`
4. blocked path traversal `read_file`
5. successful admin `write_file`
6. successful admin `read_file`

The final safe read response should show that secret-like values were redacted.

## Testing

Run the automated test suite with:

```bash
python3 -m unittest discover -s tests -v
```

The test suite covers:

- policy loading
- request validation
- RBAC enforcement
- path traversal blocking
- routing
- upstream response normalization
- response redaction
- telemetry logging
- end-to-end flow behavior

## Sample Results

Expected behavior during the demo:

- guest `write_file` is blocked with `RBAC_DENIED`
- admin `read_file` using `../secret.txt` is blocked with `PATH_TRAVERSAL`
- safe `write_file` succeeds
- safe `read_file` succeeds
- secret-like fields in the backend response are returned as redacted values

Example telemetry fields:

- `request_id`
- `agent_id`
- `target_tool`
- `status_code`
- `error_message`
- `latency_ms`

## Design Notes

Some important design choices in the project:

- HTTP transport uses a queue plus request-specific futures for concurrency
- stdio transport uses correlation IDs and atomic writes
- the orchestrator dispatches requests with `asyncio.create_task(...)`
- the router and upstream client are intentionally split by responsibility
- telemetry uses asynchronous write-behind logging to avoid adding disk I/O to the request path

## Limitations and Future Work

The project is complete for its current scope, but there are still some areas that could be improved:

- runtime rate limiting is not enforced yet
- configuration validation can be tightened further in some flexible sections
- the demo adapter could later be rebuilt directly with the official MCP SDK
- broader validation with more third-party MCP clients would strengthen interoperability claims

## References

- Model Context Protocol specification
- Model Context Protocol lifecycle documentation
- Model Context Protocol transport documentation
- Model Context Protocol tools/schema documentation
- Official MCP Inspector
- Official MCP Python SDK

## Author

Rushali Moteria

