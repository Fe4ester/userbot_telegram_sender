from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

import uvicorn

from tg_spam.paths import APP_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tg-spam UI in browser")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    try:
        port = _pick_available_port(args.host, args.port, tries=40)
        base_url = f"http://{args.host}:{port}"
        if not args.no_open:
            threading.Thread(target=_open_browser_delayed, args=(base_url,), daemon=True).start()

        uvicorn.run(
            "tg_spam.ui_app:app",
            host=args.host,
            port=port,
            reload=False,
        )
    except Exception as exc:  # noqa: BLE001
        _write_crash_log(exc)
        raise


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


def _write_crash_log(exc: Exception) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    crash_path = APP_DIR / "crash.log"
    timestamp = datetime.now(tz=UTC).isoformat()
    with crash_path.open("a", encoding="utf-8") as fh:
        fh.write(f"{timestamp} | {exc.__class__.__name__}: {exc}\n")
