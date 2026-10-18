"""Foydalanuvchiga kinolarni va ularning qismlarini yuborish handlerlari."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import movies
from keyboards.callbacks import Card
from keyboards.user import film_card_kb
from services.cards import card_caption
from utils.text import parse_int
from utils.ui import answer

router = Router()
log = logging.getLogger(__name__)


async def restore_kb(bot: Bot, user_id: int, movie: dict[str, Any], k: str, episode_id: int = 0) -> InlineKeyboardMarkup | None:
    """Kartochka klaviaturasini tiklash."""
    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(user_id, movie["id"])
    parts = await movies.movie_parts(movie["id"])
    return film_card_kb(movie, bot_info.username, is_saved, parts=parts)


async def send_movie_card(bot: Bot, chat_id: int, movie: dict[str, Any], user_id: int) -> None:
    """Kino kartochkasini barcha qismlari tugmalari bilan birga yuborish."""
    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(user_id, movie["id"])
    
    parts = await movies.movie_parts(movie["id"])
    reply_markup = film_card_kb(movie, bot_info.username, is_saved, parts=parts)
    caption = card_caption(movie)
    photo = movie.get("poster_file_id")

    # Agar asosiy kinoda video fayl bo'lsa yoki 1-qism mavjud bo'lsa
    file_id = movie.get("file_id")
    if parts:
        file_id = parts[0].get("file_id") or file_id

    if file_id:
        try:
            await bot.send_video(chat_id, file_id, caption=caption, reply_markup=reply_markup)
            await movies.record_view(user_id, movie["id"], None)
            return
        except TelegramBadRequest as exc:
            log.warning("Video yuborishda xatolik: %s", exc)

    if photo:
        try:
            await bot.send_photo(chat_id, photo, caption=caption, reply_markup=reply_markup)
            await movies.record_view(user_id, movie["id"], None)
            return
        except TelegramBadRequest as exc:
            log.warning("Poster yuborishda xatolik: %s", exc)

    await bot.send_message(chat_id, caption, reply_markup=reply_markup)
    await movies.record_view(user_id, movie["id"], None)


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
async def open_movie_part(callback: CallbackQuery, callback_data: Card, bot: Bot, db_user: Any = None) -> None:
    """Foydalanuvchi qism tugmasini (1-qism, 2-qism...) bosganda ishlaydi."""
    movie = await movies.get(callback_data.m)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return

    uid = callback.from_user.id
    old_msg_id = callback.message.message_id if callback.message else None
    
    # Eski xabarni o'chirib, tanlangan qismni yuborish
    if old_msg_id:
        try:
            await bot.delete_message(uid, old_msg_id)
        except TelegramBadRequest:
            pass

    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(uid, movie["id"])
    parts = await movies.movie_parts(movie["id"])
    
    # Hozir bosilgan qismni qizil nuqta bilan belgilab klaviatura yasash
    reply_markup = film_card_kb(movie, bot_info.username, is_saved, parts=parts, current_part_id=callback_data.v)
    caption = card_caption(movie)

    # Tanlangan qismning fayl ID sini olish
    part = await movies.movie_part_by_id(callback_data.v)
    file_id = part.get("file_id") if part else movie.get("file_id")

    if file_id:
        try:
            await bot.send_video(uid, file_id, caption=caption, reply_markup=reply_markup)
            await movies.record_view(uid, movie["id"], None)
            await answer(callback)
            return
        except TelegramBadRequest as exc:
            log.warning("Qism videosini yuborishda xatolik: %s", exc)

    photo = movie.get("poster_file_id")
    if photo:
        await bot.send_photo(uid, photo, caption=caption, reply_markup=reply_markup)
    else:
        await bot.send_message(uid, caption, reply_markup=reply_markup)
        
    await movies.record_view(uid, movie["id"], None)
    await answer(callback)
