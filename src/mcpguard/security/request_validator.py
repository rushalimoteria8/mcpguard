from pathlib import Path
import logging

class RequestValidator:
    """
    Block B: Security (The Bouncer)
    Responsible for ensuring AI requests don't violate sandbox boundaries, 
    enforcing RBAC, and validating schemas.
    """
    
    def __init__(self, workspace_root: str, agent_permissions: dict, tool_schemas: dict):
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.agent_permissions = agent_permissions
        self.tool_schemas = tool_schemas

    #Helper functions
    def _check_rbac(self, agent_id: str, tool_name: str) -> bool:
        """Checks the agent_permissions dict to see if the tool is allowed."""
        allowed_tools = self.agent_permissions.get(agent_id, [])
        return tool_name in allowed_tools

    def _validate_schema(self, tool_name: str, arguments: dict) -> bool:
        """Checks the arguments against the tool_schemas dict for correct data types."""
    
        schema = self.tool_schemas.get(tool_name)
        if not schema:
            logging.error(f"Schema error: No schema found for tool '{tool_name}'")
            return False

        expected_args = schema.get("arguments", {})
        required_args = schema.get("required", list(expected_args.keys()))

        unknown_args = set(arguments) - set(expected_args)
        if unknown_args:
            logging.error(
                "Schema error: Unexpected argument(s): %s",
                ", ".join(sorted(unknown_args)),
            )
            return False

        for arg_name in required_args:
            if arg_name not in arguments:
                logging.error(f"Schema error: Missing argument '{arg_name}'")
                return False

        for arg_name, value in arguments.items():
            expected_type = expected_args.get(arg_name)
            if not self._is_valid_type(value, expected_type):
                logging.error(
                    "Schema error: '%s' must be of type '%s'",
                    arg_name,
                    expected_type,
                )
                return False

        return True

    def _is_valid_type(self, value, expected_type: str) -> bool:
        """Checks a value against the simple schema types supported by MCPGuard."""

        type_checks = {
            "string": lambda v: isinstance(v, str),
            "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "boolean": lambda v: isinstance(v, bool),
            "number": lambda v: (
                (isinstance(v, int) and not isinstance(v, bool)) or isinstance(v, float)
            ),
            "array": lambda v: isinstance(v, list),
            "object": lambda v: isinstance(v, dict),
        }
        validator = type_checks.get(expected_type)
        return validator(value) if validator else False

    def _enforce_sandbox(self, tool_name: str, arguments: dict) -> bool:
        """Does the math to ensure any path stays inside the workspace_root."""
        schema = self.tool_schemas.get(tool_name, {})
        path_fields = schema.get("path_fields", [])

        for field_name in path_fields:
            target_path = arguments.get(field_name)
            if target_path is None:
                continue

            if not isinstance(target_path, str):
                logging.error(f"Path validation failed: '{field_name}' must be a string")
                return False

            if not self._is_path_within_workspace(target_path):
                logging.error(
                    "Path validation failed: '%s' points outside the workspace",
                    field_name,
                )
                return False

        return True

    def _is_path_within_workspace(self, target_path: str) -> bool:
        """Resolves a requested path and confirms it stays within the workspace root."""
        try:
            requested_parsed_path = (self.workspace_root / target_path).expanduser().resolve()
            return requested_parsed_path.is_relative_to(self.workspace_root)
        except Exception as e:
            logging.error(f"Path validation failed: {e}")
            return False

    def validate(self, request: dict, agent_id: str) -> tuple[bool, str]:
        """
        The main entry point. Calls private methods in order.
        Returns (True, "Safe") or (False, "Error Reason").
        """
        if not isinstance(request, dict):
            return False, "MALFORMED_REQUEST"
            
        tool_name = request.get("tool")
        arguments = request.get("parameters", {})
        
        if not isinstance(tool_name, str) or not tool_name.strip() or not isinstance(arguments, dict):
            return False, "MALFORMED_REQUEST"

        if not self._check_rbac(agent_id, tool_name):
            return False, "RBAC_DENIED"

        if not self._validate_schema(tool_name, arguments):
            return False, "SCHEMA_VALIDATION_FAILED"

        if not self._enforce_sandbox(tool_name, arguments):
            return False, "PATH_TRAVERSAL"

        return True, "Safe"
