"""/start, pin qilingan xabar, asosiy menyu, botni bloklash holati."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, InlineKeyboardMarkup, Message

import texts as t
from database import users
from keyboards.callbacks import Nav
from keyboards.common import NOOP
from keyboards.user import main_menu, start_kb, subscribe_kb
from services import delivery, subscription
from utils.text import esc, parse_int
from utils.time import days_left
from utils.ui import answer, render, safe_delete

router = Router()

Row = dict[str, Any]


def menu_view(user: Row, role: str | None) -> tuple[str, InlineKeyboardMarkup]:
    until = users.vip_until(user)
    text = t.MENU_TEXT
    if not until and role is None:
        text += "\n\n" + t.MENU_VIP_HINT
    return text, main_menu(days_left(until) if until else None, role is not None)


async def ensure_pin(bot: Bot, user: Row, chat_id: int, first_name: str, is_new: bool) -> None:
    """Salomlashuv xabarini yangilaydi (pin QILMAYDI); eski pin bo'lsa olib tashlaydi."""
    greeting = (t.WELCOME_NEW if is_new else t.WELCOME_BACK).format(name=esc(first_name))
    text = f"{greeting}\n\n{t.START_HINT}"
    pinned = user.get("pinned_message_id")
    if pinned:
        try:
            await bot.unpin_chat_message(chat_id, message_id=pinned)
        except TelegramAPIError:
            pass
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=pinned, reply_markup=start_kb())
            return
        except TelegramBadRequest as exc:
            if "not modified" in str(exc).lower():
                return
        except TelegramAPIError:
            pass
    msg = await bot.send_message(chat_id, text, reply_markup=start_kb())
    await users.set_field(user["id"], "pinned_message_id", msg.message_id)


async def send_menu(bot: Bot, user: Row, role: str | None, chat_id: int) -> None:
    await safe_delete(bot, chat_id, user.get("menu_message_id"))
    text, kb = menu_view(user, role)
    msg = await bot.send_message(chat_id, text, reply_markup=kb)
    await users.set_field(user["id"], "menu_message_id", msg.message_id)


@router.message(CommandStart(), StateFilter("*"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext, bot: Bot,
                    db_user: Row, role: str | None, is_new_user: bool) -> None:
    await state.clear()
    chat_id = message.chat.id
    arg = (command.args or "").strip()
    await ensure_pin(bot, db_user, chat_id, message.from_user.first_name if message.from_user else "", is_new_user)

    if arg.startswith("kino_"):
        code = parse_int(arg[5:])
        if code is not None:
            await delivery.open_by_code(bot, db_user, chat_id, code)
            return
    if arg == "sub":
        items = [] if users.is_privileged(db_user) else await subscription.missing(bot, db_user["id"])
        if items:
            await message.answer(t.SUBSCRIBE, reply_markup=subscribe_kb(items))
        else:
            await message.answer(t.SUB_OK)
        return
    await send_menu(bot, db_user, role, chat_id)


@router.callback_query(Nav.filter(F.to == "menu"), StateFilter("*"))
async def nav_menu(callback: CallbackQuery, state: FSMContext, bot: Bot, db_user: Row, role: str | None) -> None:
    await state.clear()
    text, kb = menu_view(db_user, role)
    mid = await render(bot, callback.from_user.id, callback.message, text, kb)
    if mid != db_user.get("menu_message_id"):
        await users.set_field(db_user["id"], "menu_message_id", mid)
    await answer(callback)


@router.callback_query(F.data == NOOP)
async def noop(callback: CallbackQuery) -> None:
    await answer(callback)


@router.my_chat_member(F.chat.type == ChatType.PRIVATE)
async def on_my_chat_member(update: ChatMemberUpdated) -> None:
    blocked = update.new_chat_member.status in (ChatMemberStatus.KICKED, ChatMemberStatus.LEFT)
    await users.ensure_exists(update.from_user.id)
    await users.set_field(update.from_user.id, "is_blocked_bot", int(blocked))
