"""Ochiq kanal posti va yangi kino bildirishnomasi."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import texts as t
from database import settings, users
from keyboards.user import watch_url_kb
from services import broadcast, notify
from services.cards import poster_of, remember_poster, short_post
from services.delivery import bot_username
from utils.text import chat_ref, esc

log = logging.getLogger(__name__)

Row = dict[str, Any]


async def public_post(bot: Bot, movie: Row) -> bool:
    channel = chat_ref(settings.get("public_channel_id"))
    if not channel:
        await notify.owner(bot, t.ADMIN_NO_PUBLIC_CHANNEL)
        return False
    caption = short_post(movie)
    markup = watch_url_kb(await bot_username(bot), movie["code"], t.BTN_WATCH_CHANNEL)
    photo = poster_of(movie)
    try:
        if photo:
            msg = await bot.send_photo(channel, photo, caption=caption, reply_markup=markup)
            await remember_poster(movie, msg)
        else:
            await bot.send_message(channel, caption, reply_markup=markup)
        return True
    except TelegramAPIError as exc:
        log.warning("Ochiq kanalga post chiqmadi: %s", exc)
        await notify.owner(bot, t.ADMIN_POST_FAILED.format(code=movie["code"], error=esc(str(exc)[:200])))
        return False


async def notify_new_movie(bot: Bot, movie: Row, report_chat: int) -> int:
    """`notify_new=1` foydalanuvchilarga tarqatadi. Navbatdagi o'rnini qaytaradi."""
    caption = t.NEW_MOVIE_NOTIFY + "\n\n" + short_post(movie)
    markup = watch_url_kb(await bot_username(bot), movie["code"])
    photo = poster_of(movie)
    if photo and not movie.get("poster_file_id"):
        # URL ni har safar yuklamaslik uchun avval file_id olamiz (admin ko'radi)
        try:
            msg = await bot.send_photo(report_chat, photo, caption=caption, reply_markup=markup)
            await remember_poster(movie, msg)
            photo = movie.get("poster_file_id") or photo
        except TelegramAPIError:
            photo = None

    async def send(user_id: int) -> None:
        if photo:
            await bot.send_photo(user_id, photo, caption=caption, reply_markup=markup)
        else:
            await bot.send_message(user_id, caption, reply_markup=markup)

    ids = await users.segment_ids("notify")
    job = broadcast.Job(title=t.JOB_NEW_MOVIE.format(title=movie["title"]), user_ids=ids, send=send,
                        report_chat=report_chat)
    return await broadcast.enqueue(bot, job)
