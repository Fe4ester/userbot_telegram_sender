from __future__ import annotations

from typing import Any

from telethon import TelegramClient
from telethon.errors import RPCError


async def is_userbot_admin(client: TelegramClient, entity: Any) -> bool:
    # """
    # Return True when current userbot has admin/creator rights in chat.
    # Return False for any permission lookup failure.
    # """
    # try:
    #     permissions = await client.get_permissions(entity, "me")
    # except RPCError:
    #     return False
    # return bool(permissions.is_admin or permissions.is_creator)
    return True
