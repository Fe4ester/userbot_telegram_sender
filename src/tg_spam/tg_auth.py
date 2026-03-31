from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from time import monotonic

from telethon import TelegramClient
from telethon.errors import RPCError, SessionPasswordNeededError

from tg_spam.paths import SESSIONS_DIR


@dataclass(slots=True)
class PendingCode:
    phone: str
    phone_code_hash: str
    expires_at: float


class TelegramAuthService:
    def __init__(self) -> None:
        self._pending: dict[str, PendingCode] = {}
        self._lock = asyncio.Lock()

    async def auth_status(self, api_id: str, api_hash: str, session: str) -> dict[str, bool]:
        async with self._build_client(api_id, api_hash, session) as client:
            return {"authorized": await client.is_user_authorized()}

    async def send_code(
        self,
        api_id: str,
        api_hash: str,
        session: str,
        phone: str,
    ) -> dict[str, str]:
        async with self._lock:
            async with self._build_client(api_id, api_hash, session) as client:
                sent = await client.send_code_request(phone=phone)
                self._pending[session] = PendingCode(
                    phone=phone,
                    phone_code_hash=sent.phone_code_hash,
                    expires_at=monotonic() + 300,
                )
        return {"status": "code_sent"}

    async def verify_code(
        self,
        api_id: str,
        api_hash: str,
        session: str,
        code: str,
    ) -> dict[str, str]:
        async with self._lock:
            pending = self._pending.get(session)
            if pending is None or pending.expires_at < monotonic():
                raise RuntimeError("Код не запрошен или истек. Запроси код заново.")

            async with self._build_client(api_id, api_hash, session) as client:
                try:
                    await client.sign_in(
                        phone=pending.phone,
                        code=code,
                        phone_code_hash=pending.phone_code_hash,
                    )
                except SessionPasswordNeededError:
                    return {"status": "password_required"}

        return {"status": "ok"}

    async def verify_password(
        self,
        api_id: str,
        api_hash: str,
        session: str,
        password: str,
    ) -> dict[str, str]:
        async with self._build_client(api_id, api_hash, session) as client:
            await client.sign_in(password=password)
        return {"status": "ok"}

    async def list_chats(
        self,
        api_id: str,
        api_hash: str,
        session: str,
        limit: int = 100,
        offset: int = 0,
        scan_limit: int = 1500,
    ) -> dict[str, int | list[dict[str, str | int]]]:
        items: list[dict[str, str | int]] = []
        async with self._build_client(api_id, api_hash, session) as client:
            if not await client.is_user_authorized():
                raise RuntimeError("Сессия не авторизована. Выполни вход в Userbot.")

            async for dialog in client.iter_dialogs(limit=scan_limit):
                entity = dialog.entity
                is_regular_group = dialog.is_group
                is_megagroup = bool(getattr(entity, "megagroup", False))
                if not (is_regular_group or is_megagroup):
                    continue
                items.append(
                    {
                        "id": int(dialog.id),
                        "title": dialog.name or f"chat_{dialog.id}",
                        "username": getattr(entity, "username", "") or "",
                        "type": "group",
                    }
                )
        total = len(items)
        start = max(0, min(offset, total))
        end = min(total, start + limit)
        return {
            "total": total,
            "offset": start,
            "limit": limit,
            "items": items[start:end],
        }

    async def status_summary(self, api_id: str, api_hash: str, session: str) -> dict[str, str | int | bool]:
        async with self._build_client(api_id, api_hash, session) as client:
            authorized = await client.is_user_authorized()
            if not authorized:
                return {
                    "authorized": False,
                    "spam_block_state": "unknown",
                    "spam_block_message": "Сессия не авторизована.",
                    "is_premium": False,
                    "groups_count": 0,
                }

            me = await client.get_me()
            groups_count = 0
            async for dialog in client.iter_dialogs(limit=800):
                entity = dialog.entity
                if dialog.is_group or bool(getattr(entity, "megagroup", False)):
                    groups_count += 1

            spam_state, spam_message = await self._check_spam_block(client)
            return {
                "authorized": True,
                "account_name": f"{(me.first_name or '').strip()} {(me.last_name or '').strip()}".strip(),
                "username": (me.username or ""),
                "phone": (me.phone or ""),
                "is_premium": bool(getattr(me, "premium", False)),
                "groups_count": groups_count,
                "spam_block_state": spam_state,
                "spam_block_message": spam_message,
            }

    async def _check_spam_block(self, client: TelegramClient) -> tuple[str, str]:
        try:
            async with client.conversation("@SpamBot", timeout=15) as conv:
                await conv.send_message("/start")
                response = await asyncio.wait_for(conv.get_response(), timeout=15)
                text = (response.raw_text or "").strip()
        except Exception as exc:  # noqa: BLE001
            return "unknown", f"Не удалось проверить @SpamBot: {exc}"

        lowered = text.lower()
        blocked_markers = ["limited", "огранич", "cannot", "не можете", "spam complaints"]
        is_blocked = any(marker in lowered for marker in blocked_markers)
        state = "blocked" if is_blocked else "clear"
        return state, text[:1200]

    class _build_client:
        def __init__(self, api_id: str, api_hash: str, session: str) -> None:
            if not api_id or not api_hash:
                raise RuntimeError("Заполни api_id и api_hash.")
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            session_name = session or "userbot"
            self._client = TelegramClient(str(SESSIONS_DIR / session_name), int(api_id), api_hash)

        async def __aenter__(self) -> TelegramClient:
            await self._client.connect()
            return self._client

        async def __aexit__(self, exc_type, exc, tb) -> None:
            with suppress(RPCError):
                await self._client.disconnect()
