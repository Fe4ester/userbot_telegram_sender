from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from tg_spam.config import BroadcastConfig, DispatchConfig, LoggingConfig, Target
from tg_spam.paths import LOGS_DIR, SETTINGS_PATH


@dataclass(slots=True)
class UserbotAccount:
    id: str
    name: str
    api_id: str
    api_hash: str
    session: str
    broadcast: BroadcastConfig


@dataclass(slots=True)
class AppSettings:
    userbots: list[UserbotAccount]
    active_userbot_id: str


DEFAULT_SETTINGS_PATH = SETTINGS_PATH


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    settings_path = Path(path)
    if not settings_path.exists():
        return _default_settings()

    with settings_path.open("r", encoding="utf-8") as fh:
        raw_data = yaml.safe_load(fh) or {}

    if not isinstance(raw_data, dict):
        raise ValueError("Settings root must be a YAML mapping.")

    userbots = _parse_userbots(raw_data)
    active_userbot_id = _parse_active_userbot_id(raw_data, userbots)
    return AppSettings(userbots=userbots, active_userbot_id=active_userbot_id)


def save_settings(settings: AppSettings, path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with settings_path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(
            {
                "userbots": [_account_to_dict(acc) for acc in settings.userbots],
                "active_userbot_id": settings.active_userbot_id,
            },
            fh,
            allow_unicode=False,
            sort_keys=False,
        )


def settings_to_dict(settings: AppSettings) -> dict[str, Any]:
    active = get_active_userbot(settings)
    return {
        "userbots": [_account_to_dict(acc) for acc in settings.userbots],
        "active_userbot_id": settings.active_userbot_id,
        "active_userbot": _account_to_dict(active),
    }


def settings_from_dict(raw_data: dict[str, Any]) -> AppSettings:
    if not isinstance(raw_data, dict):
        raise ValueError("Payload must be an object.")
    userbots = _parse_userbots(raw_data)
    active_userbot_id = _parse_active_userbot_id(raw_data, userbots)
    return AppSettings(userbots=userbots, active_userbot_id=active_userbot_id)


def get_active_userbot(settings: AppSettings) -> UserbotAccount:
    for account in settings.userbots:
        if account.id == settings.active_userbot_id:
            return account
    raise ValueError("Active userbot is not present in settings.")


def _account_to_dict(account: UserbotAccount) -> dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "api_id": account.api_id,
        "api_hash": account.api_hash,
        "session": account.session,
        "broadcast": broadcast_to_dict(account.broadcast),
    }


def broadcast_to_dict(config: BroadcastConfig) -> dict[str, Any]:
    return {
        "message": config.message,
        "parse_mode": config.parse_mode,
        "targets": [
            {
                "ref": t.ref,
                "enabled": t.enabled,
                "interval_seconds": t.interval_seconds,
                "initial_delay_seconds": t.initial_delay_seconds,
                "repeat": t.repeat,
            }
            for t in config.targets
        ],
        "dispatch": asdict(config.dispatch),
        "logging": asdict(config.logging),
    }


def _parse_userbots(raw: dict[str, Any]) -> list[UserbotAccount]:
    fallback_broadcast = _parse_broadcast(raw.get("broadcast", {}))

    # Backward compatibility: legacy single userbot object.
    if "userbot" in raw and "userbots" not in raw:
        single = _parse_single_userbot(raw.get("userbot", {}), fallback_broadcast)
        return [single]

    items = raw.get("userbots")
    if items is None:
        return [_default_account()]
    if not isinstance(items, list) or not items:
        raise ValueError("userbots must be a non-empty list.")

    accounts: list[UserbotAccount] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each userbot must be an object.")
        account_id = str(item.get("id", "")).strip() or _new_id()
        name = str(item.get("name", "")).strip() or f"Userbot {len(accounts) + 1}"
        api_id = str(item.get("api_id", "")).strip()
        api_hash = str(item.get("api_hash", "")).strip()
        session = str(item.get("session", "userbot")).strip() or "userbot"
        broadcast = _parse_broadcast(item.get("broadcast", {}), fallback=fallback_broadcast)
        accounts.append(
            UserbotAccount(
                id=account_id,
                name=name,
                api_id=api_id,
                api_hash=api_hash,
                session=session,
                broadcast=broadcast,
            )
        )
    return accounts


def _parse_single_userbot(data: Any, fallback_broadcast: BroadcastConfig) -> UserbotAccount:
    if not isinstance(data, dict):
        raise ValueError("userbot must be a mapping.")
    return UserbotAccount(
        id=_new_id(),
        name=str(data.get("name", "Userbot 1")).strip() or "Userbot 1",
        api_id=str(data.get("api_id", "")).strip(),
        api_hash=str(data.get("api_hash", "")).strip(),
        session=str(data.get("session", "userbot")).strip() or "userbot",
        broadcast=fallback_broadcast,
    )


def _parse_active_userbot_id(raw: dict[str, Any], userbots: list[UserbotAccount]) -> str:
    active_id = str(raw.get("active_userbot_id", "")).strip()
    if active_id and any(acc.id == active_id for acc in userbots):
        return active_id
    return userbots[0].id


def _parse_broadcast(data: Any, fallback: BroadcastConfig | None = None) -> BroadcastConfig:
    if not isinstance(data, dict):
        data = {}

    if not data and fallback is not None:
        return fallback

    message = str(data.get("message", "")).strip() or "Test message"
    parse_mode = _parse_parse_mode(data.get("parse_mode", "html"))

    raw_targets = data.get("targets", [])
    if not isinstance(raw_targets, list):
        raise ValueError("broadcast.targets must be a list.")

    targets: list[Target] = []
    for item in raw_targets:
        if not isinstance(item, dict):
            raise ValueError("Each target in settings must be an object.")
        ref_value = item.get("ref", item.get("id", item.get("link")))
        if isinstance(ref_value, str):
            ref_value = ref_value.strip()
        if not isinstance(ref_value, int | str) or ref_value == "":
            raise ValueError("Target ref must be a non-empty string or integer.")
        targets.append(
            Target(
                ref=ref_value,
                enabled=bool(item.get("enabled", True)),
                interval_seconds=_optional_non_negative_float(item.get("interval_seconds")),
                initial_delay_seconds=_non_negative_float(item.get("initial_delay_seconds", 0)),
                repeat=_optional_non_negative_int(item.get("repeat")),
            )
        )

    dispatch_data = data.get("dispatch", {})
    if not isinstance(dispatch_data, dict):
        raise ValueError("broadcast.dispatch must be a mapping.")
    dispatch = DispatchConfig(
        default_interval_seconds=_non_negative_float(
            dispatch_data.get("default_interval_seconds", 0)
        ),
        default_repeat=_non_negative_int(dispatch_data.get("default_repeat", 0)),
        retry_attempts=_positive_int(dispatch_data.get("retry_attempts", 3)),
        retry_delay_seconds=_non_negative_float(dispatch_data.get("retry_delay_seconds", 3)),
        continue_on_error=bool(dispatch_data.get("continue_on_error", True)),
    )

    logging_data = data.get("logging", {})
    if not isinstance(logging_data, dict):
        raise ValueError("broadcast.logging must be a mapping.")
    log_level = str(logging_data.get("level", "INFO")).strip().upper() or "INFO"
    log_file = str(logging_data.get("file", "logs/broadcast.log")).strip() or "logs/broadcast.log"
    logging_config = LoggingConfig(level=log_level, file=log_file)

    return BroadcastConfig(
        message=message,
        parse_mode=parse_mode,
        targets=targets,
        dispatch=dispatch,
        logging=logging_config,
    )


def _default_settings() -> AppSettings:
    account = _default_account()
    return AppSettings(userbots=[account], active_userbot_id=account.id)


def _default_account() -> UserbotAccount:
    return UserbotAccount(
        id=_new_id(),
        name="Userbot 1",
        api_id="",
        api_hash="",
        session="userbot",
        broadcast=BroadcastConfig(
            message="Test message",
            parse_mode="html",
            targets=[],
            dispatch=DispatchConfig(default_repeat=0, retry_attempts=3, retry_delay_seconds=3),
            logging=LoggingConfig(level="INFO", file=str(LOGS_DIR / "broadcast.log")),
        ),
    )


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _non_negative_float(value: Any) -> float:
    if isinstance(value, int | float) and value >= 0:
        return float(value)
    raise ValueError("Expected a number >= 0.")


def _optional_non_negative_float(value: Any) -> float | None:
    if value is None:
        return None
    return _non_negative_float(value)


def _positive_int(value: Any) -> int:
    if isinstance(value, int) and value > 0:
        return value
    raise ValueError("Expected an integer > 0.")


def _non_negative_int(value: Any) -> int:
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError("Expected an integer >= 0.")


def _optional_non_negative_int(value: Any) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value)


def _parse_parse_mode(value: Any) -> str:
    if isinstance(value, str):
        mode = value.strip().lower()
        if mode in {"html", "md"}:
            return mode
    raise ValueError("parse_mode must be 'html' or 'md'.")
