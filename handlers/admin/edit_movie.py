"""✏️ Kino/serialni tahrirlash va o'chirish."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import movies
from handlers.admin import episodes
from handlers.admin.common import TYPES, RoleFilter, back_panel_kb, cancel_kb, languages_kb, store_media
from keyboards.callbacks import Adm
from keyboards.common import btn, chunk, kb
from services import search
from services.cards import fmt_rating, type_label
from services.tmdb import kind_of, tmdb
from utils.text import esc, money, parse_int, split_csv, truncate
from utils.time import fmt_runtime
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("moderator"))
router.callback_query.filter(RoleFilter("moderator"))

Row = dict[str, Any]


class EditMovie(StatesGroup):
    find = State()
    value = State()
    poster = State()
    file = State()
    lang_text = State()


# maydon -> (nomi, turi)
TEXT_FIELDS: dict[str, tuple[str, str]] = {
    "title": (t.F_TITLE, "str"),
    "original_title": (t.F_ORIGINAL, "str"),
    "description": (t.F_DESC, "str"),
    "year": (t.F_YEAR, "int"),
    "genres": (t.F_GENRES, "csv"),
    "countries": (t.F_COUNTRIES, "csv"),
    "runtime_min": (t.F_RUNTIME, "int"),
    "quality": (t.F_QUALITY, "str"),
    "code": (t.F_CODE, "int"),
    "price": (t.BM_F_PRICE, "int"),
}


def movie_admin_text(movie: Row, episodes_count: int | None) -> str:
    lines = [
        t.EDIT_HEAD.format(title=esc(movie["title"]), code=movie["code"], id=movie["id"]),
        f"{t.F_TYPE}: {type_label(movie['type'])} · {'💎 VIP' if movie['is_vip'] else t.FREE}",
        f"{t.BM_F_PRICE}: " + (f"{money(movie.get('price'))} so'm" if movie.get('price') else "—"),
        f"{t.F_ORIGINAL}: {esc(movie.get('original_title') or '—')}",
        f"{t.F_YEAR}: {movie.get('year') or '—'} · {t.F_RUNTIME}: {fmt_runtime(movie.get('runtime_min')) or '—'}",
        f"{t.F_GENRES}: {esc(movie.get('genres') or '—')}",
        f"{t.F_COUNTRIES}: {esc(movie.get('countries') or '—')}",
        f"{t.F_QUALITY}: {esc(movie.get('quality') or '—')} · {t.F_LANGS}: {esc(movie.get('languages') or '—')}",
        f"TMDB: {movie.get('tmdb_id') or '—'} · IMDb: {movie.get('imdb_id') or '—'}",
        f"{t.F_POST}: {movie.get('storage_message_id') or '—'} · 👁 {movie['views']} · ⭐ {fmt_rating(movie)}",
        f"{t.F_DESC}: {esc(truncate(movie.get('description') or '—', 300))}",
    ]
    if episodes_count is not None:
        lines.append(t.EDIT_EPISODES.format(n=episodes_count))
    return "\n".join(lines)


def movie_admin_kb(movie: Row) -> InlineKeyboardMarkup:
    m = movie["id"]
    fields = [btn(label, Adm(a="ev", id=m, v=key)) for key, (label, _) in TEXT_FIELDS.items()]
    rows = chunk(fields, 3)
    rows += [
        [btn(t.F_LANGS, Adm(a="elg", id=m)), btn(t.F_TYPE, Adm(a="ety", id=m)),
         btn(t.BTN_TO_FREE if movie["is_vip"] else t.BTN_TO_VIP, Adm(a="evip", id=m))],
        [btn(t.BTN_POSTER_NEW, Adm(a="epo", id=m)), btn(t.BTN_POSTER_TMDB, Adm(a="ept", id=m))],
    ]
    if movie["type"] == "serial":
        rows.append([btn(t.BTN_EPISODES_ADMIN, Adm(a="eser", id=m))])
    else:
        rows.append([btn(t.BTN_NEW_POST, Adm(a="efi", id=m)), btn(t.MP_BTN, Adm(a="mp_list", id=m))])
    rows.append([btn(t.BTN_DELETE, Adm(a="edl", id=m))])
    rows.append([btn(t.BTN_BACK, Adm(a="edit")), btn(t.BTN_ADMIN_PANEL, Adm(a="p"))])
    return kb(rows)


async def show_movie(bot: Bot, chat_id: int, movie_id: int, message: object = None) -> None:
    movie = await movies.get(movie_id)
    if not movie:
        await render(bot, chat_id, message, t.MOVIE_GONE, back_panel_kb())
        return
    count = await movies.episode_count(movie_id) if movie["type"] == "serial" else None
    await render(bot, chat_id, message, movie_admin_text(movie, count), movie_admin_kb(movie))


@router.callback_query(Adm.filter(F.a == "edit"), StateFilter("*"))
async def edit_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await state.set_state(EditMovie.find)
    await render(bot, callback.from_user.id, callback.message, t.EDIT_FIND, cancel_kb())
    await answer(callback)


@router.message(EditMovie.find, F.text)
async def edit_find(message: Message, state: FSMContext, bot: Bot) -> None:
    text = message.text.strip()
    if text.isdigit():
        movie = await movies.by_code(int(text))
        if not movie:
            await message.answer(t.ADMIN_CODE_NOT_FOUND)
            return
        await state.clear()
        await show_movie(bot, message.chat.id, movie["id"])
        return
    found = (await search.search(text))[:10]
    if not found:
        await message.answer(t.NOTHING_FOUND)
        return
    rows = [[btn(f"{e.title} ({e.year or '—'}) [{e.code}]", Adm(a="em", id=e.id))] for e in found]
    await message.answer(t.EDIT_CHOOSE, reply_markup=cancel_kb(*rows))


@router.callback_query(Adm.filter(F.a == "em"), StateFilter("*"))
async def edit_open(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await show_movie(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)


# ---------- matnli maydonlar ----------

@router.callback_query(Adm.filter(F.a == "ev"))
async def edit_value(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v not in TEXT_FIELDS:
        await answer(callback)
        return
    await state.set_state(EditMovie.value)
    await state.update_data(movie_id=callback_data.id, field=callback_data.v)
    label, _ = TEXT_FIELDS[callback_data.v]
    await render(bot, callback.from_user.id, callback.message, t.EDIT_ENTER.format(field=label),
                 cancel_kb([btn(t.BTN_CLEAR_FIELD, Adm(a="ecl", id=callback_data.id, v=callback_data.v))]
                           if callback_data.v not in ("title", "code") else []))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "ecl"), StateFilter("*"))
async def edit_clear(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    if callback_data.v in TEXT_FIELDS and callback_data.v not in ("title", "code"):
        await movies.update(callback_data.id, **{callback_data.v: None})
        search.invalidate()
    await show_movie(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback, t.SAVED_OK)


@router.message(EditMovie.value, F.text)
async def edit_value_text(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    movie_id, field = int(data["movie_id"]), str(data["field"])
    _, kind = TEXT_FIELDS[field]
    raw = message.text.strip()
    value: Any
    if kind == "int":
        value = parse_int(raw)
        if value is None or value < 0:
            await message.answer(t.BAD_NUMBER)
            return
        if field == "code" and (value == 0 or await movies.code_taken(value, movie_id)):
            await message.answer(t.CODE_TAKEN.format(code=value))
            return
    elif kind == "csv":
        value = ", ".join(split_csv(raw)) or None
    else:
        value = raw[:2000 if field == "description" else 200]
    await movies.update(movie_id, **{field: value})
    search.invalidate()
    await state.clear()
    await message.answer(t.SAVED_OK)
    await show_movie(bot, message.chat.id, movie_id)


# ---------- tur, VIP, til ----------

@router.callback_query(Adm.filter(F.a == "ety"))
async def edit_type(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    rows = [[btn(type_label(x), Adm(a="ets", id=callback_data.id, v=x)) for x in TYPES],
            [btn(t.BTN_BACK, Adm(a="em", id=callback_data.id))]]
    await render(bot, callback.from_user.id, callback.message, t.EDIT_CHOOSE_TYPE, kb(rows))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "ets"))
async def edit_type_set(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    if callback_data.v in TYPES:
        await movies.update(callback_data.id, type=callback_data.v)
        search.invalidate()
    await show_movie(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback, t.SAVED_OK)


@router.callback_query(Adm.filter(F.a == "evip"))
async def edit_vip(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if movie:
        await movies.update(movie["id"], is_vip=0 if movie["is_vip"] else 1)
        search.invalidate()
    await show_movie(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback, t.SAVED_OK)


async def _langs_view(bot: Bot, chat_id: int, movie_id: int, message: object = None) -> None:
    movie = await movies.get(movie_id)
    if not movie:
        return
    markup = languages_kb(split_csv(movie.get("languages")), "elt", "em", movie_id, extra=await movies.languages())
    await render(bot, chat_id, message, t.EDIT_LANGS, markup)


@router.callback_query(Adm.filter(F.a == "elg"))
async def edit_langs(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await _langs_view(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "elt"))
async def edit_lang_toggle(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v == "+":
        await state.set_state(EditMovie.lang_text)
        await state.update_data(movie_id=callback_data.id)
        await render(bot, callback.from_user.id, callback.message, t.ADD_LANG_TEXT, cancel_kb())
        await answer(callback)
        return
    movie = await movies.get(callback_data.id)
    if movie:
        selected = split_csv(movie.get("languages"))
        if callback_data.v in selected:
            selected.remove(callback_data.v)
        else:
            selected.append(callback_data.v)
        await movies.update(movie["id"], languages=", ".join(selected) or None)
    await _langs_view(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)


@router.message(EditMovie.lang_text, F.text)
async def edit_lang_text(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    movie = await movies.get(int(data.get("movie_id", 0)))
    if not movie:
        await message.answer(t.MOVIE_GONE)
        return
    selected = split_csv(movie.get("languages"))
    for name in split_csv(message.text):
        name = name[:30].capitalize()
        if name not in selected:
            selected.append(name)
    await movies.update(movie["id"], languages=", ".join(selected) or None)
    await _langs_view(bot, message.chat.id, movie["id"])


# ---------- poster va kanal posti ----------

@router.callback_query(Adm.filter(F.a == "epo"))
async def edit_poster(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.set_state(EditMovie.poster)
    await state.update_data(movie_id=callback_data.id)
    await render(bot, callback.from_user.id, callback.message, t.EDIT_SEND_POSTER, cancel_kb())
    await answer(callback)


@router.message(EditMovie.poster, F.photo)
async def edit_poster_photo(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    await movies.update(int(data["movie_id"]), poster_file_id=message.photo[-1].file_id)  # type: ignore[index]
    await message.answer(t.SAVED_OK)
    await show_movie(bot, message.chat.id, int(data["movie_id"]))


@router.callback_query(Adm.filter(F.a == "ept"))
async def edit_poster_tmdb(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if not movie or not movie.get("tmdb_id"):
        await answer(callback, t.EDIT_NO_TMDB, alert=True)
        return
    fields = await tmdb.fields(kind_of(movie["type"]), movie["tmdb_id"], with_overview=False)
    if not fields or not fields.get("poster_path"):
        await answer(callback, t.ADD_TMDB_FAILED, alert=True)
        return
    await movies.update(movie["id"], poster_path=fields["poster_path"], poster_file_id=None)
    await show_movie(bot, callback.from_user.id, movie["id"], callback.message)
    await answer(callback, t.SAVED_OK)


@router.callback_query(Adm.filter(F.a == "efi"))
async def edit_file(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.set_state(EditMovie.file)
    await state.update_data(movie_id=callback_data.id)
    await render(bot, callback.from_user.id, callback.message, t.ADD_SEND_FILE, cancel_kb())
    await answer(callback)


@router.message(EditMovie.file)
async def edit_file_got(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    try:
        stored = await store_media(bot, message)
    except TelegramAPIError as exc:
        await message.answer(t.ADD_STORAGE_ERROR.format(error=esc(str(exc))))
        return
    if not stored:
        await message.answer(t.ADD_NEED_VIDEO, reply_markup=cancel_kb())
        return
    storage_id, backup_id, file_id = stored
    await movies.update(int(data["movie_id"]), storage_message_id=storage_id, backup_message_id=backup_id,
                        file_id=file_id)
    await state.clear()
    await message.answer(t.SAVED_OK)
    await show_movie(bot, message.chat.id, int(data["movie_id"]))


@router.callback_query(Adm.filter(F.a == "eser"), StateFilter("*"))
async def edit_seasons(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    movie = await movies.get(callback_data.id)
    if movie:
        await episodes.seasons_view(bot, callback.from_user.id, movie, callback.message)
    await answer(callback)


# ---------- o'chirish ----------

@router.callback_query(Adm.filter(F.a == "edl"))
async def edit_delete(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    markup = kb([[btn(t.BTN_CONFIRM_DELETE, Adm(a="edy", id=movie["id"])),
                  btn(t.BTN_NO, Adm(a="em", id=movie["id"]))]])
    await render(bot, callback.from_user.id, callback.message,
                 t.EDIT_DELETE_CONFIRM.format(title=esc(movie["title"]), code=movie["code"]), markup)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "edy"))
async def edit_delete_yes(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await movies.delete(callback_data.id)
    search.invalidate()
    await render(bot, callback.from_user.id, callback.message, t.DELETED,
                 back_panel_kb([btn(t.BTN_BACK, Adm(a="edit"))]))
    await answer(callback)
