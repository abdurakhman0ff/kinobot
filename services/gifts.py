"""Hadya fayllarini saqlash kanaliga ko'chirish va saqlangan kinoga biriktirish."""
from __future__ import annotations

import json
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import config
from database import gifts, movies, settings
from utils.text import chat_ref

log = logging.getLogger(__name__)


async def store_file(bot: Bot, user_id: int, item: dict[str, Any]) -> tuple[int, int | None, str | None]:
    """Foydalanuvchi yuborgan xabarni saqlash (va zaxira) kanaliga nusxalaydi."""
    res = await bot.copy_message(config.STORAGE_CHANNEL_ID, user_id, item["m"])
    backup_id = None
    backup = chat_ref(settings.get("backup_channel_id"))
    if backup:
        try:
            backup_id = (await bot.copy_message(backup, user_id, item["m"])).message_id
        except TelegramAPIError as exc:
            log.warning("Zaxira kanalga nusxa olinmadi: %s", exc)
    return res.message_id, backup_id, item.get("f")


async def attach(bot: Bot, gift_id: int, movie_id: int) -> None:
    """Kino saqlangach: hadyaning qolgan fayllarini qism sifatida biriktiradi."""
    gift = await gifts.get(gift_id)
    movie = await movies.get(movie_id)
    if not gift or not movie:
        return
    files = json.loads(gift["files"] or "[]")
    if movie["type"] == "serial":
        season, first, rest = 1, 1, files
    else:
        season, first, rest = 0, 2, files[1:]
    for i, item in enumerate(rest):
        try:
            stored = await store_file(bot, int(gift["user_id"]), item)
        except TelegramAPIError as exc:
            log.warning("Hadya qismi saqlanmadi (#%s): %s", gift_id, exc)
            continue
        await movies.save_episode(movie_id, season, first + i, *stored)
    await gifts.set_movie(gift_id, movie_id)
