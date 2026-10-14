"""Kartochka tugmalari: ochish, serial navigatsiyasi, aktyorlar, treyler, o'xshashlar, saqlash, shikoyat."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

import texts as t
from database import misc, movies
from keyboards.callbacks import Card, Op, Rnd
from keyboards.user import actors_kb, episodes_kb, movies_back_kb, report_kb
from services import delivery, notify
from services.tmdb import kind_of, tmdb
from utils.text import esc
from utils.ui import answer, edit_kb

router = Router()

Row = dict[str, Any]


async def restore_kb(bot: Bot, user_id: int, movie: Row, k: str, episode_id: int = 0) -> InlineKeyboardMarkup | None:
    if k == "s":
        return await delivery.serial_kb(bot, user_id, movie)
    if k == "e":
        ep = await movies.episode(episode_id)
        return await delivery.episode_nav_kb(movie["id"], ep) if ep else None
    return await delivery.film_kb(bot, user_id, movie)


@router.callback_query(Op.filter())
async def open_from_list(callback: CallbackQuery, callback_data: Op, bot: Bot, db_user: Row) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    
    movie = await movies.get(callback_data.id)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    await delivery.open_movie(bot, db_user, callback.from_user.id, movie)


@router.callback_query(Rnd.filter(F.a == "n"))
async def random_next(callback: CallbackQuery, callback_data: Rnd, bot: Bot, db_user: Row) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    await delivery.show_random(bot, db_user, callback.from_user.id, callback.message, exclude=callback_data.id)


@router.callback_query(Rnd.filter(F.a == "w"))
async def random_watch(callback: CallbackQuery, callback_data: Rnd, bot: Bot, db_user: Row) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    
    movie = await movies.get(callback_data.id)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    await delivery.open_movie(bot, db_user, callback.from_user.id, movie)


@router.callback_query(Card.filter(F.a.in_({"back", "tr", "act", "ac", "sim", "sv", "rep", "rp", "ss", "se"})))
async def card_action(callback: CallbackQuery, callback_data: Card, bot: Bot, db_user: Row) -> None:
    # ⚡ DARHOL JAVOB BERISH (Tugma bosilishi bilanoq Telegram qotishi yo'qoladi)
    await answer(callback)
    
    data = callback_data
    movie = await movies.get(data.m)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    uid = callback.from_user.id

    if data.a == "back":
        await edit_kb(callback.message, await restore_kb(bot, uid, movie, data.k, data.e))

    elif data.a == "se":
        # 💡 Faqat video xabarlardagi "Keyingi/Oldingi qism" tugmalari bosilganda oldingi videoni o'chiramiz.
        # Fasllar menyusidan qism tanlanganda esa menyu o'chib ketmaydi.
        is_video_msg = bool(callback.message and (callback.message.video or callback.message.document))
        old_msg_id = callback.message.message_id if is_video_msg else None
        await delivery.open_episode(bot, db_user, uid, data.v, old_message_id=old_msg_id)

    elif data.a == "ss":
        eps = await movies.episodes(movie["id"], data.v)
        if not eps:
            await answer(callback, t.NO_EPISODES, alert=True)
            return
        await edit_kb(callback.message, episodes_kb(movie["id"], data.v, eps, data.p, data.k, data.e))

    elif data.a == "tr":
        if movie.get("trailer_url") is None and movie.get("tmdb_id"):
            url = await tmdb.trailer(kind_of(movie["type"]), movie["tmdb_id"])
            movie["trailer_url"] = url or ""
            await movies.update(movie["id"], trailer_url=movie["trailer_url"])
        if movie.get("trailer_url"):
            await edit_kb(callback.message, await restore_kb(bot, uid, movie, data.k, data.e))
            await answer(callback, t.TRAILER_READY)
        else:
            await answer(callback, t.TRAILER_NOT_FOUND, alert=True)

    elif data.a == "act":
        cast = await tmdb.cast(kind_of(movie["type"]), movie["tmdb_id"]) if movie.get("tmdb_id") else []
        if not cast:
            await answer(callback, t.ACTORS_NOT_FOUND, alert=True)
            return
        await edit_kb(callback.message, actors_kb(movie["id"], cast, data.k))

    elif data.a == "ac":
        movie_ids, tv_ids = await tmdb.person_credits(data.v)
        found = await movies.by_tmdb(movie_ids, series=False) + await movies.by_tmdb(tv_ids, series=True)
        found = [m for m in found if m["id"] != movie["id"]][:10]
        if not found:
            await answer(callback, t.CATALOG_NO_OTHER, alert=True)
            return
        await edit_kb(callback.message, movies_back_kb(found, Card(a="act", m=movie["id"], k=data.k)))

    elif data.a == "sim":
        found = await movies.similar(movie)
        if not found:
            await answer(callback, t.NO_SIMILAR, alert=True)
            return
        await edit_kb(callback.message, movies_back_kb(found, Card(a="back", m=movie["id"], k=data.k)))

    elif data.a == "sv":
        saved = await movies.toggle_saved(uid, movie["id"])
        await edit_kb(callback.message, await restore_kb(bot, uid, movie, data.k, data.e))
        await answer(callback, t.SAVED if saved else t.UNSAVED)

    elif data.a == "rep":
        await edit_kb(callback.message, report_kb(movie["id"], data.e, data.k))

    elif data.a == "rp":
        if await misc.reported_recently(uid, movie["id"]):
            await answer(callback, t.REPORT_LIMIT, alert=True)
        else:
            reason = t.REPORT_REASONS[data.v] if 0 <= data.v < len(t.REPORT_REASONS) else t.REPORT_REASONS[-1]
            await misc.add_report(uid, movie["id"], data.e or None, reason)
            ep = await movies.episode(data.e) if data.e else None
            where = t.ADMIN_EP_SUFFIX.format(season=ep["season"], number=ep["number"]) if ep else ""
            await notify.staff(bot, t.ADMIN_NEW_REPORT.format(
                code=movie["code"], title=esc(movie["title"]), where=where, reason=esc(reason), user_id=uid,
            ))
            await answer(callback, t.REPORT_THANKS, alert=True)
        await edit_kb(callback.message, await restore_kb(bot, uid, movie, data.k, data.e))
