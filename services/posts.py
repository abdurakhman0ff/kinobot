"""Ochiq kanal posti va yangi kino bildirishnomasi."""
from __future__ import annotations

import logging
import re
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

import config
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


LOGO_EMOJI_ID = "5435848332238956244"  # kanal logosi (premium emoji ID)


def _tags(genres: object) -> str:
    out = []
    for g in str(genres or "").split(","):
        g = re.sub(r"[^\w]+", "", g.strip().replace(" ", "_").replace("'", "").replace("’", "").replace("ʻ", ""))
        if g:
            out.append("#" + g)
    return " ".join(out)


def channel_text(movie: Row, link: str) -> str:
    """Kanal posti: nom, ma'lumot, tomosha havolasi, tavsif bloki, obuna havolasi."""
    missing = "<i>kiritilmagan</i>"
    channel_url = getattr(config, "PUBLIC_CHANNEL_URL", None) or "https://t.me/abdurakhmanjaan"

    title = esc(movie.get("title") or "—")
    original = (movie.get("original_title") or "").strip()
    name = title
    if original and original.lower() != (movie.get("title") or "").strip().lower():
        name += f" ({esc(original)})"

    def val(v: object) -> str:
        return esc(v) if v else missing

    langs = str(movie.get("languages") or "").replace(", ", " | ").replace(",", " | ")
    head = [
        f'{_e("5375464961822695044", "🎬")} <b>{name}</b>',
        "— — — — — — — — — — —",
        f'{_e("5445326466067754897", "🌐")} <b>Davlat:</b> {val(movie.get("countries"))}',
        f'{_e("5447602197439218445", "🗣")} <b>Til:</b> {val(langs)} | '
        f'{_e("5447421246172069841", "📄")} <b>Yil:</b> {val(movie.get("year"))}',
        f'{_e("5447282724886839705", "📂")} <b>Sifat:</b> {val(movie.get("quality"))}',
        f'{_e("5445255929819854310", "🔎")} <b>Janr:</b> {_tags(movie.get("genres")) or missing}',
        f'{_e("5445023138297447592", "🔎")} <b>Film kodi:</b> <code>{movie["code"]}</code>',
        "",
        f'{_e("5444961234933806330", "⬇️")} <a href="{link}"><b>TOMOSHA QILISH</b></a> {_e("5890925363067886150", "✨")}',
        "",
    ]
    foot = [
        "",
        f'{_e(LOGO_EMOJI_ID, "🎬")} <a href="{channel_url}"><b>ABDURAKHMANJAAN</b></a> bilan bo\'ling! '
        f'{_e("5447242579827523388", "✔️")}',
    ]
    desc = (movie.get("description") or "").strip()

    def build(limit: int) -> str:
        body = esc(truncate(desc, limit)) if desc else missing
        return "\n".join(head + [f"<blockquote expandable>{body}</blockquote>"] + foot)

    text = build(500)
    for limit in (500, 350, 220, 120):
        text = build(limit)
        if len(_visible(text)) <= 1000:
            break
    return text


async def public_post(bot: Bot, movie: Row) -> bool:
    channel = config.ADMIN_ID  # post adminga yuboriladi, admin kanalga forward qiladi
    uname = await bot_username(bot)
    caption = channel_text(movie, f"https://t.me/{uname}?start=kino_{movie['code']}")
    markup = None
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
