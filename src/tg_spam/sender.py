from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError

from tg_spam.admin_filter import is_userbot_admin
from tg_spam.config import BroadcastConfig, Target


@dataclass(slots=True)
class SendResult:
    target: str | int
    status: str
    details: str


@dataclass(slots=True)
class TargetState:
    config: Target
    next_run_at: float
    remaining: int | None


def configure_logging(log_level: str, log_file: str) -> None:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


async def run_broadcast(
    config: BroadcastConfig,
    on_result: Callable[[SendResult], None | Awaitable[None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> list[SendResult]:
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    session = os.getenv("TG_SESSION", "userbot")

    if not api_id or not api_hash:
        raise RuntimeError("Set TG_API_ID and TG_API_HASH environment variables.")

    client = TelegramClient(session, int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        raise RuntimeError("Userbot session is not authorized. Complete login in UI first.")
    try:
        return await _run_scheduler(client, config, on_result=on_result, stop_event=stop_event)
    finally:
        await client.disconnect()


async def _run_scheduler(
    client: TelegramClient,
    config: BroadcastConfig,
    on_result: Callable[[SendResult], None | Awaitable[None]] | None = None,
    stop_event: asyncio.Event | None = None,
) -> list[SendResult]:
    results: list[SendResult] = []
    now = monotonic()
    states = [
        TargetState(
            config=t,
            next_run_at=now + t.initial_delay_seconds,
            remaining=_repeat_to_remaining(
                t.repeat if t.repeat is not None else config.dispatch.default_repeat
            ),
        )
        for t in config.targets
        if t.enabled
    ]

    if not states:
        logging.warning("No enabled targets found.")
        return results

    while True:
        if stop_event is not None and stop_event.is_set():
            logging.info("Stop signal received. Finishing scheduler loop.")
            break

        active = [state for state in states if state.remaining is None or state.remaining > 0]
        if not active:
            break

        next_state = min(active, key=lambda s: s.next_run_at)
        sleep_seconds = next_state.next_run_at - monotonic()
        if sleep_seconds > 0:
            should_stop = await _sleep_or_stop(sleep_seconds, stop_event)
            if should_stop:
                logging.info("Stop signal received during wait interval.")
                break

        send_result = await _send_with_retry(client, config, next_state.config, stop_event=stop_event)
        results.append(send_result)
        logging.info("[%s] %s -> %s", send_result.status, send_result.target, send_result.details)
        await _emit_result(send_result, on_result)

        if next_state.remaining is not None:
            next_state.remaining -= 1
        interval = next_state.config.interval_seconds
        if interval is None:
            interval = config.dispatch.default_interval_seconds
        next_state.next_run_at = monotonic() + interval

    return results


async def _send_with_retry(
    client: TelegramClient,
    config: BroadcastConfig,
    target: Target,
    stop_event: asyncio.Event | None = None,
) -> SendResult:
    attempts = config.dispatch.retry_attempts
    retry_delay = config.dispatch.retry_delay_seconds

    for attempt in range(1, attempts + 1):
        if stop_event is not None and stop_event.is_set():
            return SendResult(
                target=target.ref,
                status="stopped",
                details="broadcast stopped before send attempt",
            )
        try:
            result = await _send_once(client, config, target)
        except FloodWaitError as exc:
            wait_for = max(1, int(getattr(exc, "seconds", 1)))
            logging.warning("FloodWait for target %s: %ss", target.ref, wait_for)
            should_stop = await _sleep_or_stop(wait_for, stop_event)
            if should_stop:
                return SendResult(
                    target=target.ref,
                    status="stopped",
                    details="broadcast stopped during flood-wait",
                )
            continue
        if result.status in {"sent", "skipped"}:
            return result

        if attempt < attempts:
            logging.warning(
                "Retrying target %s in %.2fs (%s/%s): %s",
                target.ref,
                retry_delay,
                attempt,
                attempts,
                result.details,
            )
            should_stop = await _sleep_or_stop(retry_delay, stop_event)
            if should_stop:
                return SendResult(
                    target=target.ref,
                    status="stopped",
                    details="broadcast stopped before retry",
                )

    if not config.dispatch.continue_on_error:
        raise RuntimeError(f"Target failed and continue_on_error=false: {target.ref}")
    return result


async def _emit_result(
    result: SendResult,
    callback: Callable[[SendResult], None | Awaitable[None]] | None,
) -> None:
    if callback is None:
        return
    maybe_awaitable = callback(result)
    if asyncio.iscoroutine(maybe_awaitable):
        await maybe_awaitable


async def _send_once(
    client: TelegramClient,
    config: BroadcastConfig,
    target: Target,
) -> SendResult:
    try:
        entity = await client.get_entity(target.ref)
    except FloodWaitError:
        raise
    except (ValueError, RPCError) as exc:
        return SendResult(
            target=target.ref,
            status="skipped",
            details=f"target resolve failed: {exc.__class__.__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        return SendResult(
            target=target.ref,
            status="error",
            details=f"unexpected resolve error: {exc.__class__.__name__}: {exc}",
        )

    if not await is_userbot_admin(client, entity):
        return SendResult(
            target=target.ref,
            status="skipped",
            details="userbot is not admin in this chat",
        )

    try:
        await client.send_message(entity, config.message, parse_mode=config.parse_mode)
    except FloodWaitError:
        raise
    except RPCError as exc:
        return SendResult(
            target=target.ref,
            status="error",
            details=f"send failed: {exc.__class__.__name__}: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        return SendResult(
            target=target.ref,
            status="error",
            details=f"unexpected send error: {exc.__class__.__name__}: {exc}",
        )
    return SendResult(
        target=target.ref,
        status="sent",
        details="message sent successfully",
    )


async def _sleep_or_stop(delay_seconds: float, stop_event: asyncio.Event | None) -> bool:
    if stop_event is None:
        await asyncio.sleep(delay_seconds)
        return False
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=delay_seconds)
        return True
    except TimeoutError:
        return False


def _repeat_to_remaining(repeat_value: int) -> int | None:
    return None if repeat_value == 0 else repeat_value
