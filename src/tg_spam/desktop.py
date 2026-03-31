from __future__ import annotations

import argparse
import threading

import uvicorn
import webview

from tg_spam.ui_app import wait_until_ready


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tg-spam desktop UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--width", type=int, default=1240)
    parser.add_argument("--height", type=int, default=860)
    args = parser.parse_args()

    server = _build_server(args.host, args.port)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{args.host}:{args.port}"
    import asyncio

    asyncio.run(wait_until_ready(base_url))
    webview.create_window(
        "TG Рассылка",
        base_url,
        width=args.width,
        height=args.height,
        min_size=(980, 700),
    )
    webview.start()


def _build_server(host: str, port: int) -> uvicorn.Server:
    config = uvicorn.Config("tg_spam.ui_app:app", host=host, port=port, reload=False, log_level="info")
    return uvicorn.Server(config)
