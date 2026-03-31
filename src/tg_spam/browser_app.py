from __future__ import annotations

import argparse
import threading
import time
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tg-spam UI in browser")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        threading.Thread(target=_open_browser_delayed, args=(base_url,), daemon=True).start()

    uvicorn.run(
        "tg_spam.ui_app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def _open_browser_delayed(url: str) -> None:
    time.sleep(1.0)
    webbrowser.open(url)
