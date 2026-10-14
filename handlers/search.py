"""Kod va nom bo'yicha qidiruv, IMDb qidiruv."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from keyboards.callbacks import Nav, Pg
from keyboards.user import back_kb
from services import actions, delivery, subscription
from utils.ui import answer, render

router = Router()

Row = dict[str, Any]


class ImdbForm(StatesGroup):
    query = State()


@router.callback_query(Nav.filter(F.to == "imdb"))
async def imdb_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    # ⚡ Darhol javob berish
    await answer(callback)
    
    await state.set_state(ImdbForm.query)
    await render(bot, callback.from_user.id, callback.message, t.IMDB_PROMPT, back_kb())


@router.message(ImdbForm.query, F.text)
async def imdb_query(message: Message, state: FSMContext, bot: Bot, db_user: Row) -> None:
    await state.clear()
    text = message.text.strip()[:200]
    if await subscription.ensure(bot, db_user, message.chat.id, {"a": "imdb", "q": text}):
        await actions.imdb_lookup(bot, db_user, message.chat.id, text)


@router.callback_query(Pg.filter(F.k == "s"))
async def search_page(callback: CallbackQuery, callback_data: Pg, bot: Bot, db_user: Row) -> None:
    # ⚡ Darhol javob berish (tugma qotib qolmasligi uchun)
    await answer(callback)
    
    query = actions.last_query.get(db_user["id"])
    if not query:
        await answer(callback, t.SEARCH_EXPIRED, alert=True)
        return
    await actions.show_search(bot, db_user, callback.from_user.id, query, callback_data.p, callback.message)


@router.message(StateFilter(None), F.text, ~F.text.startswith("/"))
async def text_query(message: Message, bot: Bot, db_user: Row) -> None:
    text = message.text.strip()
    if not text:
        return
    if text.isdigit():
        await delivery.open_by_code(bot, db_user, message.chat.id, int(text))
        return
    text = text[:100]
    if await subscription.ensure(bot, db_user, message.chat.id, {"a": "search", "q": text}):
        await actions.show_search(bot, db_user, message.chat.id, text)
