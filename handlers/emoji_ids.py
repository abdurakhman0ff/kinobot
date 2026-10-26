"""/emojiid: yuborilgan premium emoji'larning ID sini qaytaradi (faqat admin)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import users

router = Router()


@router.message(Command("emojiid"))
async def emoji_ids(message: Message) -> None:
    if not users.has_role(message.from_user.id, "admin"):  # type: ignore[union-attr]
        return
    ids = [e.custom_emoji_id for e in (message.entities or []) if e.type == "custom_emoji"]
    if not ids:
        await message.answer("Buyruq yoniga premium emoji yozing, masalan: /emojiid (emoji)")
        return
    await message.answer("\n".join(f"<code>{i}</code>" for i in ids))
