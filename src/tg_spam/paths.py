from __future__ import annotations

import os
from pathlib import Path


def app_data_dir() -> Path:
    # Prefer OS-specific app data location, fallback to user home.
    if os.name == "nt":
        base = Path(os.getenv("APPDATA", Path.home()))
        return base / "TG Broadcaster"
    if os.name == "posix":
        xdg = os.getenv("XDG_CONFIG_HOME")
        if xdg:
            return Path(xdg) / "tg_broadcaster"
    return Path.home() / ".tg_broadcaster"


APP_DIR = app_data_dir()
SETTINGS_PATH = APP_DIR / "settings.yml"
LOGS_DIR = APP_DIR / "logs"
SESSIONS_DIR = APP_DIR / "sessions"
