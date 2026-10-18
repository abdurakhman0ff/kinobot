"""Kinolarni foydalanuvchiga yuborish, qidirish va qismlarni ochish xizmati."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup

import texts as t
from database import movies
from keyboards.user import film_card_kb
from services.cards import card_caption

log = logging.getLogger(__name__)
Row = dict[str, Any]


async def film_kb(bot: Bot, user_id: int, movie: Row) -> InlineKeyboardMarkup:
    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(user_id, movie["id"])
    parts = await movies.movie_parts(movie["id"])
    return film_card_kb(movie, bot_info.username, is_saved, parts=parts)


async def send_movie_card(bot: Bot, chat_id: int, movie: Row, user_id: int) -> None:
    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(user_id, movie["id"])
    
    parts = await movies.movie_parts(movie["id"])
    reply_markup = film_card_kb(movie, bot_info.username, is_saved, parts=parts)
    caption = card_caption(movie)
    photo = movie.get("poster_file_id")

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


async def open_movie(bot: Bot, db_user: Row, user_id: int, movie: Row) -> None:
    await send_movie_card(bot, user_id, movie, user_id)


async def open_episode(bot: Bot, db_user: Row, user_id: int, part_id: int, old_message_id: int | None = None) -> None:
    part = await movies.movie_part_by_id(part_id)
    if not part:
        return

    movie = await movies.get(part["movie_id"])
    if not movie:
        return

    if old_message_id:
        try:
            await bot.delete_message(user_id, old_message_id)
        except TelegramBadRequest:
            pass

    bot_info = await bot.get_me()
    is_saved = await movies.is_saved(user_id, movie["id"])
    parts = await movies.movie_parts(movie["id"])
    
    reply_markup = film_card_kb(movie, bot_info.username, is_saved, parts=parts)
    caption = card_caption(movie)

    file_id = part.get("file_id") or movie.get("file_id")
    if file_id:
        try:
            await bot.send_video(user_id, file_id, caption=caption, reply_markup=reply_markup)
            await movies.record_view(user_id, movie["id"], None)
            return
        except TelegramBadRequest as exc:
            log.warning("Qism videosini yuborishda xatolik: %s", exc)

    await bot.send_message(user_id, caption, reply_markup=reply_markup)
    await movies.record_view(user_id, movie["id"], None)
