from __future__ import annotations

import argparse
import ctypes
import multiprocessing
import os
import socket
import sys
import traceback
import threading
import time
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

APP_NAME = "TG Broadcaster"


def main() -> None:
    multiprocessing.freeze_support()
    app_dir = _resolve_app_dir()
    try:
        import uvicorn
        parser = argparse.ArgumentParser(description="Run tg-spam UI in browser")
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8787)
        parser.add_argument("--no-open", action="store_true")
        args = parser.parse_args()

        # Import lazily so import-time crashes are also caught and logged.
        from tg_spam.ui_app import app as fastapi_app

        port = _pick_available_port(args.host, args.port, tries=40)
        base_url = f"http://{args.host}:{port}"
        if not args.no_open:
            threading.Thread(target=_open_browser_delayed, args=(base_url,), daemon=True).start()

        _write_launcher_log(app_dir, f"starting server on {base_url}")
        config = uvicorn.Config(
            app=fastapi_app,
            host=args.host,
            port=port,
            reload=False,
            log_level="info",
            access_log=False,
        )
        server = uvicorn.Server(config)
        server.run()
    except Exception as exc:  # noqa: BLE001
        _write_crash_log(app_dir, exc)
        _show_error_message(app_dir, exc)
        sys.exit(1)


def _open_browser_delayed(url: str) -> None:
    time.sleep(1.0)
    webbrowser.open(url)


def _pick_available_port(host: str, start_port: int, tries: int) -> int:
    for port in range(start_port, start_port + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex((host, port)) != 0:
                return port
    raise RuntimeError("No free port found for UI.")


def _resolve_app_dir() -> Path:
    if os.name == "nt":
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
    return Path.home() / ".tg_broadcaster"


def _write_crash_log(app_dir: Path, exc: Exception) -> None:
    app_dir.mkdir(parents=True, exist_ok=True)
    crash_path = app_dir / "crash.log"
    timestamp = datetime.now(tz=UTC).isoformat()
    with crash_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} | {exc.__class__.__name__}: {exc}\n")
        fh.write(traceback.format_exc())
        fh.write("\n")


def _write_launcher_log(app_dir: Path, message: str) -> None:
    app_dir.mkdir(parents=True, exist_ok=True)
    path = app_dir / "launcher.log"
    timestamp = datetime.now(tz=UTC).isoformat()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} | {message}\n")


def _show_error_message(app_dir: Path, exc: Exception) -> None:
    try:
        text = (
            "TG-Broadcaster crashed at startup.\n\n"
            f"{exc.__class__.__name__}: {exc}\n\n"
            f"Check log:\n{app_dir / 'crash.log'}"
        )
        ctypes.windll.user32.MessageBoxW(0, text, "TG-Broadcaster error", 0x10)
    except Exception:
        pass


if __name__ == "__main__":
    main()
