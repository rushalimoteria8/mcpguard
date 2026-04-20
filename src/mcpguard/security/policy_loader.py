from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml


class PolicyLoader:
    """
    Loads and validates the policy file once at startup.

    Main responsibilities:
    - Read YAML from disk
    - Validate the top-level structure
    - Populate config attributes for the rest of the system
    """

    SUPPORTED_SCHEMA_TYPES = {
        "string",
        "integer",
        "boolean",
        "number",
        "array",
        "object",
    }

    def __init__(self, config_path: str = "policy.yaml") -> None:
        self.config_path: str = config_path
        self.agent_permissions: dict[str, list[str]] = {}
        self.tool_schemas: dict[str, dict[str, Any]] = {}
        self.workspace_root: str = ""
        self.transport_config: dict[str, Any] = {}
        self.routing_endpoints: dict[str, Any] = {}
        self.redaction_patterns: list[Any] = []
        self.rate_limits: dict[str, Any] = {}

        self._loaded: bool = False
        self.last_error: str = ""

    def load(self) -> bool:
        """
        Opens the YAML file, validates structure, and populates attributes.
        Returns True on success, False on failure.
        """
        try:
            policy = self._read_yaml()
            self._validate_top_level_structure(policy)
            self._populate_attributes(policy)
            self._loaded = True
            self.last_error = ""
            return True

        except (OSError, yaml.YAMLError, ValueError, TypeError) as exc:
            self._loaded = False
            self.last_error = str(exc)
            return False

    def get_security_rules(self) -> dict[str, Any]:
        """
        Returns the config needed by RequestValidator.
        """
        self._ensure_loaded()
        return {
            "workspace_root": self.workspace_root,
            "agent_permissions": copy.deepcopy(self.agent_permissions),
            "tool_schemas": copy.deepcopy(self.tool_schemas),
            "rate_limits": copy.deepcopy(self.rate_limits),
        }

    def get_routing_rules(self) -> dict[str, Any]:
        """
        Returns routing endpoints for the ToolRouter.
        """
        self._ensure_loaded()
        return copy.deepcopy(self.routing_endpoints)

    def get_transport_rules(self) -> dict[str, Any]:
        """
        Returns transport configuration for startup selection.
        """
        self._ensure_loaded()
        return copy.deepcopy(self.transport_config)

    def get_redaction_rules(self) -> list[Any]:
        """
        Returns redaction patterns for the ResponseRedactor.
        """
        self._ensure_loaded()
        return copy.deepcopy(self.redaction_patterns)

    def _read_yaml(self) -> dict[str, Any]:
        path = Path(self.config_path)

        if not path.exists():
            raise FileNotFoundError(f"Configuration file '{self.config_path}' not found.")

        with path.open("r", encoding="utf-8") as file:
            policy = yaml.safe_load(file)

        if policy is None:
            raise ValueError("Configuration file is empty.")

        if not isinstance(policy, dict):
            raise TypeError("Top-level YAML structure must be a dictionary.")

        return policy

    def _validate_top_level_structure(self, policy: dict[str, Any]) -> None:
        self._require_type(policy, "version", str)
        self._require_type(policy, "workspace_root", str)
        if not policy["workspace_root"].strip():
            raise ValueError("'workspace_root' must be a non-empty string.")

        self._require_type(policy, "transport", dict)
        self._require_type(policy, "agent_permissions", dict)
        self._require_type(policy, "allowed_tools", dict)

        if "routing_endpoints" in policy and not isinstance(policy["routing_endpoints"], dict):
            raise TypeError("'routing_endpoints' must be a dictionary.")

        if "redaction_patterns" in policy and not isinstance(policy["redaction_patterns"], list):
            raise TypeError("'redaction_patterns' must be a list.")

        if "rate_limits" in policy and not isinstance(policy["rate_limits"], dict):
            raise TypeError("'rate_limits' must be a dictionary.")

        self._validate_transport_config(policy["transport"])
        self._validate_tool_schemas(policy["allowed_tools"])
        self._validate_agent_permissions(policy["agent_permissions"], policy["allowed_tools"])
        self._validate_routing_endpoints(policy.get("routing_endpoints", {}))
        self._validate_redaction_patterns(policy.get("redaction_patterns", []))
        self._validate_rate_limits(policy.get("rate_limits", {}))

    def _require_type(self, data: dict[str, Any], key: str, expected_type: type) -> None:
        if key not in data:
            raise ValueError(f"Missing required configuration key: '{key}'")

        if not isinstance(data[key], expected_type):
            raise TypeError(
                f"Configuration key '{key}' must be of type {expected_type.__name__}."
            )

    def _validate_agent_permissions(
        self,
        agent_permissions: dict[str, Any],
        allowed_tools: dict[str, Any],
    ) -> None:
        for agent_id, agent_tools in agent_permissions.items():
            if not isinstance(agent_id, str) or not agent_id.strip():
                raise TypeError("Each agent ID in 'agent_permissions' must be a non-empty string.")

            if not isinstance(agent_tools, list):
                raise TypeError(
                    f"'agent_permissions[{agent_id}]' must be a list of tool names."
                )

            for tool_name in agent_tools:
                if not isinstance(tool_name, str) or not tool_name.strip():
                    raise TypeError(
                        f"Every tool listed for agent '{agent_id}' must be a non-empty string."
                    )

                if tool_name not in allowed_tools:
                    raise ValueError(
                        f"Agent '{agent_id}' references unknown tool '{tool_name}' "
                        f"which is not defined in 'allowed_tools'."
                    )

    def _validate_tool_schemas(self, tool_schemas: dict[str, Any]) -> None:
        for tool_name, schema in tool_schemas.items():
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise TypeError("Each tool name in 'allowed_tools' must be a non-empty string.")

            if not isinstance(schema, dict):
                raise TypeError(f"Schema for tool '{tool_name}' must be a dictionary.")

            arguments = schema.get("arguments")
            if not isinstance(arguments, dict) or not arguments:
                raise TypeError(
                    f"Tool '{tool_name}' must define a non-empty 'arguments' dictionary."
                )

            for arg_name, arg_type in arguments.items():
                if not isinstance(arg_name, str) or not arg_name.strip():
                    raise TypeError(
                        f"Tool '{tool_name}' has an invalid argument name: '{arg_name}'."
                    )

                if arg_type not in self.SUPPORTED_SCHEMA_TYPES:
                    supported = ", ".join(sorted(self.SUPPORTED_SCHEMA_TYPES))
                    raise ValueError(
                        f"Tool '{tool_name}' argument '{arg_name}' uses unsupported type "
                        f"'{arg_type}'. Supported types: {supported}"
                    )

            required = schema.get("required", list(arguments.keys()))
            if not isinstance(required, list):
                raise TypeError(f"Tool '{tool_name}' field 'required' must be a list.")

            for arg_name in required:
                if not isinstance(arg_name, str) or not arg_name.strip():
                    raise TypeError(
                        f"Tool '{tool_name}' field 'required' must contain only non-empty strings."
                    )

                if arg_name not in arguments:
                    raise ValueError(
                        f"Tool '{tool_name}' marks '{arg_name}' as required, but it is not "
                        f"declared in 'arguments'."
                    )

            path_fields = schema.get("path_fields", [])
            if not isinstance(path_fields, list):
                raise TypeError(f"Tool '{tool_name}' field 'path_fields' must be a list.")

            for field_name in path_fields:
                if not isinstance(field_name, str) or not field_name.strip():
                    raise TypeError(
                        f"Tool '{tool_name}' field 'path_fields' must contain only non-empty strings."
                    )

                if field_name not in arguments:
                    raise ValueError(
                        f"Tool '{tool_name}' path field '{field_name}' is not declared in "
                        f"'arguments'."
                    )

                if arguments[field_name] != "string":
                    raise ValueError(
                        f"Tool '{tool_name}' path field '{field_name}' must have type 'string'."
                    )

    def _validate_transport_config(self, transport: dict[str, Any]) -> None:
        transport_type = transport.get("type")
        if not isinstance(transport_type, str) or not transport_type.strip():
            raise TypeError("'transport.type' must be a non-empty string.")

        supported_transports = {"stdio", "http"}
        if transport_type not in supported_transports:
            supported = ", ".join(sorted(supported_transports))
            raise ValueError(
                f"Unsupported transport type '{transport_type}'. Supported types: {supported}"
            )

        if transport_type == "http":
            host = transport.get("host")
            port = transport.get("port")
            request_timeout_seconds = transport.get("request_timeout_seconds")

            if not isinstance(host, str) or not host.strip():
                raise TypeError("'transport.host' must be a non-empty string for HTTP transport.")

            if not isinstance(port, int) or isinstance(port, bool):
                raise TypeError("'transport.port' must be an integer for HTTP transport.")

            if not (1 <= port <= 65535):
                raise ValueError("'transport.port' must be between 1 and 65535.")

            if not isinstance(request_timeout_seconds, (int, float)) or isinstance(
                request_timeout_seconds, bool
            ):
                raise TypeError(
                    "'transport.request_timeout_seconds' must be a number for HTTP transport."
                )

            if request_timeout_seconds <= 0:
                raise ValueError(
                    "'transport.request_timeout_seconds' must be greater than 0."
                )

    def _validate_routing_endpoints(self, routing_endpoints: dict[str, Any]) -> None:
        for tool_name, endpoint in routing_endpoints.items():
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise TypeError("Each routing endpoint key must be a non-empty string.")

            # Keep route config flexible for now; ToolRouter performs the deeper
            # normalization and validation of fields like url/method/path/headers.
            if not isinstance(endpoint, (str, dict)):
                raise TypeError(
                    f"Routing endpoint for tool '{tool_name}' must be a string or dictionary."
                )

    def _validate_redaction_patterns(self, redaction_patterns: list[Any]) -> None:
        for idx, pattern in enumerate(redaction_patterns):
            # Keep this flexible for now so policy-driven redaction can evolve
            # without forcing a strict schema before all rule shapes are finalized.
            if not isinstance(pattern, (str, dict)):
                raise TypeError(
                    f"Redaction pattern at index {idx} must be a string or dictionary."
                )

    def _validate_rate_limits(self, rate_limits: dict[str, Any]) -> None:
        for scope, rule in rate_limits.items():
            if not isinstance(scope, str) or not scope.strip():
                raise TypeError("Each 'rate_limits' key must be a non-empty string.")

            # Rate limiting is not enforced yet; for now we only preserve a
            # dictionary-shaped config so concrete limiter rules can be added later.
            if not isinstance(rule, dict):
                raise TypeError(f"Rate limit rule for '{scope}' must be a dictionary.")

    def _populate_attributes(self, policy: dict[str, Any]) -> None:
        self.workspace_root = policy["workspace_root"]
        self.transport_config = copy.deepcopy(policy["transport"])
        self.agent_permissions = copy.deepcopy(policy["agent_permissions"])
        self.tool_schemas = copy.deepcopy(policy["allowed_tools"])
        self.routing_endpoints = copy.deepcopy(policy.get("routing_endpoints", {}))
        self.redaction_patterns = copy.deepcopy(policy.get("redaction_patterns", []))
        self.rate_limits = copy.deepcopy(policy.get("rate_limits", {}))

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            raise RuntimeError(
                "PolicyLoader has not loaded a valid policy yet. Call load() first."
            )
