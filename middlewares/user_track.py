"""Foydalanuvchini bazaga yozadi va handlerlarga `db_user`, `role`, `is_new_user` beradi."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import InlineQuery, Message, TelegramObject, User

from database import users


class UserTrackMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # bot faqat shaxsiy chatda ishlaydi (majburiy obuna guruhlaridagi xabarlar e'tiborsiz)
        if isinstance(event, Message) and event.chat.type != ChatType.PRIVATE:
            return None
        user: User | None = data.get("event_from_user")
        if user is None or user.is_bot:
            return await handler(event, data)
        row, is_new = await users.touch(user, interacted=not isinstance(event, InlineQuery))
        data["db_user"] = row
        data["is_new_user"] = is_new
        data["role"] = users.role_of(user.id)
        return await handler(event, data)
