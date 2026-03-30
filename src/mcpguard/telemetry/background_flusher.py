from __future__ import annotations

import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class BackgroundFlusher:
    """
    Background write-behind worker for audit events.

    It drains the shared queue and writes one flat JSON object per line using a
    rotating log file, keeping disk I/O off the request path.
    """

    _SENTINEL = object()

    def __init__(
        self,
        queue: asyncio.Queue[dict[str, Any] | object],
        *,
        log_path: str | Path = "logs/mcpguard_audit.log",
        max_bytes: int = 50 * 1024 * 1024,
        backup_count: int = 5,
    ) -> None:
        self.queue = queue
        self.log_path = Path(log_path)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self._shutdown = False

        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        logger_name = f"mcpguard.audit.{id(self)}"
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        self._handler = RotatingFileHandler(
            self.log_path,
            maxBytes=self.max_bytes,
            backupCount=self.backup_count,
            encoding="utf-8",
        )
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.handlers.clear()
        self._logger.addHandler(self._handler)

    async def flush_loop(self) -> None:
        while True:
            item = await self.queue.get()
            try:
                if item is self._SENTINEL:
                    if self._shutdown and self.queue.empty():
                        break
                    continue

                if not isinstance(item, dict):
                    continue

                await asyncio.to_thread(self._write_entry, item)
            finally:
                self.queue.task_done()

        await asyncio.to_thread(self._close_handler)

    async def shutdown(self) -> None:
        self._shutdown = True
        await self.queue.put(self._SENTINEL)
        await self.queue.join()

    def _write_entry(self, event: dict[str, Any]) -> None:
        self._logger.info(json.dumps(event, separators=(",", ":"), ensure_ascii=True))

    def _close_handler(self) -> None:
        self._handler.flush()
        self._handler.close()
        self._logger.handlers.clear()
