from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from tg_spam.log_store import InMemoryLogHandler, InMemoryLogStore
from tg_spam.paths import SESSIONS_DIR
from tg_spam.sender import SendResult, configure_logging, run_broadcast
from tg_spam.settings_store import AppSettings, get_active_userbot


@dataclass(slots=True)
class RuntimeState:
    running: bool
    started_at: str | None = None
    finished_at: str | None = None
    last_error: str | None = None
    results_count: int = 0


class BroadcastService:
    def __init__(self, log_store: InMemoryLogStore) -> None:
        self._log_store = log_store
        self._runtime = RuntimeState(running=False)
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._lock = asyncio.Lock()

    async def start(self, settings: AppSettings) -> None:
        async with self._lock:
            if self._task and not self._task.done():
                raise RuntimeError("Broadcast is already running.")

            account = get_active_userbot(settings)
            configure_logging(account.broadcast.logging.level, account.broadcast.logging.file)
            self._attach_memory_log_handler()
            self._set_env(settings)

            self._stop_event = asyncio.Event()
            self._runtime = RuntimeState(
                running=True,
                started_at=datetime.now(tz=UTC).isoformat(),
                finished_at=None,
                last_error=None,
                results_count=0,
            )
            self._task = asyncio.create_task(self._run(settings))

    async def stop(self) -> None:
        async with self._lock:
            if not self._task or self._task.done():
                return
            if self._stop_event is not None:
                self._stop_event.set()
            try:
                await asyncio.wait_for(self._task, timeout=20)
            except TimeoutError:
                self._task.cancel()
                await asyncio.gather(self._task, return_exceptions=True)
                logging.warning("Broadcast task was force-cancelled after stop timeout.")

    def status(self) -> dict[str, str | int | bool | None]:
        return {
            "running": self._runtime.running,
            "started_at": self._runtime.started_at,
            "finished_at": self._runtime.finished_at,
            "last_error": self._runtime.last_error,
            "results_count": self._runtime.results_count,
        }

    async def _run(self, settings: AppSettings) -> None:
        account = get_active_userbot(settings)
        try:
            results = await run_broadcast(
                account.broadcast,
                on_result=self._on_result,
                stop_event=self._stop_event,
            )
            self._runtime.results_count = len(results)
        except Exception as exc:  # noqa: BLE001
            self._runtime.last_error = str(exc)
            logging.exception("Broadcast crashed: %s", exc)
        finally:
            self._runtime.running = False
            self._runtime.finished_at = datetime.now(tz=UTC).isoformat()

    def _on_result(self, result: SendResult) -> None:
        self._runtime.results_count += 1
        self._log_store.add(
            "INFO",
            f"result [{result.status}] {result.target} -> {result.details}",
        )

    def _set_env(self, settings: AppSettings) -> None:
        account = get_active_userbot(settings)
        if not account.api_id or not account.api_hash:
            raise RuntimeError("Userbot api_id and api_hash must be set in UI settings.")
        os.environ["TG_API_ID"] = account.api_id
        os.environ["TG_API_HASH"] = account.api_hash
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        session_name = account.session or "userbot"
        os.environ["TG_SESSION"] = str(SESSIONS_DIR / session_name)

    def _attach_memory_log_handler(self) -> None:
        root = logging.getLogger()
        for handler in root.handlers:
            if isinstance(handler, InMemoryLogHandler):
                return
        memory_handler = InMemoryLogHandler(self._log_store)
        memory_handler.setLevel(logging.DEBUG)
        memory_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        root.addHandler(memory_handler)
