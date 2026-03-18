import yaml
import sys
from pathlib import Path
from security.validator import RequestValidator
# from orchestrator import MCPGuardProxy  <-- We will uncomment this next!

# --- NEW IMPORTS ---
from transport.stdio import StdioTransport
from orchestrator import MCPGuardProxy

def load_and_validate_policy(policy_path="policy.yaml"):
    """Reads the blueprint to figure out how to build the proxy"""
    path = Path(policy_path)
    if not path.exists():
        print(f"\n[!] Error: Configuration file '{path}' not found.")
        sys.exit(1)
        
    with open(path, 'r') as file:
        policy = yaml.safe_load(file)

    # Basic structure validation
    if "workspace_root" in policy and not isinstance(policy["workspace_root"], str):
        print("[!] Configuration Error: 'workspace_root' must be a string path.")
        sys.exit(1)

    return policy

async def main():
    
    #read the YAML 
    policy = load_and_validate_policy("policy.yaml") # Adjust path based on where you run it
    
   # Extract the full dictionaries from your YAML
    workspace_root = policy.get("workspace_root", "./")
    
    # We grab the ENTIRE dictionaries now, not just the admin list!
    full_agent_permissions = policy.get("agent_permissions", {})
    
    # In your YAML, you named the schema section "allowed_tools"
    tool_schemas = policy.get("allowed_tools", {}) 

    # Initialise the validator object with the new parameters
    validator = RequestValidator(
        workspace_root=workspace_root, 
        agent_permissions=full_agent_permissions,
        tool_schemas=tool_schemas
    )
    print(f"Validator initialised. Sandbox locked to: {validator.workspace_root}")

    # Build the Boss and hand it the tools (Coming up next!)
    # proxy = MCPGuardProxy(validator=validator)
    # await proxy.run()

    # 2. Build the Front Door
    transport = StdioTransport()

    # 3. Build the Boss and hand it the tools
    proxy = MCPGuardProxy(transport=transport, validator=validator)
    
    # 4. Start the engine!
    await proxy.run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())