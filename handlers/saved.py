"""⭐ Saqlangan kinolar."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import movies
from keyboards.callbacks import Nav, Pg
from keyboards.common import list_kb, pages_of
from utils.ui import answer, render

router = Router()

PER_PAGE = 8


async def saved_view(user_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    total, _ = await movies.saved_page(user_id, 0, 0)
    pages = pages_of(total, PER_PAGE)
    page = min(max(page, 0), pages - 1)
    _, rows = await movies.saved_page(user_id, page * PER_PAGE, PER_PAGE)
    text = t.SAVED_TITLE.format(n=total) if rows else t.SAVED_EMPTY
    return text, list_kb(rows, "saved", page, pages)


@router.callback_query(Nav.filter(F.to == "saved"))
async def nav_saved(callback: CallbackQuery, bot: Bot) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    text, kb = await saved_view(callback.from_user.id, 0)
    await render(bot, callback.from_user.id, callback.message, text, kb)


@router.callback_query(Pg.filter(F.k == "saved"))
async def page_saved(callback: CallbackQuery, callback_data: Pg, bot: Bot) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    text, kb = await saved_view(callback.from_user.id, callback_data.p)
    await render(bot, callback.from_user.id, callback.message, text, kb)


@router.message(Command("saved"))
async def cmd_saved(message: Message, bot: Bot) -> None:
    text, kb = await saved_view(message.chat.id, 0)
    await render(bot, message.chat.id, None, text, kb)
