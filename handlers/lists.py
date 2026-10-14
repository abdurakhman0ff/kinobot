"""Top, Yangilari, Kinolar, Seriallar, Tasodifiy."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import movies
from keyboards.callbacks import Nav, Pg
from keyboards.common import btn, list_kb, pages_of
from services import delivery
from utils.ui import answer, render

router = Router()

Row = dict[str, Any]

TOP_PER_PAGE = 10
CATALOG_PER_PAGE = 8
NEW_COUNT = 10
PERIODS = {"w": t.PERIOD_WEEK, "m": t.PERIOD_MONTH, "a": t.PERIOD_ALL}


async def top_view(period: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    period = period if period in PERIODS else "a"
    total, _ = await movies.top(period, 0, 0)
    pages = pages_of(total, TOP_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    _, rows = await movies.top(period, page * TOP_PER_PAGE, TOP_PER_PAGE)
    period_row = [
        btn(("✅ " if key == period else "") + label, Pg(k="top", p=0, x=key)) for key, label in PERIODS.items()
    ]
    text = t.TOP_TITLE.format(period=PERIODS[period]) + ("" if rows else "\n\n" + t.EMPTY_LIST)
    return text, list_kb(rows, "top", page, pages, period, top_rows=[period_row])


async def new_view() -> tuple[str, InlineKeyboardMarkup]:
    rows = await movies.newest(NEW_COUNT)
    text = t.NEW_TITLE + ("" if rows else "\n\n" + t.EMPTY_LIST)
    return text, list_kb(rows, "new", 0, 1)


async def catalog_view(kind: str, page: int) -> tuple[str, InlineKeyboardMarkup]:
    total, _ = await movies.catalog(kind, 0, 0)
    pages = pages_of(total, CATALOG_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    _, rows = await movies.catalog(kind, page * CATALOG_PER_PAGE, CATALOG_PER_PAGE)
    title = t.SERIES_TITLE if kind == "series" else t.FILMS_TITLE
    text = title.format(total=total) + ("" if rows else "\n\n" + t.EMPTY_LIST)
    return text, list_kb(rows, kind, page, pages)


@router.callback_query(Nav.filter(F.to.in_({"top", "new", "films", "series"})))
async def nav_lists(callback: CallbackQuery, callback_data: Nav, bot: Bot) -> None:
    if callback_data.to == "top":
        text, kb = await top_view("a", 0)
    elif callback_data.to == "new":
        text, kb = await new_view()
    else:
        text, kb = await catalog_view(callback_data.to, 0)
    await render(bot, callback.from_user.id, callback.message, text, kb)
    await answer(callback)


@router.callback_query(Pg.filter(F.k.in_({"top", "films", "series"})))
async def page_lists(callback: CallbackQuery, callback_data: Pg, bot: Bot) -> None:
    if callback_data.k == "top":
        text, kb = await top_view(callback_data.x, callback_data.p)
    else:
        text, kb = await catalog_view(callback_data.k, callback_data.p)
    await render(bot, callback.from_user.id, callback.message, text, kb)
    await answer(callback)


@router.callback_query(Nav.filter(F.to == "random"))
async def nav_random(callback: CallbackQuery, bot: Bot, db_user: Row) -> None:
    await answer(callback)
    await delivery.show_random(bot, db_user, callback.from_user.id, callback.message)


@router.message(Command("top"))
async def cmd_top(message: Message, bot: Bot) -> None:
    text, kb = await top_view("a", 0)
    await render(bot, message.chat.id, None, text, kb)


@router.message(Command("new"))
async def cmd_new(message: Message, bot: Bot) -> None:
    text, kb = await new_view()
    await render(bot, message.chat.id, None, text, kb)
