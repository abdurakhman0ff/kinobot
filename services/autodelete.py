"""Yuborilgan kinolarni N soatdan keyin chatdan o'chirish (seriallar o'chirilmaydi)."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter

from database import settings
from database.db import db
from utils.time import now_db, to_db, utcnow

log = logging.getLogger(__name__)

_task: asyncio.Task | None = None


def minutes() -> int:
    """Kino chatda turish muddati (daqiqa). 0 = o'chirilmaydi. Telegram 48 soatdan keyin o'chirishga ruxsat bermaydi."""
    return max(0, min(settings.get_int("auto_delete_minutes", 2870), 2870))


def human() -> str:
    m = minutes()
    days, rest = divmod(m, 1440)
    hrs, mins = divmod(rest, 60)
    parts = []
    if days:
        parts.append(f"{days} kun")
    if hrs:
        parts.append(f"{hrs} soat")
    if mins:
        parts.append(f"{mins} daqiqa")
    return " ".join(parts) or "0 daqiqa"


async def schedule(chat_id: int, message_id: int) -> None:
    m = minutes()
    if m <= 0 or not message_id:
        return
    await db.execute(
        "INSERT INTO autodelete (chat_id, message_id, delete_at) VALUES (?, ?, ?)",
        (chat_id, message_id, to_db(utcnow() + timedelta(minutes=m))),
    )


async def _loop(bot: Bot) -> None:
    while True:
        try:
            rows = await db.fetchall(
                "SELECT id, chat_id, message_id FROM autodelete WHERE delete_at <= ? ORDER BY id LIMIT 100",
                (now_db(),),
            )
            for row in rows:
                try:
                    await bot.delete_message(row["chat_id"], row["message_id"])
                except TelegramRetryAfter as exc:
                    await asyncio.sleep(exc.retry_after + 1)
                    break  # qatorni o'chirmaymiz, keyingi aylanishda qayta uriniladi
                except TelegramAPIError as exc:
                    log.debug("Avto-o'chirish bajarilmadi (%s/%s): %s", row["chat_id"], row["message_id"], exc)
                await db.execute("DELETE FROM autodelete WHERE id = ?", (row["id"],))
                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("Avto-o'chirish tsikli xatosi")
        await asyncio.sleep(60)


def start(bot: Bot) -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(bot))
