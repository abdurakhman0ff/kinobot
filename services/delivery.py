"""Kino/serial ochish va video yuborish (`deliver`)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardMarkup

import config
import texts as t
from database import movies, settings, users
from keyboards.user import (
    back_kb,
    episode_kb,
    film_card_kb,
    locked_kb,
    not_found_kb,
    random_kb,
    serial_card_kb,
    vip_offer_kb,
)
from services import limits, notify, subscription
from services.cards import card_caption, episode_caption, locked_caption, poster_of, remember_poster
from utils.text import chat_ref, esc
from utils.time import fmt_duration
from utils.ui import render, render_photo

log = logging.getLogger(__name__)

Row = dict[str, Any]

_locks: dict[int, asyncio.Lock] = {}


def _lock_for(user_id: int) -> asyncio.Lock:
    if len(_locks) > 5000:
        for uid in [u for u, lock in _locks.items() if not lock.locked()]:
            _locks.pop(uid, None)
    return _locks.setdefault(user_id, asyncio.Lock())


async def bot_username(bot: Bot) -> str:
    me = await bot.me()
    return me.username or ""


# ---------- kartochka klaviaturalari ----------

async def film_kb(bot: Bot, user_id: int, movie: Row) -> InlineKeyboardMarkup:
    return film_card_kb(
        movie,
        await bot_username(bot),
        await movies.is_saved(user_id, movie["id"]),
        await movies.comment_count(movie["id"]),
    )


async def continue_target(user_id: int, movie_id: int) -> tuple[int, int, int] | None:
    """Oxirgi ko'rilgan qismdan keyingisi (bo'lmasa o'sha qism)."""
    prog = await movies.progress(user_id, movie_id)
    if not prog:
        return None
    ep = await movies.episode_by_number(movie_id, prog["season"], prog["episode"])
    if not ep:
        return None
    target = await movies.neighbor(ep, 1) or ep
    return target["id"], target["season"], target["number"]


async def serial_kb(bot: Bot, user_id: int, movie: Row) -> InlineKeyboardMarkup:
    return serial_card_kb(
        movie,
        await bot_username(bot),
        await movies.seasons(movie["id"]),
        await movies.is_saved(user_id, movie["id"]),
        await continue_target(user_id, movie["id"]),
    )


async def serial_caption(movie: Row) -> str:
    seasons = await movies.seasons(movie["id"])
    count = await movies.episode_count(movie["id"])
    extra = t.SERIES_INFO.format(seasons=len(seasons), episodes=count) if count else t.NO_EPISODES
    return card_caption(movie, extra)


async def episode_nav_kb(movie_id: int, ep: Row) -> InlineKeyboardMarkup:
    prev = await movies.neighbor(ep, -1)
    nxt = await movies.neighbor(ep, 1)
    return episode_kb(movie_id, ep, prev["id"] if prev else None, nxt["id"] if nxt else None)


# ---------- rasmli kartochkalar ----------

async def show_card(bot: Bot, chat_id: int, message: object, movie: Row, caption: str,
                    kb: InlineKeyboardMarkup) -> None:
    """Poster bilan kartochka; poster yuklanmasa matn ko'rinishida."""
    photo = poster_of(movie)
    if photo:
        try:
            sent = await render_photo(bot, chat_id, message, photo, caption, kb)
            await remember_poster(movie, sent)
            return
        except TelegramBadRequest as exc:
            log.warning("Poster yuborilmadi (kod %s): %s", movie["code"], exc)
            if movie.get("poster_file_id"):
                await movies.update(movie["id"], poster_file_id=None)
    await render(bot, chat_id, message, caption, kb)


async def send_locked_card(bot: Bot, chat_id: int, movie: Row, message: object = None) -> None:
    await show_card(bot, chat_id, message, movie, locked_caption(movie), locked_kb())


async def send_serial_card(bot: Bot, user: Row, chat_id: int, movie: Row, message: object = None) -> None:
    if movie["is_vip"] and not users.is_privileged(user):
        await send_locked_card(bot, chat_id, movie, message)
        return
    await show_card(bot, chat_id, message, movie, await serial_caption(movie),
                    await serial_kb(bot, user["id"], movie))


async def show_random(bot: Bot, user: Row, chat_id: int, message: object = None, exclude: int = 0,
                      checked: bool = False) -> None:
    if not checked and not await subscription.ensure(bot, user, chat_id, {"a": "random"}):
        return
    movie = await movies.random_one(exclude)
    if not movie:
        await render(bot, chat_id, message, t.EMPTY_CATALOG, back_kb())
        return
    await show_card(bot, chat_id, message, movie, card_caption(movie), random_kb(movie["id"]))


# ---------- ochish ----------

async def open_by_code(bot: Bot, user: Row, chat_id: int, code: int, checked: bool = False) -> None:
    if not checked and not await subscription.ensure(bot, user, chat_id, {"a": "code", "v": code}):
        return
    movie = await movies.by_code(code)
    if not movie:
        await bot.send_message(chat_id, t.CODE_NOT_FOUND.format(code=code), reply_markup=not_found_kb(prefill=False))
        return
    await open_movie(bot, user, chat_id, movie, checked=True)


async def open_movie(bot: Bot, user: Row, chat_id: int, movie: Row, checked: bool = False) -> None:
    if not checked and not await subscription.ensure(bot, user, chat_id, {"a": "open", "id": movie["id"]}):
        return
    if movie["type"] == "serial":
        await send_serial_card(bot, user, chat_id, movie)
    else:
        await deliver(bot, user, chat_id, movie)


async def open_episode(bot: Bot, user: Row, chat_id: int, episode_id: int, checked: bool = False, old_message_id: int | None = None) -> bool:
    ep = await movies.episode(episode_id)
    movie = await movies.get(ep["movie_id"]) if ep else None
    if not ep or not movie:
        await bot.send_message(chat_id, t.EPISODE_NOT_FOUND)
        return False
    if not checked and not await subscription.ensure(bot, user, chat_id, {"a": "ep", "id": episode_id}):
        return False
    return await deliver(bot, user, chat_id, movie, ep, old_message_id=old_message_id)


# ---------- yuborish ----------

async def _copy(bot: Bot, chat_id: int, from_chat: int | str, message_id: int, caption: str,
                kb: InlineKeyboardMarkup, protect: bool) -> bool:
    for attempt in range(2):
        try:
            await bot.copy_message(chat_id, from_chat, message_id, caption=caption,
                                   reply_markup=kb, protect_content=protect)
            return True
        except TelegramRetryAfter as exc:
            if attempt:
                return False
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            raise
        except TelegramAPIError as exc:
            log.warning("copy_message %s/%s xato: %s", from_chat, message_id, exc)
            return False
    return False


async def send_video(bot: Bot, chat_id: int, src: Row, caption: str, kb: InlineKeyboardMarkup,
                     protect: bool) -> bool:
    """Saqlash kanali -> zaxira kanal -> eski file_id tartibida urinadi."""
    sources = [
        (config.STORAGE_CHANNEL_ID, src.get("storage_message_id")),
        (chat_ref(settings.get("backup_channel_id")), src.get("backup_message_id")),
    ]
    for from_chat, message_id in sources:
        if from_chat and message_id and await _copy(bot, chat_id, from_chat, message_id, caption, kb, protect):
            return True
    file_id = src.get("file_id")
    if file_id:
        for sender in (bot.send_video, bot.send_document):
            try:
                await sender(chat_id, file_id, caption=caption, reply_markup=kb, protect_content=protect)
                return True
            except TelegramForbiddenError:
                raise
            except TelegramAPIError as exc:
                log.debug("file_id bilan yuborilmadi: %s", exc)
    return False


async def deliver(bot: Bot, user: Row, chat_id: int, movie: Row, ep: Row | None = None, old_message_id: int | None = None) -> bool:
    """Obuna tekshiruvidan keyin chaqiriladi: VIP qulf -> limit -> yuborish -> hisob."""
    privileged = users.is_privileged(user)
    if movie["is_vip"] and not privileged:
        await send_locked_card(bot, chat_id, movie)
        return False

    kind = "series" if ep else "movie"
    item_key = f"e{ep['id']}" if ep else f"m{movie['id']}"
    async with _lock_for(user["id"]):
        if not privileged:
            verdict = await limits.check(user["id"], kind, item_key)
            if not verdict.allowed:
                await bot.send_message(chat_id, t.LIMIT_REACHED.format(left=fmt_duration(verdict.seconds_left)),
                                       reply_markup=vip_offer_kb())
                await users.add_event(user["id"], "limit_hit", {"kind": kind})
                return False

        if ep:
            caption, kb, src = episode_caption(movie, ep), await episode_nav_kb(movie["id"], ep), ep
        else:
            caption, kb, src = card_caption(movie), await film_kb(bot, user["id"], movie), movie

        # 🗑 Agar video xabari ID si bo'lsa (va menyu xabari bo'lmasa), yangisini yuborishdan oldin o'chiramiz
        if old_message_id:
            try:
                await bot.delete_message(chat_id, old_message_id)
            except Exception:
                pass

        # 🔒 HAMMA filmlar va seriallar uchun protect=True qilindi
        if not await send_video(bot, chat_id, src, caption, kb, protect=True):
            await bot.send_message(chat_id, t.VIDEO_UNAVAILABLE)
            where = t.ADMIN_EP_SUFFIX.format(season=ep["season"], number=ep["number"]) if ep else ""
            await notify.owner(
                bot,
                t.ADMIN_VIDEO_MISSING.format(code=movie["code"], title=esc(movie["title"]), where=where),
                key=f"missing:{movie['id']}:{ep['id'] if ep else 0}",
                every=600,
            )
            return False

        await movies.record_view(user["id"], movie["id"], ep["id"] if ep else None)
        if ep:
            await movies.set_progress(user["id"], movie["id"], ep["season"], ep["number"])
        if not privileged:
            await limits.consume(user["id"], kind, item_key)
    return True
