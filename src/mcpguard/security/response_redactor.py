from __future__ import annotations

import asyncio
import re
from typing import Any, Pattern

from routing import ResponseEnvelope


class ResponseRedactor:
    """
    Scrubs sensitive values from upstream responses before they leave MCPGuard.

    The main entrypoint is async so it fits naturally into the proxy pipeline,
    while the actual redaction work stays in synchronous helper methods.
    """

    DEFAULT_SECRET_PATTERNS: dict[str, Pattern[str]] = {
        "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
        "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", re.IGNORECASE),
    }

    DEFAULT_SENSITIVE_KEYS: frozenset[str] = frozenset(
        {
            "password",
            "api_key",
            "apikey",
            "secret",
            "token",
            "access_token",
            "refresh_token",
            "client_secret",
            "authorization",
        }
    )

    SECRET_REPLACEMENT = "[REDACTED_SECRET]"
    KEY_REPLACEMENT = "[REDACTED]"

    def __init__(
        self,
        *,
        secret_patterns: dict[str, Pattern[str]] | None = None,
        sensitive_keys: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.secret_patterns = dict(secret_patterns or self.DEFAULT_SECRET_PATTERNS)
        self.sensitive_keys = {
            key.strip().lower()
            for key in (sensitive_keys or self.DEFAULT_SENSITIVE_KEYS)
            if isinstance(key, str) and key.strip()
        }

    async def redact(self, envelope: ResponseEnvelope) -> ResponseEnvelope:
        """Return a new envelope with sensitive content scrubbed."""
        return await asyncio.to_thread(self._redact_sync, envelope)

    def _redact_sync(self, envelope: ResponseEnvelope) -> ResponseEnvelope:
        if envelope.is_json:
            cleaned_body = self._redact_json_value(envelope.body)
        else:
            cleaned_body = self._scrub_text(str(envelope.body))

        return ResponseEnvelope(
            status_code=envelope.status_code,
            is_json=envelope.is_json,
            body=cleaned_body,
        )

    def _redact_json_value(self, value: Any, *, parent_key: str | None = None) -> Any:
        if parent_key is not None and parent_key.lower() in self.sensitive_keys:
            return self.KEY_REPLACEMENT

        if isinstance(value, dict):
            return {
                key: self._redact_json_value(child, parent_key=str(key))
                for key, child in value.items()
            }

        if isinstance(value, list):
            return [self._redact_json_value(item, parent_key=parent_key) for item in value]

        if isinstance(value, str):
            return self._scrub_text(value)

        return value

    def _scrub_text(self, text: str) -> str:
        scrubbed = text
        for pattern in self.secret_patterns.values():
            scrubbed = pattern.sub(self.SECRET_REPLACEMENT, scrubbed)
        return scrubbed
