"""Banlangan foydalanuvchi hech narsa qila olmaydi."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, InlineQuery, Message, TelegramObject

import texts as t


class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("db_user")
        if not user or not user.get("is_banned") or data.get("role"):
            return await handler(event, data)
        try:
            if isinstance(event, Message):
                # to'lov tasdig'i baribir qayd etilishi kerak
                if event.successful_payment:
                    return await handler(event, data)
                await event.answer(t.BANNED)
            elif isinstance(event, CallbackQuery):
                await event.answer(t.BANNED, show_alert=True)
            elif isinstance(event, InlineQuery):
                await event.answer([], cache_time=60, is_personal=True)
        except TelegramAPIError:
            pass
        return None
