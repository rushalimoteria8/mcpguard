from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import urljoin

import aiohttp

from .router import RouteTarget


@dataclass(frozen=True, slots=True)
class ResponseEnvelope:
    """Normalized upstream response returned to the orchestrator."""

    status_code: int
    is_json: bool
    body: dict[str, Any] | str


class UpstreamClient:
    """
    Sends validated requests to the resolved upstream backend.

    This class owns the aiohttp ClientSession so requests can reuse TCP
    connections through connection pooling rather than creating a new
    connection for every forwarded request.
    """

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        *,
        pool_limit: int = 100,
        pool_limit_per_host: int = 20,
    ) -> None:
        self.timeout_seconds = float(timeout_seconds)
        self.pool_limit = int(pool_limit)
        self.pool_limit_per_host = int(pool_limit_per_host)
        self._session: aiohttp.ClientSession | None = None

    async def forward(self, target: RouteTarget, payload: dict[str, Any]) -> ResponseEnvelope:
        """
        Forward a validated payload to the resolved upstream target.

        Returns a normalized response envelope so callers do not need to care
        whether the upstream returned JSON, plain text, or HTML.
        """
        session = await self._ensure_session()
        url = self._build_url(target)
        headers = dict(target.headers)

        try:
            async with session.request(
                method=target.method,
                url=url,
                json=payload,
                headers=headers,
            ) as response:
                return await self._normalize_response(response)

        except asyncio.TimeoutError:
            return ResponseEnvelope(
                status_code=502,
                is_json=True,
                body={
                    "status": "error",
                    "error": "UPSTREAM_TIMEOUT",
                    "message": f"Upstream request to '{url}' timed out after {self.timeout_seconds} seconds.",
                },
            )

        except aiohttp.ClientError as exc:
            return ResponseEnvelope(
                status_code=502,
                is_json=True,
                body={
                    "status": "error",
                    "error": "BAD_GATEWAY",
                    "message": str(exc),
                },
            )

        except Exception as exc:
            return ResponseEnvelope(
                status_code=502,
                is_json=True,
                body={
                    "status": "error",
                    "error": "UPSTREAM_FAILURE",
                    "message": str(exc),
                },
            )

    async def close(self) -> None:
        """Close the shared ClientSession cleanly during proxy shutdown."""
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            connector = aiohttp.TCPConnector(
                limit=self.pool_limit,
                limit_per_host=self.pool_limit_per_host,
                ttl_dns_cache=300,
            )
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return self._session

    async def _normalize_response(self, response: aiohttp.ClientResponse) -> ResponseEnvelope:
        content_type = response.headers.get("Content-Type", "").lower()
        text_body = await response.text()
        declared_json = "application/json" in content_type

        if declared_json:
            normalized_body = self._normalize_json_body(text_body)
            if normalized_body is not None:
                return ResponseEnvelope(
                    status_code=response.status,
                    is_json=True,
                    body=normalized_body,
                )

        parsed_body = self._normalize_json_body(text_body)
        if parsed_body is not None:
            return ResponseEnvelope(
                status_code=response.status,
                is_json=True,
                body=parsed_body,
            )

        return ResponseEnvelope(
            status_code=response.status,
            is_json=False,
            body=text_body,
        )

    def _build_url(self, target: RouteTarget) -> str:
        if target.path:
            base_url = target.url.rstrip("/") + "/"
            path = target.path.lstrip("/")
            return urljoin(base_url, path)
        return target.url

    def _normalize_json_body(self, raw_body: str) -> dict[str, Any] | None:
        try:
            parsed_body = json.loads(raw_body)
        except json.JSONDecodeError:
            return None

        if isinstance(parsed_body, dict):
            return parsed_body
        return {"data": parsed_body}
