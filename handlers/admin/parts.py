"""🎞 Ko'p qismli film: qismlar ro'yxati, qo'shish, almashtirish, o'chirish.

1-qism = filmning asosiy fayli; 2, 3, ... qismlar `episodes` jadvalida season=0 bilan saqlanadi.
"""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import movies
from handlers.admin import episodes
from handlers.admin.common import RoleFilter, cancel_kb, store_media
from keyboards.callbacks import Adm
from keyboards.common import btn, chunk, kb
from utils.text import esc
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("moderator"))
router.callback_query.filter(RoleFilter("moderator"))

Row = dict[str, Any]


class PartReplace(StatesGroup):
    file = State()


async def parts_view(bot: Bot, chat_id: int, movie: Row, message: object = None) -> None:
    parts = await movies.parts(movie["id"])
    rows = chunk([btn(t.MP_N.format(n=p["number"]), Adm(a="mp_one", id=p["id"])) for p in parts], 3)
    rows.append([btn(t.MP_ADD, Adm(a="mp_add", id=movie["id"]))])
    rows.append([btn(t.BTN_BACK, Adm(a="em", id=movie["id"]))])
    await render(bot, chat_id, message, t.MP_TITLE.format(title=esc(movie["title"]), count=len(parts) + 1), kb(rows))


@router.callback_query(Adm.filter(F.a == "mp_list"), StateFilter("*"))
async def parts_list(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    movie = await movies.get(callback_data.id)
    if movie:
        await parts_view(bot, callback.from_user.id, movie, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "mp_add"), StateFilter("*"))
async def parts_add(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if movie:
        await episodes.start_parts(bot, callback.from_user.id, state, movie, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "mp_one"))
async def part_one(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    ep = await movies.episode(callback_data.id)
    if not ep or ep["season"] != 0:
        await answer(callback, t.MP_GONE, alert=True)
        return
    markup = kb([
        [btn(t.BTN_REPLACE, Adm(a="mp_rep", id=ep["id"])), btn(t.BTN_DELETE, Adm(a="mp_del", id=ep["id"]))],
        [btn(t.BTN_BACK, Adm(a="mp_list", id=ep["movie_id"]))],
    ])
    await render(bot, callback.from_user.id, callback.message,
                 t.MP_ONE.format(n=ep["number"], views=ep["views"]), markup)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "mp_del"))
async def part_delete(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    ep = await movies.episode(callback_data.id)
    if not ep or ep["season"] != 0:
        await answer(callback, t.MP_GONE, alert=True)
        return
    await movies.delete_episode(ep["id"])
    await answer(callback, t.DELETED)
    movie = await movies.get(ep["movie_id"])
    if movie:
        await parts_view(bot, callback.from_user.id, movie, callback.message)


@router.callback_query(Adm.filter(F.a == "mp_rep"))
async def part_replace(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.set_state(PartReplace.file)
    await state.update_data(episode_id=callback_data.id)
    await render(bot, callback.from_user.id, callback.message, t.MP_REPLACE_SEND, cancel_kb())
    await answer(callback)


@router.message(PartReplace.file)
async def part_replace_file(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    ep = await movies.episode(int(data.get("episode_id", 0)))
    if not ep or ep["season"] != 0:
        await state.clear()
        await message.answer(t.MP_GONE)
        return
    try:
        stored = await store_media(bot, message)
    except TelegramAPIError as exc:
        await message.answer(t.ADD_STORAGE_ERROR.format(error=esc(str(exc))))
        return
    if not stored:
        await message.answer(t.ADD_NEED_VIDEO, reply_markup=cancel_kb())
        return
    await movies.save_episode(ep["movie_id"], 0, ep["number"], *stored)
    await state.clear()
    await message.answer(t.MP_REPLACED.format(n=ep["number"]))
    movie = await movies.get(ep["movie_id"])
    if movie:
        await parts_view(bot, message.chat.id, movie)
