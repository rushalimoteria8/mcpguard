import sys
import tempfile
from pathlib import Path
import unittest

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "mcpguard"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from security.policy_loader import PolicyLoader
from security.request_validator import RequestValidator


class PolicyLoaderTests(unittest.TestCase):
    def test_loads_valid_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            policy_path = Path(tmpdir) / "policy.yaml"
            policy = {
                "version": "1.0",
                "workspace_root": str(workspace),
                "transport": {"type": "stdio"},
                "routing_endpoints": {
                    "read_file": {"url": "http://127.0.0.1:3001", "method": "POST"}
                },
                "redaction_patterns": [r"ghp_[A-Za-z0-9]{20,}"],
                "agent_permissions": {"admin_agent": ["read_file"]},
                "allowed_tools": {
                    "read_file": {
                        "arguments": {"file_path": "string"},
                        "path_fields": ["file_path"],
                    }
                },
            }
            policy_path.write_text(yaml.safe_dump(policy), encoding="utf-8")

            loader = PolicyLoader(str(policy_path))

            self.assertTrue(loader.load())
            self.assertEqual(loader.get_transport_rules()["type"], "stdio")
            self.assertIn("read_file", loader.get_routing_rules())

    def test_rejects_policy_with_unknown_agent_tool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir) / "workspace"
            workspace.mkdir()
            policy_path = Path(tmpdir) / "policy.yaml"
            policy = {
                "version": "1.0",
                "workspace_root": str(workspace),
                "transport": {"type": "stdio"},
                "agent_permissions": {"admin_agent": ["missing_tool"]},
                "allowed_tools": {
                    "read_file": {
                        "arguments": {"file_path": "string"},
                        "path_fields": ["file_path"],
                    }
                },
            }
            policy_path.write_text(yaml.safe_dump(policy), encoding="utf-8")

            loader = PolicyLoader(str(policy_path))

            self.assertFalse(loader.load())
            self.assertIn("unknown tool", loader.last_error.lower())


class RequestValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.workspace_root = Path(self.tmpdir.name)
        self.validator = RequestValidator(
            workspace_root=str(self.workspace_root),
            agent_permissions={
                "admin_agent": ["read_file", "write_file"],
                "guest_agent": ["read_file"],
            },
            tool_schemas={
                "read_file": {
                    "arguments": {"file_path": "string"},
                    "path_fields": ["file_path"],
                },
                "write_file": {
                    "arguments": {"file_path": "string", "content": "string"},
                    "path_fields": ["file_path"],
                },
            },
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_rejects_malformed_request(self) -> None:
        is_safe, message = self.validator.validate(
            {"tool": "", "parameters": {}},
            agent_id="admin_agent",
        )
        self.assertFalse(is_safe)
        self.assertEqual(message, "MALFORMED_REQUEST")

    def test_blocks_rbac_violation(self) -> None:
        is_safe, message = self.validator.validate(
            {
                "tool": "write_file",
                "parameters": {"file_path": "notes.txt", "content": "hello"},
            },
            agent_id="guest_agent",
        )
        self.assertFalse(is_safe)
        self.assertEqual(message, "RBAC_DENIED")

    def test_blocks_path_traversal(self) -> None:
        is_safe, message = self.validator.validate(
            {
                "tool": "read_file",
                "parameters": {"file_path": "../secret.txt"},
            },
            agent_id="admin_agent",
        )
        self.assertFalse(is_safe)
        self.assertEqual(message, "PATH_TRAVERSAL")
