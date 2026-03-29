from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from typing import Any


class RoutingError(Exception):
    """Raised when a request cannot be mapped to an upstream route."""


@dataclass(frozen=True, slots=True)
class RouteTarget:
    """The resolved upstream target for a tool request."""

    url: str
    headers: dict[str, str]
    method: str = "POST"
    path: str | None = None


class ToolRouter:
    """
    Resolves a validated tool request to an upstream destination.

    V1 uses an in-memory routing table for constant-time lookups, but the
    interface is asynchronous so the implementation can later be upgraded to
    fetch routes from a remote store such as Redis without breaking callers.
    """

    def __init__(
        self,
        routing_table: dict[str, Any] | None = None,
        *,
        env_prefix: str = "MCPGUARD_ROUTE_",
    ) -> None:
        self.env_prefix = env_prefix
        self.routing_table = self._load_routing_table(routing_table or {})

    @classmethod
    def from_environment(cls, *, env_prefix: str = "MCPGUARD_ROUTE_") -> "ToolRouter":
        """method to build a router from environment variables only."""
        return cls({}, env_prefix=env_prefix)

    async def resolve(self, request: dict[str, Any]) -> RouteTarget:
        """
        Resolve a validated request to its upstream target.

        Expected input shape:
            {"tool": "github_read", ...}
        """
        tool_name = request.get("tool")
        if not isinstance(tool_name, str) or not tool_name.strip():
            raise RoutingError("ROUTING_MALFORMED_REQUEST")

        route = self.routing_table.get(tool_name)
        if route is None:
            raise RoutingError(f"ROUTE_NOT_FOUND:{tool_name}")

        return route

    def _load_routing_table(self, config_routes: dict[str, Any]) -> dict[str, RouteTarget]:
        """
        Merge routes from config and environment into a normalized in-memory map.

        Environment variables can override configured URLs using:
            MCPGUARD_ROUTE_<TOOL_NAME>=https://service.internal/path
        Example:
            MCPGUARD_ROUTE_GITHUB_READ=https://github-proxy.internal/api/read
        """
        normalized_routes: dict[str, RouteTarget] = {}

        for tool_name, route_config in config_routes.items():
            normalized_routes[tool_name] = self._normalize_route(tool_name, route_config)

        for env_key, env_value in os.environ.items():
            if not env_key.startswith(self.env_prefix):
                continue

            tool_name = env_key[len(self.env_prefix) :].lower()
            normalized_routes[tool_name] = RouteTarget(
                url=env_value,
                headers={},
                method="POST",
                path=None,
            )

        return normalized_routes

    def _normalize_route(self, tool_name: str, route_config: Any) -> RouteTarget:
        """
        Normalize one route definition into a RouteTarget.

        Supported config shapes:
            routing_endpoints:
              github_read: "https://github.internal/read"

              github_write:
                url: "https://github.internal"
                method: "POST"
                path: "/write"
                headers:
                  x-service: "github"
        """
        if isinstance(route_config, str):
            return RouteTarget(url=route_config, headers={}, path=None)

        if not isinstance(route_config, dict):
            raise RoutingError(
                f"INVALID_ROUTE_CONFIG:{tool_name}: route must be a string or dictionary"
            )

        url = route_config.get("url")
        if not isinstance(url, str) or not url.strip():
            raise RoutingError(
                f"INVALID_ROUTE_CONFIG:{tool_name}: missing non-empty 'url'"
            )

        path = route_config.get("path")
        if path is not None and not isinstance(path, str):
            raise RoutingError(
                f"INVALID_ROUTE_CONFIG:{tool_name}: 'path' must be a string if provided"
            )

        method = route_config.get("method", "POST")
        if not isinstance(method, str) or not method.strip():
            raise RoutingError(
                f"INVALID_ROUTE_CONFIG:{tool_name}: 'method' must be a non-empty string"
            )

        headers = route_config.get("headers", {})
        if not isinstance(headers, dict):
            raise RoutingError(
                f"INVALID_ROUTE_CONFIG:{tool_name}: 'headers' must be a dictionary"
            )

        normalized_headers: dict[str, str] = {}
        for header_name, header_value in headers.items():
            if not isinstance(header_name, str) or not header_name.strip():
                raise RoutingError(
                    f"INVALID_ROUTE_CONFIG:{tool_name}: header names must be non-empty strings"
                )
            if not isinstance(header_value, str):
                raise RoutingError(
                    f"INVALID_ROUTE_CONFIG:{tool_name}: header values must be strings"
                )
            normalized_headers[header_name] = header_value

        return RouteTarget(
            url=url,
            headers=copy.deepcopy(normalized_headers),
            method=method.strip().upper(),
            path=path,
        )
