"""🎬 Kino qo'shish (FSM): tur -> fayl -> nom/TMDB -> sifat -> til -> VIP -> tavsif -> kod -> preview."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import misc, movies
from handlers.admin import episodes
from handlers.admin.common import (
    QUALITIES,
    TYPES,
    RoleFilter,
    back_panel_kb,
    cancel_kb,
    languages_kb,
    store_media,
)
from keyboards.callbacks import Adm
from keyboards.common import btn, chunk, kb
from services import posts, search
from services.cards import card_caption, type_label
from services.tmdb import kind_of, poster_url, result_title, result_year, tmdb
from utils.text import esc, parse_int, split_csv, truncate
from utils.time import fmt_local, parse_local, to_db, utcnow
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("moderator"))
router.callback_query.filter(RoleFilter("moderator"))
log = logging.getLogger(__name__)

Row = dict[str, Any]


class AddMovie(StatesGroup):
    type = State()
    file = State()
    title = State()
    title_edit = State()
    pick = State()
    m_year = State()
    m_genres = State()
    m_countries = State()
    m_runtime = State()
    m_poster = State()
    quality = State()
    quality_text = State()
    langs = State()
    lang_text = State()
    vip = State()
    desc = State()
    desc_text = State()
    code = State()
    code_text = State()
    preview = State()
    post_time = State()


ORDER = ["quality", "langs", "vip", "desc", "code", "preview"]
MANUAL = ["m_year", "m_genres", "m_countries", "m_runtime", "m_poster"]
MANUAL_PROMPTS = {
    "m_year": t.ADD_M_YEAR, "m_genres": t.ADD_M_GENRES, "m_countries": t.ADD_M_COUNTRIES,
    "m_runtime": t.ADD_M_RUNTIME, "m_poster": t.ADD_M_POSTER,
}
EDITABLE = [("title", t.F_TITLE), ("quality", t.F_QUALITY), ("langs", t.F_LANGS), ("vip", t.F_VIP),
            ("desc", t.F_DESC), ("code", t.F_CODE)]


def compose(data: dict[str, Any]) -> Row:
    """FSM ma'lumotlaridan `movies` qatori."""
    movie: Row = dict(data.get("tmdb") or {})
    for key in ("year", "genres", "countries", "runtime_min"):
        if data.get(key) is not None:
            movie[key] = data[key]
    movie.update(
        type=data.get("type", "film"),
        title=data.get("title", ""),
        quality=data.get("quality"),
        languages=", ".join(data.get("languages") or []) or None,
        is_vip=int(data.get("is_vip", 0)),
        description=data.get("description"),
        code=data.get("code") or 0,
        storage_message_id=data.get("storage_message_id"),
        backup_message_id=data.get("backup_message_id"),
        file_id=data.get("file_id"),
        poster_file_id=data.get("poster_file_id"),
        rating_sum=0,
        rating_count=0,
    )
    return movie


# ---------- qadamlar ----------

async def ask(step: str, bot: Bot, chat_id: int, state: FSMContext, message: object = None) -> None:
    data = await state.get_data()
    if step in MANUAL:
        markup = cancel_kb([btn(t.BTN_SKIP, Adm(a="ms", v=step))])
        text = MANUAL_PROMPTS[step]
    elif step == "quality":
        markup = cancel_kb([btn(q, Adm(a="q", v=q)) for q in QUALITIES] + [btn(t.BTN_OTHER, Adm(a="q", v="+"))])
        text = t.ADD_QUALITY
    elif step == "langs":
        markup = languages_kb(data.get("languages") or [], "lg", "lgd", extra=await movies.languages())
        markup.inline_keyboard.append([btn(t.BTN_CANCEL, Adm(a="x"))])
        text = t.ADD_LANGS
    elif step == "vip":
        markup = cancel_kb([btn(t.BTN_VIP_CONTENT, Adm(a="vp", v="1")), btn(t.BTN_FREE_CONTENT, Adm(a="vp", v="0"))])
        text = t.ADD_VIP
    elif step == "desc":
        row = [btn(t.BTN_DESC_TMDB, Adm(a="ds", v="tmdb"))] if data.get("tmdb_desc") else []
        row += [btn(t.BTN_DESC_OWN, Adm(a="ds", v="own")), btn(t.BTN_DESC_NONE, Adm(a="ds", v="none"))]
        markup = cancel_kb(row)
        preview = truncate(data.get("tmdb_desc") or "", 600)
        text = t.ADD_DESC + (f"\n\n<i>{esc(preview)}</i>" if preview else "")
    elif step == "code":
        auto = await movies.next_code()
        markup = cancel_kb([btn(t.BTN_CODE_AUTO.format(code=auto), Adm(a="cd", v="auto")),
                            btn(t.BTN_CODE_MANUAL, Adm(a="cd", v="man"))])
        text = t.ADD_CODE
    elif step == "preview":
        await show_preview(bot, chat_id, state)
        return
    else:
        raise ValueError(step)
    await state.set_state(getattr(AddMovie, step))
    await render(bot, chat_id, message, text, markup)


async def proceed(step: str, bot: Bot, chat_id: int, state: FSMContext, message: object = None) -> None:
    data = await state.get_data()
    if data.get("edit"):
        await state.update_data(edit=False)
        await show_preview(bot, chat_id, state)
        return
    if step in MANUAL:
        idx = MANUAL.index(step)
        nxt = MANUAL[idx + 1] if idx + 1 < len(MANUAL) else "quality"
    else:
        nxt = ORDER[ORDER.index(step) + 1]
    await ask(nxt, bot, chat_id, state, message)


async def show_preview(bot: Bot, chat_id: int, state: FSMContext) -> None:
    await state.set_state(AddMovie.preview)
    data = await state.get_data()
    movie = compose(data)
    caption = t.ADD_PREVIEW_HEAD.format(type=type_label(movie["type"])) + "\n\n" + card_caption(movie)
    markup = kb([
        [btn(t.BTN_SAVE_MOVIE, Adm(a="sv")), btn(t.BTN_EDIT, Adm(a="ed"))],
        [btn(t.BTN_CANCEL, Adm(a="x"))],
    ])
    photo = movie.get("poster_file_id") or poster_url(movie.get("poster_path"))
    if photo:
        try:
            msg = await bot.send_photo(chat_id, photo, caption=caption, reply_markup=markup)
            if msg.photo and not data.get("poster_file_id"):
                await state.update_data(poster_file_id=msg.photo[-1].file_id)
            return
        except TelegramBadRequest as exc:
            log.warning("Preview posteri yuborilmadi: %s", exc)
    await bot.send_message(chat_id, caption, reply_markup=markup)


# ---------- boshlash ----------

@router.message(Command("add"), StateFilter("*"))
async def cmd_add(message: Message, state: FSMContext, bot: Bot) -> None:
    await start(bot, message.chat.id, state, None)


@router.callback_query(Adm.filter(F.a == "add"), StateFilter("*"))
async def cb_add(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await start(bot, callback.from_user.id, state, callback.message)
    await answer(callback)


async def start(bot: Bot, chat_id: int, state: FSMContext, message: object) -> None:
    await state.clear()
    await state.set_state(AddMovie.type)
    markup = cancel_kb([btn(type_label(x), Adm(a="at", v=x)) for x in TYPES])
    await render(bot, chat_id, message, t.ADD_CHOOSE_TYPE, markup)


@router.callback_query(AddMovie.type, Adm.filter(F.a == "at"))
async def choose_type(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    movie_type = callback_data.v if callback_data.v in TYPES else "film"
    await state.update_data(type=movie_type)
    if movie_type == "serial":
        await state.set_state(AddMovie.title)
        await render(bot, callback.from_user.id, callback.message, t.ADD_TITLE, cancel_kb())
    else:
        await state.set_state(AddMovie.file)
        await render(bot, callback.from_user.id, callback.message, t.ADD_SEND_FILE, cancel_kb())
    await answer(callback)


@router.message(AddMovie.file)
async def got_file(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        stored = await store_media(bot, message)
    except TelegramAPIError as exc:
        await message.answer(t.ADD_STORAGE_ERROR.format(error=esc(str(exc))), reply_markup=cancel_kb())
        return
    if not stored:
        await message.answer(t.ADD_NEED_VIDEO, reply_markup=cancel_kb())
        return
    storage_id, backup_id, file_id = stored
    await state.update_data(storage_message_id=storage_id, backup_message_id=backup_id, file_id=file_id)
    await state.set_state(AddMovie.title)
    await message.answer(t.ADD_FILE_OK.format(mid=storage_id) + "\n\n" + t.ADD_TITLE, reply_markup=cancel_kb())


@router.message(AddMovie.title, F.text)
async def got_title(message: Message, state: FSMContext, bot: Bot) -> None:
    title = message.text.strip()[:200]
    await state.update_data(title=title)
    data = await state.get_data()
    kind = kind_of(data.get("type", "film"))
    results = (await tmdb.search(kind, title))[:5] if tmdb.enabled else []
    if not results:
        await message.answer(t.ADD_TMDB_NONE if tmdb.enabled else t.ADD_TMDB_DISABLED)
        await ask("m_year", bot, message.chat.id, state)
        return
    await state.set_state(AddMovie.pick)
    for item in results:
        name = result_title(item)
        year = result_year(item)
        original = item.get("original_title") or item.get("original_name") or ""
        caption = f"<b>{esc(name)}</b>" + (f" ({year})" if year else "")
        if original and original != name:
            caption += f"\n<i>{esc(original)}</i>"
        overview = truncate(item.get("overview") or "", 300)
        if overview:
            caption += f"\n\n{esc(overview)}"
        markup = kb([[btn(t.BTN_PICK, Adm(a="tp", id=item["id"]))]])
        photo = poster_url(item.get("poster_path"), "w342")
        try:
            if photo:
                await message.answer_photo(photo, caption=caption, reply_markup=markup)
            else:
                await message.answer(caption, reply_markup=markup)
        except TelegramBadRequest:
            await message.answer(caption, reply_markup=markup)
    await message.answer(t.ADD_PICK_HINT, reply_markup=cancel_kb([btn(t.BTN_MANUAL, Adm(a="tm"))]))


@router.callback_query(AddMovie.pick, Adm.filter(F.a == "tp"))
async def pick_tmdb(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    fields = await tmdb.fields(kind_of(data.get("type", "film")), callback_data.id)
    if not fields:
        await answer(callback, t.ADD_TMDB_FAILED, alert=True)
        return
    description = fields.pop("description", None)
    await state.update_data(tmdb=fields, tmdb_desc=description)
    await answer(callback, t.ADD_TMDB_PICKED)
    await ask("quality", bot, callback.from_user.id, state)


@router.callback_query(AddMovie.pick, Adm.filter(F.a == "tm"))
async def pick_manual(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.update_data(tmdb=None, tmdb_desc=None)
    await ask("m_year", bot, callback.from_user.id, state, callback.message)
    await answer(callback)


# ---------- qo'lda kiritish ----------

@router.callback_query(StateFilter(*[getattr(AddMovie, s) for s in MANUAL]), Adm.filter(F.a == "ms"))
async def manual_skip(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await proceed(callback_data.v, bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.message(AddMovie.m_year, F.text)
async def manual_year(message: Message, state: FSMContext, bot: Bot) -> None:
    year = parse_int(message.text)
    if not year or not 1900 <= year <= 2100:
        await message.answer(t.BAD_YEAR)
        return
    await state.update_data(year=year)
    await proceed("m_year", bot, message.chat.id, state)


@router.message(AddMovie.m_genres, F.text)
async def manual_genres(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(genres=", ".join(split_csv(message.text))[:200] or None)
    await proceed("m_genres", bot, message.chat.id, state)


@router.message(AddMovie.m_countries, F.text)
async def manual_countries(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(countries=", ".join(split_csv(message.text))[:200] or None)
    await proceed("m_countries", bot, message.chat.id, state)


@router.message(AddMovie.m_runtime, F.text)
async def manual_runtime(message: Message, state: FSMContext, bot: Bot) -> None:
    minutes = parse_int(message.text)
    if not minutes or not 1 <= minutes <= 1000:
        await message.answer(t.BAD_RUNTIME)
        return
    await state.update_data(runtime_min=minutes)
    await proceed("m_runtime", bot, message.chat.id, state)


@router.message(AddMovie.m_poster, F.photo)
async def manual_poster(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(poster_file_id=message.photo[-1].file_id)  # type: ignore[index]
    await proceed("m_poster", bot, message.chat.id, state)


# ---------- sifat, til, VIP, tavsif, kod ----------

@router.callback_query(AddMovie.quality, Adm.filter(F.a == "q"))
async def choose_quality(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v == "+":
        await state.set_state(AddMovie.quality_text)
        await render(bot, callback.from_user.id, callback.message, t.ADD_QUALITY_TEXT, cancel_kb())
    else:
        await state.update_data(quality=callback_data.v)
        await proceed("quality", bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.message(AddMovie.quality_text, F.text)
async def quality_text(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(quality=message.text.strip()[:30])
    await proceed("quality", bot, message.chat.id, state)


@router.callback_query(AddMovie.langs, Adm.filter(F.a == "lg"))
async def toggle_lang(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v == "+":
        await state.set_state(AddMovie.lang_text)
        await render(bot, callback.from_user.id, callback.message, t.ADD_LANG_TEXT, cancel_kb())
        await answer(callback)
        return
    data = await state.get_data()
    selected: list[str] = list(data.get("languages") or [])
    if callback_data.v in selected:
        selected.remove(callback_data.v)
    else:
        selected.append(callback_data.v)
    await state.update_data(languages=selected)
    await ask("langs", bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.message(AddMovie.lang_text, F.text)
async def lang_text(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    selected: list[str] = list(data.get("languages") or [])
    for name in split_csv(message.text):
        name = name[:30].capitalize()
        if name not in selected:
            selected.append(name)
    await state.update_data(languages=selected)
    await ask("langs", bot, message.chat.id, state)


@router.callback_query(AddMovie.langs, Adm.filter(F.a == "lgd"))
async def langs_done(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    if not data.get("languages"):
        await answer(callback, t.ADD_LANG_REQUIRED, alert=True)
        return
    await proceed("langs", bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.callback_query(AddMovie.vip, Adm.filter(F.a == "vp"))
async def choose_vip(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.update_data(is_vip=1 if callback_data.v == "1" else 0)
    await proceed("vip", bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.callback_query(AddMovie.desc, Adm.filter(F.a == "ds"))
async def choose_desc(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v == "own":
        await state.set_state(AddMovie.desc_text)
        await render(bot, callback.from_user.id, callback.message, t.ADD_DESC_TEXT, cancel_kb())
        await answer(callback)
        return
    data = await state.get_data()
    await state.update_data(description=data.get("tmdb_desc") if callback_data.v == "tmdb" else None)
    await proceed("desc", bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.message(AddMovie.desc_text, F.text)
async def desc_text(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(description=message.text.strip()[:2000])
    await proceed("desc", bot, message.chat.id, state)


@router.callback_query(AddMovie.code, Adm.filter(F.a == "cd"))
async def choose_code(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v == "man":
        await state.set_state(AddMovie.code_text)
        await render(bot, callback.from_user.id, callback.message, t.ADD_CODE_TEXT, cancel_kb())
        await answer(callback)
        return
    await state.update_data(code=await movies.next_code(), code_auto=True)
    await proceed("code", bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.message(AddMovie.code_text, F.text)
async def code_text(message: Message, state: FSMContext, bot: Bot) -> None:
    code = parse_int(message.text)
    if not code or code <= 0:
        await message.answer(t.BAD_CODE)
        return
    if await movies.code_taken(code):
        await message.answer(t.CODE_TAKEN.format(code=code))
        return
    await state.update_data(code=code, code_auto=False)
    await proceed("code", bot, message.chat.id, state)


# ---------- preview: tahrirlash va saqlash ----------

@router.callback_query(AddMovie.preview, Adm.filter(F.a == "ed"))
async def edit_menu(callback: CallbackQuery, bot: Bot) -> None:
    rows = chunk([btn(label, Adm(a="ef", v=key)) for key, label in EDITABLE], 3)
    rows.append([btn(t.BTN_BACK, Adm(a="pv"))])
    await bot.send_message(callback.from_user.id, t.ADD_EDIT_WHICH, reply_markup=kb(rows))
    await answer(callback)


@router.callback_query(AddMovie.preview, Adm.filter(F.a == "pv"))
async def back_to_preview(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await show_preview(bot, callback.from_user.id, state)
    await answer(callback)


@router.callback_query(AddMovie.preview, Adm.filter(F.a == "ef"))
async def edit_field(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.update_data(edit=True)
    if callback_data.v == "title":
        await state.set_state(AddMovie.title_edit)
        await render(bot, callback.from_user.id, callback.message, t.ADD_TITLE, cancel_kb())
    else:
        await ask(callback_data.v, bot, callback.from_user.id, state, callback.message)
    await answer(callback)


@router.message(AddMovie.title_edit, F.text)
async def title_edit(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.update_data(title=message.text.strip()[:200], edit=False)
    await show_preview(bot, message.chat.id, state)


@router.callback_query(AddMovie.preview, Adm.filter(F.a == "sv"))
async def save(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    movie = compose(data)
    if await movies.code_taken(movie["code"]):
        if not data.get("code_auto"):
            await answer(callback, t.CODE_TAKEN.format(code=movie["code"]), alert=True)
            await state.update_data(edit=True)
            await ask("code", bot, callback.from_user.id, state)
            return
        movie["code"] = await movies.next_code()
    movie_id = await movies.create(movie)
    search.invalidate()
    await state.clear()
    saved = await movies.get(movie_id)
    await answer(callback, t.ADD_SAVED_SHORT)
    await bot.send_message(
        callback.from_user.id,
        t.ADD_SAVED.format(code=saved["code"], title=esc(saved["title"])) + "\n\n" + t.ADD_ASK_NOTIFY,  # type: ignore[index]
        reply_markup=kb([[btn(t.BTN_YES, Adm(a="nt", id=movie_id, v="1")),
                          btn(t.BTN_NO, Adm(a="nt", id=movie_id, v="0"))]]),
    )


def _post_kb(movie_id: int):
    return kb([[btn(t.BTN_POST_NOW, Adm(a="pt", id=movie_id, v="now")),
                btn(t.BTN_POST_LATER, Adm(a="pt", id=movie_id, v="sch")),
                btn(t.BTN_NO, Adm(a="pt", id=movie_id, v="no"))]])


@router.callback_query(Adm.filter(F.a == "nt"), StateFilter("*"))
async def ask_notify(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    note = t.NOTIFY_SKIPPED
    if callback_data.v == "1":
        ahead = await posts.notify_new_movie(bot, movie, callback.from_user.id)
        note = t.NOTIFY_QUEUED + (t.QUEUE_AHEAD.format(n=ahead) if ahead else "")
    await render(bot, callback.from_user.id, callback.message, note + "\n\n" + t.ADD_ASK_POST, _post_kb(movie["id"]))
    await answer(callback)


async def finish(bot: Bot, chat_id: int, state: FSMContext, movie: Row) -> None:
    if movie["type"] == "serial":
        await episodes.start_for_movie(bot, chat_id, state, movie)
        return
    await state.clear()
    await bot.send_message(chat_id, t.ADD_DONE.format(code=movie["code"]),
                           reply_markup=back_panel_kb([btn(t.BTN_ADD_MORE, Adm(a="add"))]))


@router.callback_query(Adm.filter(F.a == "pt"), StateFilter("*"))
async def ask_post(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    if callback_data.v == "sch":
        await state.set_state(AddMovie.post_time)
        await state.update_data(post_movie_id=movie["id"])
        await render(bot, callback.from_user.id, callback.message, t.ADD_POST_TIME, cancel_kb())
        await answer(callback)
        return
    if callback_data.v == "now":
        ok = await posts.public_post(bot, movie)
        await render(bot, callback.from_user.id, callback.message, t.POST_DONE if ok else t.POST_FAILED)
    else:
        await render(bot, callback.from_user.id, callback.message, t.POST_SKIPPED)
    await answer(callback)
    await finish(bot, callback.from_user.id, state, movie)


@router.message(AddMovie.post_time, F.text)
async def post_time(message: Message, state: FSMContext, bot: Bot) -> None:
    when = parse_local(message.text)
    if not when or when <= utcnow():
        await message.answer(t.BAD_DATETIME)
        return# ---------- Mavjud kinoga qism qo'shish (Part FSM) ----------

class AddMoviePart(StatesGroup):
    waiting_for_code = State()
    waiting_for_number = State()
    waiting_for_file = State()


# Admin menyusidan "Qism qo'shish" bosilganda ishga tushadigan handler
@router.message(Command("add_part"), StateFilter("*"))
async def cmd_add_part(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(AddMoviePart.waiting_for_code)
    await message.answer("🎬 Qaysi kinoga qism qo'shmoqchisiz? Asosiy kino **kodini** kiriting:", reply_markup=cancel_kb())


@router.message(AddMoviePart.waiting_for_code, F.text)
async def part_got_code(message: Message, state: FSMContext) -> None:
    code = parse_int(message.text)
    if not code:
        await message.answer("❌ Iltimos, to'g'ri kod kiriting:")
        return
    
    movie = await movies.get_by_code(code)
    if not movie:
        await message.answer("❌ Bu kod bilan kino topilmadi. Qaytadan kiriting:")
        return
    
    await state.update_data(parent_movie_id=movie["id"])
    await state.set_state(AddMoviePart.waiting_for_number)
    await message.answer(f"✅ <b>{esc(movie['title'])}</b> topildi.\n\nBu nechanchi qism? (Masalan: 2, 3...):", reply_markup=cancel_kb())


@router.message(AddMoviePart.waiting_for_number, F.text)
async def part_got_number(message: Message, state: FSMContext) -> None:
    num = parse_int(message.text)
    if not num or num < 1:
        await message.answer("❌ Noto'g'ri raqam. Qism raqamini 1 dan katta qilib kiriting:")
        return
    
    await state.update_data(part_number=num)
    await state.set_state(AddMoviePart.waiting_for_file)
    await message.answer(f"📥 Endi {num}-qismning **video faylini** yuboring:", reply_markup=cancel_kb())


@router.message(AddMoviePart.waiting_for_file, F.video)
async def part_got_file(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        stored = await store_media(bot, message)
    except TelegramAPIError as exc:
        await message.answer(t.ADD_STORAGE_ERROR.format(error=esc(str(exc))), reply_markup=cancel_kb())
        return
    
    if not stored:
        await message.answer(t.ADD_NEED_VIDEO, reply_markup=cancel_kb())
        return
    
    storage_id, backup_id, file_id = stored
    data = await state.get_data()
    
    # Bazaga saqlaymiz
    await movies.add_movie_part(
        movie_id=data["parent_movie_id"],
        part_number=data["part_number"],
        file_id=file_id,
        storage_message_id=storage_id,
        backup_message_id=backup_id
    )
    
    await state.clear()
    await message.answer(f"✅ Muvaffaqiyatli! Kinoning **{data['part_number']}-qismi** qo'shildi.", reply_markup=back_panel_kb())
    data = await state.get_data()
    movie = await movies.get(int(data.get("post_movie_id", 0)))
    if not movie:
        await state.clear()
        await message.answer(t.MOVIE_GONE)
        return
    await misc.add_scheduled(movie["id"], to_db(when), message.from_user.id)  # type: ignore[union-attr]
    await message.answer(t.POST_SCHEDULED.format(time=fmt_local(when)))
    await finish(bot, message.chat.id, state, movie)


