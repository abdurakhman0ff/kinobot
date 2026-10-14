"""Adminlarga bildirishnomalar."""
from __future__ import annotations

import logging
import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

import config
from database import users

log = logging.getLogger(__name__)

_last_sent: dict[str, float] = {}


async def owner(bot: Bot, text: str, *, key: str | None = None, every: float = 0,
                kb: InlineKeyboardMarkup | None = None) -> None:
    """Asosiy adminga xabar. `key` + `every` (soniya) bilan takrorlanish cheklanadi."""
    if key and every:
        now = time.monotonic()
        if now - _last_sent.get(key, -every - 1) < every:
            return
        _last_sent[key] = now
    try:
        await bot.send_message(config.ADMIN_ID, text, reply_markup=kb)
    except TelegramAPIError as exc:
        log.warning("Adminga xabar yuborilmadi: %s", exc)


async def staff(bot: Bot, text: str, *, minimum: str = "moderator",
                kb: InlineKeyboardMarkup | None = None) -> None:
    for uid in users.staff_ids(minimum):
        try:
            await bot.send_message(uid, text, reply_markup=kb)
        except TelegramAPIError as exc:
            log.debug("Xodimga (%s) xabar yuborilmadi: %s", uid, exc)
