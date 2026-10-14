"""Fon vazifalari (APScheduler, Tashkent vaqti)."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
import texts as t
from database import misc, movies, users
from database.db import db
from keyboards.user import renew_kb
from services import backup, posts
from utils.time import ago_db, now_db, to_db, utcnow

log = logging.getLogger(__name__)


async def publish_due(bot: Bot) -> None:
    for post in await misc.due_scheduled():
        movie = await movies.get(post["movie_id"])
        ok = bool(movie) and await posts.public_post(bot, movie)  # type: ignore[arg-type]
        await misc.set_scheduled_status(post["id"], "done" if ok else "failed")


async def _send(bot: Bot, user_id: int, text: str) -> None:
    try:
        await bot.send_message(user_id, text, reply_markup=renew_kb())
    except TelegramForbiddenError:
        await users.set_field(user_id, "is_blocked_bot", 1)
    except TelegramAPIError as exc:
        log.debug("VIP eslatmasi yuborilmadi %s: %s", user_id, exc)
    await asyncio.sleep(0.05)


async def vip_reminders(bot: Bot) -> None:
    now = now_db()
    soon = to_db(utcnow() + timedelta(days=3))
    rows = await db.fetchall(
        """SELECT id, vip_until FROM users WHERE vip_until > ? AND vip_until <= ?
           AND (vip_remind_for IS NULL OR vip_remind_for != vip_until) AND is_blocked_bot = 0""",
        (now, soon),
    )
    for r in rows:
        await _send(bot, r["id"], t.VIP_EXPIRES_SOON)
        await users.set_field(r["id"], "vip_remind_for", r["vip_until"])
    rows = await db.fetchall(
        """SELECT id, vip_until FROM users WHERE vip_until <= ? AND vip_until > ?
           AND (vip_expired_for IS NULL OR vip_expired_for != vip_until) AND is_blocked_bot = 0""",
        (now, ago_db(days=30)),
    )
    for r in rows:
        await _send(bot, r["id"], t.VIP_EXPIRED)
        await users.set_field(r["id"], "vip_expired_for", r["vip_until"])


async def daily_backup(bot: Bot) -> None:
    try:
        await backup.send_backup(bot, config.ADMIN_ID)
    except Exception:  # noqa: BLE001 - fon vazifasi yiqilmasin
        log.exception("Kunlik backup xatosi")


async def cleanup() -> None:
    removed = await misc.cleanup_pending()
    log.info("Eskirgan pending_actions o'chirildi: %s", removed)


def setup(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=config.TZ)
    common = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 3600}
    scheduler.add_job(publish_due, "interval", minutes=1, args=[bot], **common)
    scheduler.add_job(vip_reminders, "cron", hour=10, minute=0, args=[bot], **common)
    scheduler.add_job(daily_backup, "cron", hour=3, minute=0, args=[bot], **common)
    scheduler.add_job(cleanup, "cron", hour=4, minute=0, **common)
    return scheduler
