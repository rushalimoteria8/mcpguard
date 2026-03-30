from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Any


@dataclass(frozen=True, slots=True)
class _ActiveRequest:
    agent_id: str
    target_tool: str
    started_at_ns: int


class AuditLogger:
    """
    Fast, non-blocking frontend for structured audit events.

    This class performs no disk I/O. It tracks active requests in memory,
    computes final latency, formats a flat JSON-ready dictionary, and drops
    completed events onto the shared queue for the background flusher.
    """

    def __init__(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.queue = queue
        self._active_requests: dict[str, _ActiveRequest] = {}

    def start_request(self, request_id: str, agent_id: str, target_tool: str) -> None:
        self._active_requests[request_id] = _ActiveRequest(
            agent_id=agent_id,
            target_tool=target_tool,
            started_at_ns=time.perf_counter_ns(),
        )

    def finish_request(
        self,
        request_id: str,
        status_code: int,
        error_message: str | None = None,
    ) -> None:
        active_request = self._active_requests.pop(request_id, None)
        if active_request is None:
            return

        finished_at_ns = time.perf_counter_ns()
        latency_ms = (finished_at_ns - active_request.started_at_ns) / 1_000_000

        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
            "agent_id": active_request.agent_id,
            "target_tool": active_request.target_tool,
            "status_code": int(status_code),
            "error_message": error_message,
            "latency_ms": round(latency_ms, 3),
        }
        self.queue.put_nowait(event)
