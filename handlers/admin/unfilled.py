"""🧩 To'ldirilmaganlar: turi yoki tili bo'sh kinolarni birin-ketin to'ldirish."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

import texts as t
from database import movies
from handlers.admin.common import TYPES, RoleFilter, back_panel_kb, languages_kb
from keyboards.callbacks import Adm
from keyboards.common import btn
from services import search
from services.cards import type_label
from utils.text import esc, split_csv
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("admin"))
router.callback_query.filter(RoleFilter("admin"))


async def show_next(bot: Bot, chat_id: int, after_id: int, message: object = None) -> None:
    movie = await movies.unfilled_next(after_id)
    if not movie:
        await render(bot, chat_id, message, t.UNFILLED_DONE, back_panel_kb())
        return
    await show_movie(bot, chat_id, movie["id"], message)


async def show_movie(bot: Bot, chat_id: int, movie_id: int, message: object = None) -> None:
    movie = await movies.get(movie_id)
    if not movie:
        await show_next(bot, chat_id, movie_id, message)
        return
    left = await movies.unfilled_count()
    selected = split_csv(movie.get("languages"))
    markup = languages_kb(selected, "ul", "un", movie["id"], extra=await movies.languages())
    markup.inline_keyboard.insert(0, [
        btn(("✅ " if movie["type"] == x else "") + type_label(x), Adm(a="ut", id=movie["id"], v=x)) for x in TYPES
    ])
    markup.inline_keyboard.append([btn(t.BTN_ADMIN_PANEL, Adm(a="p"))])
    text = t.UNFILLED_ITEM.format(left=left, title=esc(movie["title"]), code=movie["code"],
                                  year=movie.get("year") or "—", type=type_label(movie["type"]),
                                  langs=esc(movie.get("languages") or "—"))
    await render(bot, chat_id, message, text, markup)


@router.callback_query(Adm.filter(F.a == "unf"))
async def unfilled_start(callback: CallbackQuery, bot: Bot) -> None:
    await show_next(bot, callback.from_user.id, 0, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "ut"))
async def set_type(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    if callback_data.v in TYPES:
        await movies.update(callback_data.id, type=callback_data.v)
        search.invalidate()
    await show_movie(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "ul"))
async def toggle_lang(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    if callback_data.v == "+":
        # "Boshqa" til qo'lda faqat tahrirlash bo'limida kiritiladi
        await answer(callback, t.UNFILLED_OTHER_LANG, alert=True)
        return
    movie = await movies.get(callback_data.id)
    if movie:
        selected = split_csv(movie.get("languages"))
        if callback_data.v in selected:
            selected.remove(callback_data.v)
        else:
            selected.append(callback_data.v)
        await movies.update(movie["id"], languages=", ".join(selected) or None)
    await show_movie(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "un"))
async def next_movie(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await show_next(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)
