from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class Target:
    ref: str | int
    enabled: bool = True
    interval_seconds: float | None = None
    initial_delay_seconds: float = 0.0
    repeat: int | None = None


@dataclass(slots=True)
class DispatchConfig:
    default_interval_seconds: float = 0.0
    default_repeat: int = 0
    retry_attempts: int = 1
    retry_delay_seconds: float = 2.0
    continue_on_error: bool = True


@dataclass(slots=True)
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/broadcast.log"


@dataclass(slots=True)
class BroadcastConfig:
    message: str
    parse_mode: str
    targets: list[Target]
    dispatch: DispatchConfig
    logging: LoggingConfig


def load_config(path: str | Path) -> BroadcastConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ValueError("Config root must be a YAML mapping.")

    message = data.get("message")
    if not isinstance(message, str) or not message.strip():
        raise ValueError("Config field 'message' must be a non-empty string.")

    parse_mode = _read_parse_mode(data.get("parse_mode", "html"))

    raw_targets = data.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise ValueError("Config field 'targets' must be a non-empty list.")

    targets = [_parse_target(item) for item in raw_targets]

    dispatch_data = data.get("dispatch", {})
    if not isinstance(dispatch_data, dict):
        raise ValueError("Config field 'dispatch' must be a mapping.")

    logging_data = data.get("logging", {})
    if not isinstance(logging_data, dict):
        raise ValueError("Config field 'logging' must be a mapping.")

    dispatch = DispatchConfig(
        default_interval_seconds=_read_float(dispatch_data, "default_interval_seconds", 0.0),
        default_repeat=_read_non_negative_int(dispatch_data, "default_repeat", 0),
        retry_attempts=_read_positive_int(dispatch_data, "retry_attempts", 1),
        retry_delay_seconds=_read_float(dispatch_data, "retry_delay_seconds", 2.0),
        continue_on_error=bool(dispatch_data.get("continue_on_error", True)),
    )
    logging = LoggingConfig(
        level=_read_str(logging_data, "level", "INFO").upper(),
        file=_read_str(logging_data, "file", "logs/broadcast.log"),
    )
    return BroadcastConfig(
        message=message,
        parse_mode=parse_mode,
        targets=targets,
        dispatch=dispatch,
        logging=logging,
    )


def _parse_target(item: Any) -> Target:
    if isinstance(item, int):
        return Target(ref=item)
    if isinstance(item, str) and item.strip():
        return Target(ref=item.strip())
    if isinstance(item, dict):
        ref = _extract_target_ref(item)
        return Target(
            ref=ref,
            enabled=bool(item.get("enabled", True)),
            interval_seconds=_read_optional_float(item, "interval_seconds"),
            initial_delay_seconds=_read_float(item, "initial_delay_seconds", 0.0),
            repeat=_read_optional_non_negative_int(item, "repeat"),
        )
    raise ValueError(
        "Each target must be int, str, or mapping with 'id'/'link'/'ref'."
    )


def _extract_target_ref(data: dict[str, Any]) -> str | int:
    raw_ref = data.get("ref")
    if isinstance(raw_ref, int):
        return raw_ref
    if isinstance(raw_ref, str) and raw_ref.strip():
        return raw_ref.strip()

    raw_id = data.get("id")
    if isinstance(raw_id, int):
        return raw_id

    raw_link = data.get("link")
    if isinstance(raw_link, str) and raw_link.strip():
        return raw_link.strip()

    raise ValueError("Target mapping must include a valid 'ref', 'id' or 'link'.")


def _read_float(data: dict[str, Any], key: str, default: float) -> float:
    value = data.get(key, default)
    if isinstance(value, int | float):
        if value < 0:
            raise ValueError(f"Config field '{key}' must be >= 0.")
        return float(value)
    raise ValueError(f"Config field '{key}' must be a number.")


def _read_optional_float(data: dict[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, int | float) and value >= 0:
        return float(value)
    raise ValueError(f"Config field '{key}' must be null or a number >= 0.")


def _read_positive_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, int) and value > 0:
        return value
    raise ValueError(f"Config field '{key}' must be an integer > 0.")


def _read_optional_positive_int(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, int) and value > 0:
        return value
    raise ValueError(f"Config field '{key}' must be null or an integer > 0.")


def _read_non_negative_int(data: dict[str, Any], key: str, default: int) -> int:
    value = data.get(key, default)
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError(f"Config field '{key}' must be an integer >= 0.")


def _read_optional_non_negative_int(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, int) and value >= 0:
        return value
    raise ValueError(f"Config field '{key}' must be null or an integer >= 0.")


def _read_str(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError(f"Config field '{key}' must be a non-empty string.")


def _read_parse_mode(value: Any) -> str:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"html", "md"}:
            return normalized
    raise ValueError("Config field 'parse_mode' must be 'html' or 'md'.")
