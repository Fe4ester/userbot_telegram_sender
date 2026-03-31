from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tg_spam.log_store import InMemoryLogStore
from tg_spam.service import BroadcastService
from tg_spam.settings_store import (
    DEFAULT_SETTINGS_PATH,
    AppSettings,
    get_active_userbot,
    load_settings,
    save_settings,
    settings_from_dict,
    settings_to_dict,
)
from tg_spam.tg_auth import TelegramAuthService


WEB_DIR = Path(__file__).parent / "web"


class AppState:
    def __init__(self) -> None:
        self.log_store = InMemoryLogStore(maxlen=5000)
        self.service = BroadcastService(self.log_store)
        self.auth = TelegramAuthService()
        self.settings_path = DEFAULT_SETTINGS_PATH
        self.settings: AppSettings = settings_from_dict({})


state = AppState()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        state.settings = await asyncio.to_thread(load_settings, state.settings_path)
    except ValueError as exc:
        state.log_store.add("ERROR", f"settings.yml parse failed, using defaults: {exc}")
        state.settings = settings_from_dict({})
    yield
    await state.service.stop()


app = FastAPI(title="tg-spam-ui", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=WEB_DIR), name="assets")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    return {
        "settings": settings_to_dict(state.settings),
        "runtime": state.service.status(),
    }


@app.put("/api/state")
async def put_state(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        updated = settings_from_dict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state.settings = updated
    await asyncio.to_thread(save_settings, updated, state.settings_path)
    return {"ok": True}


@app.get("/api/logs")
async def get_logs(
    level: str | None = Query(default=None),
    limit: int = Query(default=300, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    page = state.log_store.list(level=level, limit=limit, offset=offset)
    return page


@app.post("/api/start")
async def start_broadcast() -> dict[str, Any]:
    try:
        await state.service.start(state.settings)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "runtime": state.service.status()}


@app.post("/api/stop")
async def stop_broadcast() -> dict[str, Any]:
    await state.service.stop()
    return {"ok": True, "runtime": state.service.status()}


@app.get("/api/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/send-code")
async def auth_send_code(payload: dict[str, Any]) -> dict[str, Any]:
    creds = _extract_userbot_creds(payload)
    phone = str(payload.get("phone", "")).strip()
    if not phone:
        raise HTTPException(status_code=400, detail="Укажи номер телефона.")
    try:
        result = await state.auth.send_code(
            creds["api_id"],
            creds["api_hash"],
            creds["session"],
            phone,
        )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/verify-code")
async def auth_verify_code(payload: dict[str, Any]) -> dict[str, Any]:
    creds = _extract_userbot_creds(payload)
    code = str(payload.get("code", "")).strip()
    if not code:
        raise HTTPException(status_code=400, detail="Укажи код из Telegram.")
    try:
        result = await state.auth.verify_code(
            creds["api_id"],
            creds["api_hash"],
            creds["session"],
            code,
        )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/verify-password")
async def auth_verify_password(payload: dict[str, Any]) -> dict[str, Any]:
    creds = _extract_userbot_creds(payload)
    password = str(payload.get("password", "")).strip()
    if not password:
        raise HTTPException(status_code=400, detail="Укажи пароль 2FA.")
    try:
        result = await state.auth.verify_password(
            creds["api_id"],
            creds["api_hash"],
            creds["session"],
            password,
        )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/status")
async def auth_status(payload: dict[str, Any]) -> dict[str, Any]:
    creds = _extract_userbot_creds(payload)
    try:
        result = await state.auth.auth_status(
            creds["api_id"],
            creds["api_hash"],
            creds["session"],
        )
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/chats/list")
async def chats_list(payload: dict[str, Any]) -> dict[str, Any]:
    creds = _extract_userbot_creds(payload)
    limit = int(payload.get("limit", 100))
    offset = int(payload.get("offset", 0))
    try:
        page = await state.auth.list_chats(
            creds["api_id"],
            creds["api_hash"],
            creds["session"],
            limit=max(1, min(limit, 1000)),
            offset=max(0, offset),
        )
        return {"ok": True, **page}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/status/check")
async def status_check(payload: dict[str, Any]) -> dict[str, Any]:
    creds = _extract_userbot_creds(payload)
    try:
        summary = await state.auth.status_summary(
            creds["api_id"],
            creds["api_hash"],
            creds["session"],
        )
        return {"ok": True, **summary}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tg-spam UI server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    uvicorn.run(
        "tg_spam.ui_app:app",
        host=args.host,
        port=args.port,
        reload=False,
    )


def _extract_userbot_creds(payload: dict[str, Any]) -> dict[str, str]:
    userbot = payload.get("userbot", {})
    if isinstance(userbot, dict):
        api_id = str(userbot.get("api_id", "")).strip()
        api_hash = str(userbot.get("api_hash", "")).strip()
        session = str(userbot.get("session", "userbot")).strip() or "userbot"
        if api_id and api_hash:
            return {"api_id": api_id, "api_hash": api_hash, "session": session}

    account_id = str(payload.get("account_id", "")).strip()
    if account_id:
        for account in state.settings.userbots:
            if account.id == account_id:
                return {
                    "api_id": account.api_id,
                    "api_hash": account.api_hash,
                    "session": account.session,
                }
        raise HTTPException(status_code=400, detail="Аккаунт не найден.")

    active = get_active_userbot(state.settings)
    if not active.api_id or not active.api_hash:
        raise HTTPException(status_code=400, detail="Заполни api_id и api_hash.")
    return {"api_id": active.api_id, "api_hash": active.api_hash, "session": active.session}


async def wait_until_ready(base_url: str, timeout: float = 10.0) -> None:
    import urllib.request
    from time import monotonic

    end = monotonic() + timeout
    while monotonic() < end:
        try:
            with urllib.request.urlopen(f"{base_url}/api/ping", timeout=1.0) as response:
                if response.status == 200:
                    return
        except Exception:
            await asyncio.sleep(0.2)
    raise RuntimeError("UI server did not start in time.")
