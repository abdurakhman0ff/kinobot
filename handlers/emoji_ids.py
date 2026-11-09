"""/emojiid: yuborilgan premium emoji'larning ID sini qaytaradi (faqat admin)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import users

router = Router()


@router.message(Command("emojiid"))
async def emoji_ids(message: Message) -> None:
    if not users.has_role(message.from_user.id, "admin"):  # type: ignore[union-attr]
        return
    ids = [e.custom_emoji_id for e in (message.entities or []) if e.type == "custom_emoji"]
    if not ids:
        await message.answer("Buyruq yoniga premium emoji yozing, masalan: /emojiid (emoji)")
        return
    await message.answer("\n".join(f"<code>{i}</code>" for i in ids))


@router.message(Command("rmkb"))
async def remove_reply_keyboard(message: Message) -> None:
    """Eski versiyadan qolgan pastki (reply) klaviaturani chatdan olib tashlaydi."""
    if not users.has_role(message.from_user.id, "admin"):  # type: ignore[union-attr]
        return
    from aiogram.types import ReplyKeyboardRemove

    sent = await message.answer("✅ Pastki tugmalar olib tashlandi.", reply_markup=ReplyKeyboardRemove())
    try:
        await sent.delete()
    except Exception:  # noqa: BLE001
        pass


# ---------- treyler yuklash va kartochkani ko'rish (admin) ----------
from aiogram import Bot, F  # noqa: E402
from aiogram.filters import CommandObject  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.state import State, StatesGroup  # noqa: E402

import texts as t  # noqa: E402
from database import movies, users  # noqa: E402
from utils.text import esc  # noqa: E402


class TrailerForm(StatesGroup):
    video = State()


@router.message(Command("treyler"))
async def trailer_cmd(message: Message, command: CommandObject, state: FSMContext) -> None:
    if not users.has_role(message.from_user.id, "moderator"):  # type: ignore[union-attr]
        return
    args = (command.args or "").split()
    if not args or not args[0].isdigit():
        await message.answer(t.BM_TRAILER_USAGE)
        return
    movie = await movies.by_code(int(args[0]))
    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi.")
        return
    if len(args) > 1:
        await movies.update(movie["id"], trailer_file_id=None)
        await message.answer(t.BM_TRAILER_DELETED)
        return
    await state.set_state(TrailerForm.video)
    await state.update_data(trailer_movie_id=movie["id"])
    await message.answer(t.BM_TRAILER_ASK.format(title=esc(movie["title"])))


@router.message(TrailerForm.video, F.video)
async def trailer_got_video(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    movie_id = int(data.get("trailer_movie_id") or 0)
    await state.clear()
    if not movie_id:
        return
    await movies.update(movie_id, trailer_file_id=message.video.file_id)  # type: ignore[union-attr]
    await message.answer(t.BM_TRAILER_SAVED)


@router.message(TrailerForm.video, Command("cancel"))
async def trailer_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.message(TrailerForm.video)
async def trailer_bad(message: Message) -> None:
    await message.answer(t.BM_TRAILER_BAD)


@router.message(Command("korish"))
async def preview_buy_card(message: Message, command: CommandObject, bot: Bot) -> None:
    if not users.has_role(message.from_user.id, "moderator"):  # type: ignore[union-attr]
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer(t.BM_TRAILER_USAGE)
        return
    movie = await movies.by_code(int(arg))
    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi.")
        return
    if not int(movie.get("price") or 0):
        await message.answer("Bu kino bepul, sotib olish kartochkasi yo'q.")
        return
    from services import delivery
    await delivery.send_buy_card(bot, message.chat.id, movie)


# ---------- bazani tiklash (faqat asosiy admin) ----------
import asyncio  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup  # noqa: E402

import config  # noqa: E402


class RestoreDb(StatesGroup):
    file = State()


def _is_owner(user_id: int | None) -> bool:
    return user_id == config.ADMIN_ID


@router.message(Command("restoredb"))
async def restoredb_cmd(message: Message, state: FSMContext) -> None:
    if not _is_owner(message.from_user.id):  # type: ignore[union-attr]
        return
    await state.set_state(RestoreDb.file)
    await message.answer("🗄 Zaxira .db faylini yuboring (fayl sifatida). Bekor qilish: /cancel")


@router.message(RestoreDb.file, Command("cancel"))
async def restoredb_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.message(RestoreDb.file, F.document)
async def restoredb_file(message: Message, state: FSMContext, bot: Bot) -> None:
    if not _is_owner(message.from_user.id):  # type: ignore[union-attr]
        return
    pending = config.DB_PATH + ".restore"
    os.makedirs(os.path.dirname(os.path.abspath(pending)), exist_ok=True)
    try:
        await bot.download(message.document, destination=pending)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"❌ Fayl yuklab olinmadi: {esc(str(exc)[:200])}")
        return
    try:
        con = sqlite3.connect(f"file:{pending}?mode=ro", uri=True)
        ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        users_n = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        movies_n = con.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        con.close()
    except Exception as exc:  # noqa: BLE001
        os.remove(pending)
        await message.answer(f"❌ Bu to'g'ri baza fayli emas: {esc(str(exc)[:200])}")
        return
    if not ok:
        os.remove(pending)
        await message.answer("❌ Baza fayli buzilgan (integrity_check ok emas).")
        return
    await state.clear()
    markup = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tiklash", callback_data="rdb_ok"),
        InlineKeyboardButton(text="❌ Bekor", callback_data="rdb_no"),
    ]])
    await message.answer(
        f"🗄 Fayl tekshirildi: foydalanuvchilar {users_n}, kinolar {movies_n}.\n\n"
        "⚠️ Tiklash joriy bazani almashtiradi va botni qayta ishga tushiradi. Davom etamizmi?",
        reply_markup=markup,
    )


@router.callback_query(F.data == "rdb_no")
async def restoredb_no(callback: CallbackQuery) -> None:
    if not _is_owner(callback.from_user.id):
        return
    try:
        os.remove(config.DB_PATH + ".restore")
    except FileNotFoundError:
        pass
    await callback.message.edit_text("Bekor qilindi.")  # type: ignore[union-attr]
    await callback.answer()


@router.callback_query(F.data == "rdb_ok")
async def restoredb_apply(callback: CallbackQuery) -> None:
    if not _is_owner(callback.from_user.id):
        return
    if not os.path.exists(config.DB_PATH + ".restore"):
        await callback.answer("Fayl topilmadi, qaytadan /restoredb qiling.", show_alert=True)
        return
    await callback.message.edit_text("♻️ Baza tiklanmoqda. Bot qayta ishga tushadi (1 daqiqagacha).")  # type: ignore[union-attr]
    await callback.answer()
    await asyncio.sleep(1)
    os._exit(3)  # Railway (ON_FAILURE) botni qayta ishga tushiradi, baza ochilishidan oldin almashadi


# ---------- VIP bo'lim ----------
from aiogram import Bot as _Bot, F as _F  # noqa: E402
from aiogram.types import CallbackQuery as _CQ  # noqa: E402
from database import users as _users  # noqa: E402
from database.db import db as _db  # noqa: E402
from database.movies import SHORT as _SHORT  # noqa: E402
from keyboards.callbacks import Nav as _Nav, Pg as _Pg  # noqa: E402
from keyboards.common import btn as _btn, kb as _kb, list_kb as _list_kb, pages_of as _pages_of  # noqa: E402
from utils.text import esc as _esc  # noqa: E402
from utils.ui import answer as _answer, render as _render  # noqa: E402

_VZ_PER_PAGE = 8


def _vz_op(series: bool) -> str:
    return "=" if series else "!="


async def _vz_count(series: bool) -> int:
    return int(await _db.fetchval(
        f"SELECT COUNT(*) FROM movies WHERE is_vip = 1 AND type {_vz_op(series)} 'serial'", default=0))


async def _vz_rows(series: bool, offset: int, limit: int) -> list:
    return await _db.fetchall(
        f"SELECT {_SHORT} FROM movies m WHERE m.is_vip = 1 AND m.type {_vz_op(series)} 'serial' "
        "ORDER BY m.id DESC LIMIT ? OFFSET ?", (limit, offset))


@router.callback_query(_Nav.filter(_F.to == "vipzone"))
async def vipzone_menu(callback: _CQ, bot: _Bot, db_user: dict) -> None:
    films = await _vz_count(False)
    series = await _vz_count(True)
    if not _users.is_privileged(db_user):
        sample = await _db.fetchall("SELECT title, year FROM movies WHERE is_vip = 1 ORDER BY RANDOM() LIMIT 3")
        lines = ["👑 <b>VIP bo'lim</b>", "", "🔒 Bu bo'lim faqat VIP obunachilar uchun.", ""]
        if films + series:
            lines.append(f"Bu yerda {films} ta VIP kino va {series} ta serial bor.")
        if sample:
            lines.append("Masalan:")
            for m in sample:
                year = f" ({m['year']})" if m.get("year") else ""
                lines.append(f"• {_esc(m['title'])}{year}")
        lines += ["", "VIP bilan hammasini cheklovsiz ko'rasiz."]
        markup = _kb([[_btn("💎 VIP olish", _Nav(to="vip"))], [_btn("⬅️ Menyu", _Nav(to="menu"))]])
        await _render(bot, callback.from_user.id, callback.message, "\n".join(lines), markup)
        await _answer(callback)
        return
    markup = _kb([
        [_btn(f"🎬 VIP kinolar ({films})", _Pg(k="vzf", p=0)),
         _btn(f"📺 VIP seriallar ({series})", _Pg(k="vzs", p=0))],
        [_btn("🆕 Yangi VIP kinolar", _Pg(k="vzn", p=0))],
        [_btn("⬅️ Menyu", _Nav(to="menu"))],
    ])
    await _render(bot, callback.from_user.id, callback.message,
                  "👑 <b>VIP bo'lim</b>\n\nFaqat VIP obunachilar uchun maxsus kinolar va seriallar.", markup)
    await _answer(callback)


@router.callback_query(_Pg.filter(_F.k.in_({"vzf", "vzs", "vzn"})))
async def vipzone_list(callback: _CQ, callback_data: _Pg, bot: _Bot, db_user: dict) -> None:
    if not _users.is_privileged(db_user):
        await _answer(callback, "Bu bo'lim faqat VIP obunachilar uchun.", alert=True)
        return
    kind = callback_data.k
    if kind == "vzn":
        rows = await _db.fetchall(f"SELECT {_SHORT} FROM movies m WHERE m.is_vip = 1 ORDER BY m.id DESC LIMIT 10")
        text = "👑 <b>Yangi VIP kinolar</b>" + ("" if rows else "\n\nHozircha bo'sh.")
        markup = _list_kb(rows, "vzn", 0, 1)
    else:
        series = kind == "vzs"
        total = await _vz_count(series)
        pages = _pages_of(total, _VZ_PER_PAGE)
        page = min(max(callback_data.p, 0), pages - 1)
        rows = await _vz_rows(series, page * _VZ_PER_PAGE, _VZ_PER_PAGE)
        title = "📺 VIP seriallar" if series else "🎬 VIP kinolar"
        text = f"👑 <b>{title}</b> ({total})" + ("" if rows else "\n\nHozircha bo'sh.")
        markup = _list_kb(rows, kind, page, pages)
    await _render(bot, callback.from_user.id, callback.message, text, markup)
    await _answer(callback)
