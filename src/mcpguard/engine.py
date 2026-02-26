import yaml
from pathlib import Path
import sys

class SecurityEngine:
    def __init__(self, policy_path="policy.yaml"):
        self.policy_path = Path(policy_path)
        self.policy = self.load_policy()

        self._validate_policy_structure()
        
        #extracting the workspace root
        #use "resolve" to calculate the absolute path
        self.workspace_root = Path(self.policy.get("workspace_root")).expanduser().resolve()

    def _validate_policy_structure(self):
        """
        Ensures the YAML contains the minimum required fields for MCPGuard.
        """
        if "workspace_root" in self.policy and not isinstance(self.policy["workspace_root"], str):
            print("[!] Configuration Error: 'workspace_root' must be a string path.")
            sys.exit(1)

        permissions = self.policy.get("agent_permissions")
        if permissions and not isinstance(permissions, dict):
            print(f"\n[!] Configuration Error: 'agent_permissions' must be a dictionary, got {type(permissions).__name__}.")
            sys.exit(1)

        required_keys = ["version", "workspace_root", "agent_permissions"]
        missing = [key for key in required_keys if key not in self.policy]
        
        if missing:
            print(f"\n[!] Configuration Error: Your '{self.policy_path}' is missing: {', '.join(missing)}")
            print("Please update the file to match the required schema.")
            sys.exit(1)

    def load_policy(self):
        """
        Loads the YAML policy. If missing, informs the user to create it.
        """
        if not self.policy_path.exists():
            print(f"\n[!] Error: Configuration file '{self.policy_path}' not found.")
            print(f"Please create a '{self.policy_path}' file in your project root to define your security rules.")
            sys.exit(1)
            
        with open(self.policy_path, 'r') as file:
            return yaml.safe_load(file)

    def get_agent_tools(self, agent_name):
        """
        Helper to see what a specific agent is allowed to do.
        """
        return self.policy.get("agent_permissions", {}).get(agent_name) or []