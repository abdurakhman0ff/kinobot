"""Foydalanuvchiga kinolarni va ularning qismlarini yuborish handlerlari."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

import texts as t
from database import movies
from keyboards.callbacks import Card
from keyboards.user import film_card_kb
from services.cards import card_caption
from utils.text import parse_int
from utils.ui import answer

router = Router()
log = logging.getLogger(__name__)


async def send_movie_card(bot: Bot, chat_id: int, movie: dict[str, Any], user_id: int) -> None:
    """Kino kartochkasini barcha qismlari tugmalari bilan birga yuborish."""
    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(user_id, movie["id"])
    
    # 1. Kinoning barcha qismlarini bazadan olamiz (franshizalar uchun)
    parts = await movies.movie_parts(movie["id"])
    
    # 2. Qismlarni klaviaturaga uzatamiz
    reply_markup = film_card_kb(movie, bot_info.username, is_saved, parts=parts)
    caption = card_caption(movie)
    photo = movie.get("poster_file_id")

    if photo:
        try:
            await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup)
            return
        except TelegramBadRequest as exc:
            log.warning("Poster yuborishda xatolik: %s", exc)

    await bot.send_message(chat_id, caption, reply_markup=reply_markup)


@router.message(F.chat.type == ChatType.PRIVATE, F.text)
async def handle_movie_code(message: Message, bot: Bot) -> None:
    """Foydalanuvchi chatga kino kodini yozganda ishlaydi."""
    code = parse_int(message.text)
    if not code or code <= 0:
        return

    movie = await movies.by_code(code)
    if not movie:
        await message.answer(t.NOT_FOUND.format(code=code))
        return

    await send_movie_card(bot, message.chat.id, movie, message.from_user.id)


@router.callback_query(Card.filter(F.a == "open"))
async def open_movie_part(callback: CallbackQuery, callback_data: Card, bot: Bot) -> None:
    """Foydalanuvchi qism tugmasini (1-qism, 2-qism...) bosganda boshqa qismga o'tish."""
    movie = await movies.get(callback_data.m)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return

    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(callback.from_user.id, movie["id"])
    
    # Asosiy kinoning barcha qismlarini olish
    parts = await movies.movie_parts(movie["id"])
    reply_markup = film_card_kb(movie, bot_info.username, is_saved, parts=parts)
    caption = card_caption(movie)

    try:
        if callback.message.photo:
            await callback.message.edit_caption(caption=caption, reply_markup=reply_markup)
        else:
            await callback.message.edit_text(text=caption, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass

    await answer(callback)

# ---------- ro'yxatlar ----------

def _type_cond(kind: str) -> str:
    if kind == "series":
        return "m.type = 'serial'"
    elif kind == "cartoons":
        return "m.type = 'multfilm'"
    return "m.type = 'film'"


async def catalog(kind: str, offset: int, limit: int) -> tuple[int, list[Row]]:
    """Katalog bo'yicha kinolarni sahifalab olish."""
    cond = _type_cond(kind)
    total = int(await db.fetchval(f"SELECT COUNT(*) FROM movies m WHERE {cond}", default=0))
    rows = await db.fetchall(
        f"SELECT {SHORT} FROM movies m WHERE {cond} ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return total, rows
