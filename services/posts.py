"""Ochiq kanal posti va yangi kino bildirishnomasi."""
from __future__ import annotations

import logging
import re
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import texts as t
from database import settings, users
from keyboards.user import watch_url_kb
from services import broadcast, notify
from services.cards import poster_of, remember_poster, short_post
from services.delivery import bot_username
from utils.text import chat_ref, esc, truncate
from database import movies as _movies
from services.cards import fmt_rating, fmt_runtime

log = logging.getLogger(__name__)

Row = dict[str, Any]


def _e(emoji_id: str, fallback: str) -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def _visible(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text)


def channel_text(movie: Row, link: str) -> str:
    """Kanal posti: ikkita yopiladigan blok + yuklab olish havolasi."""
    title = esc(movie.get("title") or "—")
    original = (movie.get("original_title") or "").strip()
    info = [f"{_e('5447242579827523388', '✔️')} Nomi: {title}"]
    if original and original.lower() != (movie.get("title") or "").strip().lower():
        info.append(f"{_e('5445163158526261598', '☑️')} Original nomi: {esc(original)}")
    pairs = [
        (_e("5447421246172069841", "📄") + " Yil", movie.get("year")),
        (_e("5445326466067754897", "🌐") + " Davlat", movie.get("countries")),
        (_e("5445255929819854310", "🔎") + " Janr", movie.get("genres")),
        (_e("5447602197439218445", "🌐") + " Til", movie.get("languages")),
        (_e("5447282724886839705", "📂") + " Sifat", movie.get("quality")),
        (_e("5445350406215465190", "⏰") + " Davomiylik", fmt_runtime(movie.get("runtime_min")) if movie.get("runtime_min") else None),
    ]
    missing = "<i>kiritilmagan</i>"
    info += [f"{label}: {esc(value) if value else missing}" for label, value in pairs]

    def build(limit: int) -> str:
        parts = ["<blockquote expandable>" + "\n".join(info) + "</blockquote>"]
        desc = (movie.get("description") or "").strip()
        body = esc(truncate(desc, limit)) if desc else missing
        parts.append("<blockquote expandable>" + _e("5247029067256987229", "ℹ️") + " Film haqida:\n" + body + "</blockquote>")
        parts.append(f'{_e("5445023138297447592", "🔎")} Kod: <code>{movie["code"]}</code>\n'
                     f'<a href="{link}">{_e("5444961234933806330", "⬇️")} Filmni yuklab olish {_e("5890925363067886150", "✨")}</a>')
        return "\n".join(parts)

    for limit in (500, 350, 220, 120):
        text = build(limit)
        if len(_visible(text)) <= 1000:
            return text
    return text


async def public_post(bot: Bot, movie: Row) -> bool:
    channel = chat_ref(settings.get("public_channel_id"))
    if not channel:
        await notify.owner(bot, t.ADMIN_NO_PUBLIC_CHANNEL)
        return False
    uname = await bot_username(bot)
    caption = channel_text(movie, f"https://t.me/{uname}?start=kino_{movie['code']}")
    markup = None
    photo = poster_of(movie)
    try:
        if photo:
            msg = await bot.send_photo(channel, photo, caption=caption, reply_markup=markup,
                                       show_caption_above_media=True)
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
