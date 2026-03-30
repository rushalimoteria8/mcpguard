import sys
import logging
import asyncio
from routing import ToolRouter, UpstreamClient
from security.policy_loader import PolicyLoader
from security.response_redactor import ResponseRedactor
from security.request_validator import RequestValidator
from telemetry import AuditLogger, BackgroundFlusher
from transport import HttpTransport, StdioTransport
from orchestrator import MCPGuardProxy

"""""
Sequence for 
1. create PolicyLoader
2. call load()
3. if load fails -> print error and exit
4. get security rules
5. create RequestValidator
6. create transport
7. create proxy
8. call await proxy.run()
"""
async def main():
    loader = PolicyLoader("policy.yaml")
    if not loader.load():
        logging.error("Policy load failed: %s", loader.last_error)
        sys.exit(1)

    security_rules = loader.get_security_rules()
    transport_rules = loader.get_transport_rules()
    routing_rules = loader.get_routing_rules()
    redaction_rules = loader.get_redaction_rules()

    #validator object initialisation
    validator = RequestValidator(
        workspace_root=security_rules["workspace_root"],
        agent_permissions=security_rules["agent_permissions"],
        tool_schemas=security_rules["tool_schemas"]
    )
    logging.info("Validator initialised. Sandbox locked to: %s", validator.workspace_root)

    transport_type = transport_rules["type"]
    if transport_type == "stdio":
        transport = StdioTransport()
    elif transport_type == "http":
        transport = HttpTransport(
            host=transport_rules["host"],
            port=transport_rules["port"],
            request_timeout_seconds=transport_rules["request_timeout_seconds"],
        )
    else:
        logging.error("Unsupported transport type: %s", transport_type)
        sys.exit(1)

    router = ToolRouter(routing_rules)
    upstream_client = UpstreamClient()
    redactor = ResponseRedactor(redaction_rules=redaction_rules)
    telemetry_queue: asyncio.Queue[dict[str, object] | object] = asyncio.Queue()
    audit_logger = AuditLogger(telemetry_queue)
    background_flusher = BackgroundFlusher(telemetry_queue)

    proxy = MCPGuardProxy(
        transport=transport,
        validator=validator,
        router=router,
        upstream_client=upstream_client,
        redactor=redactor,
        audit_logger=audit_logger,
        background_flusher=background_flusher,
    )
    
    await proxy.run()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
