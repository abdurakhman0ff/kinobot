"""Xabarlarni xavfsiz tahrirlash/o'chirish yordamchilari."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

log = logging.getLogger(__name__)

# Bu xatolar foydalanuvchi uchun zararsiz: jim o'tkazib yuboriladi
SILENT_ERRORS = (
    "message is not modified",
    "message to edit not found",
    "message to delete not found",
    "message can't be deleted",
    "message can't be edited",
    "query is too old",
    "query id is invalid",
)


def is_silent(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(s in text for s in SILENT_ERRORS)


async def safe_delete(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramAPIError:
        pass


async def answer(callback: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    try:
        await callback.answer(text, show_alert=alert)
    except TelegramAPIError:
        pass


def _is_text(message: object) -> bool:
    return isinstance(message, Message) and message.text is not None


async def render(
    bot: Bot,
    chat_id: int,
    message: object,
    text: str,
    kb: InlineKeyboardMarkup | None = None,
) -> int:
    """Matnli xabarni tahrirlaydi; imkon bo'lmasa (media xabar) o'chirib, yangisini yuboradi."""
    if _is_text(message):
        assert isinstance(message, Message)
        try:
            await message.edit_text(text, reply_markup=kb)
            return message.message_id
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return message.message_id
            log.debug("edit_text bo'lmadi: %s", exc)
    if isinstance(message, Message):
        await safe_delete(bot, chat_id, message.message_id)
    sent = await bot.send_message(chat_id, text, reply_markup=kb)
    return sent.message_id


async def render_photo(
    bot: Bot,
    chat_id: int,
    message: object,
    photo: str | None,
    caption: str,
    kb: InlineKeyboardMarkup | None = None,
) -> Message | None:
    """Rasmli kartochka: rasm bo'lsa edit_media, aks holda matn sifatida."""
    if not photo:
        mid = await render(bot, chat_id, message, caption, kb)
        return message if isinstance(message, Message) and message.message_id == mid else None
    if isinstance(message, Message) and message.photo:
        try:
            result = await message.edit_media(InputMediaPhoto(media=photo, caption=caption), reply_markup=kb)
            return result if isinstance(result, Message) else message
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return message
            log.debug("edit_media bo'lmadi: %s", exc)
    if isinstance(message, Message):
        await safe_delete(bot, chat_id, message.message_id)
    return await bot.send_photo(chat_id, photo, caption=caption, reply_markup=kb)


async def edit_kb(message: object, kb: InlineKeyboardMarkup | None) -> None:
    if not isinstance(message, Message):
        return
    try:
        await message.edit_reply_markup(reply_markup=kb)
    except TelegramBadRequest as exc:
        if not is_silent(exc):
            raise


async def edit_caption(message: object, caption: str, kb: InlineKeyboardMarkup | None) -> bool:
    """Media xabar sarlavhasini (yoki matnni) tahrirlaydi."""
    if not isinstance(message, Message):
        return False
    try:
        if message.text is not None:
            await message.edit_text(caption, reply_markup=kb)
        else:
            await message.edit_caption(caption=caption, reply_markup=kb)
        return True
    except TelegramBadRequest as exc:
        if "not modified" in str(exc).lower():
            return True
        if not is_silent(exc):
            log.debug("edit_caption bo'lmadi: %s", exc)
        return False
