"""📺 Qism qo'shish: ketma-ket video/forward, almashtirish va o'chirish."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import movies
from handlers.admin.common import RoleFilter, back_panel_kb, cancel_kb, media_file_id, store_media
from keyboards.callbacks import Adm
from keyboards.common import btn, chunk, kb
from services import search
from utils.text import esc, parse_int
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("moderator"))
router.callback_query.filter(RoleFilter("moderator"))
log = logging.getLogger(__name__)

Row = dict[str, Any]

FLUSH_DELAY = 1.5  # albom/ko'p forward bir vaqtda kelganda tartibni saqlash uchun


class EpAdd(StatesGroup):
    find = State()
    season = State()
    start = State()
    upload = State()
    replace = State()


# admin -> kelgan xabarlar navbati
_buffers: dict[int, list[Message]] = {}
_timers: dict[int, asyncio.Task] = {}


def done_kb() -> InlineKeyboardMarkup:
    return kb([[btn(t.BTN_EP_DONE, Adm(a="epd"))]])


async def start_for_movie(bot: Bot, chat_id: int, state: FSMContext, movie: Row, message: object = None) -> None:
    await state.clear()
    await state.set_state(EpAdd.season)
    await state.update_data(movie_id=movie["id"])
    seasons = await movies.seasons(movie["id"])
    hint = t.EP_SEASONS_HAVE.format(seasons=", ".join(map(str, seasons))) if seasons else ""
    buttons = [btn(str(s), Adm(a="eps_s", v=str(s))) for s in seasons]
    buttons.append(btn(t.BTN_NEW_SEASON.format(n=(max(seasons) + 1) if seasons else 1),
                       Adm(a="eps_s", v=str((max(seasons) + 1) if seasons else 1))))
    await render(bot, chat_id, message,
                 t.EP_ASK_SEASON.format(title=esc(movie["title"]), code=movie["code"]) + hint,
                 cancel_kb(*chunk(buttons, 4)))


@router.callback_query(Adm.filter(F.a == "eps"), StateFilter("*"))
async def eps_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await state.set_state(EpAdd.find)
    await render(bot, callback.from_user.id, callback.message, t.EP_FIND, cancel_kb())
    await answer(callback)


@router.message(EpAdd.find, F.text)
async def eps_find(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text.strip()
    if text.isdigit():
        movie = await movies.by_code(int(text))
        if not movie or movie["type"] != "serial":
            await message.answer(t.EP_NOT_SERIAL)
            return
        await start_for_movie(bot, message.chat.id, state, movie)
        return
    found = [e for e in await search.search(text) if e.type == "serial"][:10]
    if not found:
        await message.answer(t.EP_NOT_SERIAL)
        return
    rows = [[btn(f"📺 {e.title} [{e.code}]", Adm(a="eps_m", id=e.id))] for e in found]
    await message.answer(t.EP_CHOOSE, reply_markup=cancel_kb(*rows))


@router.callback_query(EpAdd.find, Adm.filter(F.a == "eps_m"))
async def eps_pick(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    await start_for_movie(bot, callback.from_user.id, state, movie, callback.message)
    await answer(callback)


async def _ask_start(bot: Bot, chat_id: int, state: FSMContext, season: int, message: object = None) -> None:
    data = await state.get_data()
    eps = await movies.episodes(int(data["movie_id"]), season)
    nxt = (eps[-1]["number"] + 1) if eps else 1
    await state.update_data(season=season)
    await state.set_state(EpAdd.start)
    await render(bot, chat_id, message, t.EP_ASK_START.format(season=season, n=nxt),
                 cancel_kb([btn(t.BTN_START_FROM.format(n=nxt), Adm(a="eps_n", v=str(nxt)))]))


@router.callback_query(EpAdd.season, Adm.filter(F.a == "eps_s"))
async def eps_season_cb(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await _ask_start(bot, callback.from_user.id, state, int(callback_data.v), callback.message)
    await answer(callback)


@router.message(EpAdd.season, F.text)
async def eps_season(message: Message, state: FSMContext, bot: Bot) -> None:
    season = parse_int(message.text)
    if not season or season < 1:
        await message.answer(t.BAD_NUMBER)
        return
    await _ask_start(bot, message.chat.id, state, season)


async def _begin_upload(bot: Bot, chat_id: int, state: FSMContext, number: int, message: object = None) -> None:
    await state.update_data(next_number=number)
    await state.set_state(EpAdd.upload)
    data = await state.get_data()
    await render(bot, chat_id, message, t.EP_UPLOAD.format(season=data["season"], n=number), done_kb())


@router.callback_query(EpAdd.start, Adm.filter(F.a == "eps_n"))
async def eps_start_cb(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await _begin_upload(bot, callback.from_user.id, state, int(callback_data.v), callback.message)
    await answer(callback)


@router.message(EpAdd.start, F.text)
async def eps_start_number(message: Message, state: FSMContext, bot: Bot) -> None:
    number = parse_int(message.text)
    if not number or number < 1:
        await message.answer(t.BAD_NUMBER)
        return
    await _begin_upload(bot, message.chat.id, state, number)


@router.message(EpAdd.upload)
async def eps_upload(message: Message, state: FSMContext, bot: Bot) -> None:
    if not media_file_id(message):
        await message.answer(t.ADD_NEED_VIDEO, reply_markup=done_kb())
        return
    uid = message.from_user.id  # type: ignore[union-attr]
    _buffers.setdefault(uid, []).append(message)
    timer = _timers.get(uid)
    if timer and not timer.done():
        timer.cancel()
    _timers[uid] = asyncio.create_task(_flush_later(bot, uid, state))


async def _flush_later(bot: Bot, uid: int, state: FSMContext) -> None:
    try:
        await asyncio.sleep(FLUSH_DELAY)
    except asyncio.CancelledError:
        return
    batch = sorted(_buffers.pop(uid, []), key=lambda m: m.message_id)
    if not batch:
        return
    data = await state.get_data()
    if "movie_id" not in data or "season" not in data:
        return  # admin rejimni yopib ulgurgan
    movie_id, season = int(data["movie_id"]), int(data["season"])
    number = int(data.get("next_number", 1))
    lines = []
    for message in batch:
        try:
            stored = await store_media(bot, message)
        except TelegramAPIError as exc:
            lines.append(t.EP_FAILED.format(season=season, n=number, error=esc(str(exc)[:100])))
            continue
        if not stored:
            continue
        replaced = await movies.save_episode(movie_id, season, number, *stored)
        if season == 0:
            lines.append((t.MP_REPLACED if replaced else t.MP_ADDED).format(n=number))
        else:
            lines.append((t.EP_REPLACED if replaced else t.EP_ADDED).format(season=season, n=number))
        number += 1
    await state.update_data(next_number=number)
    try:
        nxt_text = (t.MP_NEXT if season == 0 else t.EP_NEXT).format(n=number)
        await bot.send_message(uid, "\n".join(lines) + "\n\n" + nxt_text, reply_markup=done_kb())
    except TelegramAPIError:
        pass


@router.callback_query(Adm.filter(F.a == "epd"), StateFilter("*"))
async def eps_done(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    movie = await movies.get(int(data.get("movie_id", 0))) if data.get("movie_id") else None
    count = await movies.episode_count(movie["id"]) if movie else 0
    if movie and data.get("season") == 0:
        text = t.MP_DONE.format(title=esc(movie["title"]), count=count + 1)
    else:
        text = t.EP_DONE.format(title=esc(movie["title"]), count=count) if movie else t.CANCELLED
    await render(bot, callback.from_user.id, callback.message, text,
                 back_panel_kb([btn(t.BTN_ADD_MORE, Adm(a="add"))]))
    await answer(callback)


# ---------- tahrirlash menyusidan: qismlar ro'yxati, almashtirish, o'chirish ----------

async def seasons_view(bot: Bot, chat_id: int, movie: Row, message: object = None) -> None:
    seasons = await movies.seasons(movie["id"])
    buttons = [btn(t.BTN_SEASON.format(n=s), Adm(a="ese", id=movie["id"], v=str(s))) for s in seasons]
    rows = chunk(buttons, 3)
    rows.append([btn(t.BTN_ADD_EPISODES, Adm(a="eadd", id=movie["id"]))])
    rows.append([btn(t.BTN_BACK, Adm(a="em", id=movie["id"]))])
    text = t.EP_SEASONS.format(title=esc(movie["title"])) if seasons else t.NO_EPISODES
    await render(bot, chat_id, message, text, kb(rows))


@router.callback_query(Adm.filter(F.a == "eadd"), StateFilter("*"))
async def eps_add_for(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if movie:
        await start_for_movie(bot, callback.from_user.id, state, movie, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "ese"))
async def eps_list(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    season = int(callback_data.v)
    eps = await movies.episodes(callback_data.id, season)
    buttons = [btn(str(e["number"]), Adm(a="eep", id=e["id"])) for e in eps]
    rows = chunk(buttons, 6)
    rows.append([btn(t.BTN_BACK, Adm(a="eser", id=callback_data.id))])
    await render(bot, callback.from_user.id, callback.message, t.EP_LIST.format(season=season), kb(rows))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "eep"), StateFilter("*"))
async def eps_one(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    ep = await movies.episode(callback_data.id)
    if not ep:
        await answer(callback, t.EPISODE_NOT_FOUND, alert=True)
        return
    markup = kb([
        [btn(t.BTN_REPLACE, Adm(a="epr", id=ep["id"])), btn(t.BTN_DELETE, Adm(a="epx", id=ep["id"]))],
        [btn(t.BTN_BACK, Adm(a="ese", id=ep["movie_id"], v=str(ep["season"])))],
    ])
    await render(bot, callback.from_user.id, callback.message,
                 t.EP_ONE.format(season=ep["season"], n=ep["number"], views=ep["views"]), markup)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "epx"))
async def eps_delete(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    ep = await movies.episode(callback_data.id)
    if not ep:
        await answer(callback, t.EPISODE_NOT_FOUND, alert=True)
        return
    await movies.delete_episode(ep["id"])
    await answer(callback, t.DELETED)
    eps = await movies.episodes(ep["movie_id"], ep["season"])
    rows = chunk([btn(str(e["number"]), Adm(a="eep", id=e["id"])) for e in eps], 6)
    rows.append([btn(t.BTN_BACK, Adm(a="eser", id=ep["movie_id"]))])
    await render(bot, callback.from_user.id, callback.message, t.EP_LIST.format(season=ep["season"]), kb(rows))


@router.callback_query(Adm.filter(F.a == "epr"))
async def eps_replace(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.set_state(EpAdd.replace)
    await state.update_data(episode_id=callback_data.id)
    await render(bot, callback.from_user.id, callback.message, t.EP_REPLACE_SEND, cancel_kb())
    await answer(callback)


@router.message(EpAdd.replace)
async def eps_replace_file(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    ep = await movies.episode(int(data.get("episode_id", 0)))
    if not ep:
        await state.clear()
        await message.answer(t.EPISODE_NOT_FOUND)
        return
    try:
        stored = await store_media(bot, message)
    except TelegramAPIError as exc:
        await message.answer(t.ADD_STORAGE_ERROR.format(error=esc(str(exc))))
        return
    if not stored:
        await message.answer(t.ADD_NEED_VIDEO, reply_markup=cancel_kb())
        return
    await movies.save_episode(ep["movie_id"], ep["season"], ep["number"], *stored)
    await state.clear()
    await message.answer(t.EP_REPLACED.format(season=ep["season"], n=ep["number"]),
                         reply_markup=back_panel_kb([btn(t.BTN_BACK, Adm(a="eep", id=ep["id"]))]))


async def start_parts(bot: Bot, chat_id: int, state: FSMContext, movie: Row, message: object = None) -> None:
    """Ko'p qismli film: 2, 3, ... qismlarni ketma-ket yuklash (episodes, season = 0)."""
    await state.clear()
    parts = await movies.parts(movie["id"])
    nxt = (parts[-1]["number"] + 1) if parts else 2
    await state.set_state(EpAdd.upload)
    await state.update_data(movie_id=movie["id"], season=0, next_number=nxt)
    await render(bot, chat_id, message, t.MP_UPLOAD.format(title=esc(movie["title"]), n=nxt), done_kb())
