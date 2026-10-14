"""Anti-spam: xabarlar orasida ~0.7 s, tugmalar orasida ~0.4 s. Adminlar ozod."""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, TelegramObject

import texts as t

STRIKES_TO_MUTE = 5  # 10 soniya ichida shuncha buzilish -> 60 soniya cheklov
STRIKE_WINDOW = 10.0
MUTE_SECONDS = 60.0


@dataclass
class _State:
    last: float = 0.0
    muted_until: float = 0.0
    strikes: deque[float] = field(default_factory=deque)


class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._states: dict[int, _State] = {}

    def _state(self, user_id: int, now: float) -> _State:
        if len(self._states) > 20000:
            self._states = {k: v for k, v in self._states.items() if now - v.last < 300}
        return self._states.setdefault(user_id, _State())

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None or data.get("role"):
            return await handler(event, data)
        if isinstance(event, Message) and (event.successful_payment or event.via_bot):
            return await handler(event, data)

        now = time.monotonic()
        state = self._state(user.id, now)
        if now < state.muted_until:
            await self._quiet(event)
            return None
        if now - state.last < self.interval:
            state.strikes.append(now)
            while state.strikes and now - state.strikes[0] > STRIKE_WINDOW:
                state.strikes.popleft()
            if len(state.strikes) >= STRIKES_TO_MUTE:
                state.strikes.clear()
                state.muted_until = now + MUTE_SECONDS
                await self._warn(event)
            else:
                await self._quiet(event)
            return None
        state.last = now
        return await handler(event, data)

    @staticmethod
    async def _quiet(event: TelegramObject) -> None:
        if isinstance(event, CallbackQuery):
            try:
                await event.answer()
            except TelegramAPIError:
                pass

    @staticmethod
    async def _warn(event: TelegramObject) -> None:
        try:
            if isinstance(event, CallbackQuery):
                await event.answer(t.TOO_FAST, show_alert=True)
            elif isinstance(event, Message):
                await event.answer(t.TOO_FAST)
        except TelegramAPIError:
            pass
