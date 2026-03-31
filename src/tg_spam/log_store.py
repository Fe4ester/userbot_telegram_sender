from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock


@dataclass(slots=True)
class LogEntry:
    timestamp: str
    level: str
    message: str


class InMemoryLogStore:
    def __init__(self, maxlen: int = 3000) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=maxlen)
        self._lock = Lock()

    def add(self, level: str, message: str) -> None:
        entry = LogEntry(
            timestamp=datetime.now(tz=UTC).isoformat(),
            level=level.upper(),
            message=message,
        )
        with self._lock:
            self._entries.append(entry)

    def list(
        self,
        level: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> dict[str, int | list[dict[str, str]]]:
        level_filter = level.upper() if level else None
        with self._lock:
            items = list(self._entries)
        if level_filter:
            items = [item for item in items if item.level == level_filter]
        total = len(items)
        start = max(0, min(offset, total))
        end = min(total, start + limit)
        page_items = items[start:end]
        return {
            "total": total,
            "offset": start,
            "limit": limit,
            "items": [
            {"timestamp": item.timestamp, "level": item.level, "message": item.message}
            for item in page_items
            ],
        }


class InMemoryLogHandler(logging.Handler):
    def __init__(self, store: InMemoryLogStore) -> None:
        super().__init__()
        self._store = store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        self._store.add(record.levelname, message)
