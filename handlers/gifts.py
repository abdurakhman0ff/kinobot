"""🎁 Kino hadya qilib VIP olish: foydalanuvchi tomoni va admin qarori."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import gifts, settings, users
from handlers.admin.add_movie import AddMovie, search_title
from handlers.admin.common import media_file_id
from keyboards.callbacks import Gift, Nav
from keyboards.common import btn, kb
from keyboards.user import back_kb
from services import search
from services.cards import type_label
from services.gifts import store_file
from utils.text import esc, truncate
from utils.time import fmt_date
from utils.ui import answer, edit_kb, render

router = Router()
log = logging.getLogger(__name__)

Row = dict[str, Any]

TYPES = ("film", "serial", "multfilm")
MAX_FILES = 10
_locks: dict[int, asyncio.Lock] = {}


class GiftForm(StatesGroup):
    title = State()
    dup = State()
    files = State()


def _lock(user_id: int) -> asyncio.Lock:
    if len(_locks) > 2000:
        _locks.clear()
    return _locks.setdefault(user_id, asyncio.Lock())


def cancel_row() -> list:
    return [btn(t.BTN_CANCEL, Gift(a="x"))]


async def _limit_text(user_id: int) -> str | None:
    pending_max = settings.get_int("gift_pending_max", 3)
    cap = settings.get_int("gift_month_cap", 7)
    if await gifts.pending_count(user_id) >= pending_max:
        return t.GIFT_PENDING_LIMIT.format(n=pending_max)
    if await gifts.rewarded_days(user_id) >= cap:
        return t.GIFT_CAP.format(cap=cap)
    return None


# ---------- foydalanuvchi ----------

@router.callback_query(Nav.filter(F.to == "gift"))
async def gift_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    uid = callback.from_user.id
    blocked = await _limit_text(uid)
    if blocked:
        await render(bot, uid, callback.message, blocked, back_kb("vip"))
        await answer(callback)
        return
    text = t.GIFT_INTRO.format(days=settings.get_int("gift_vip_days", 1), cap=settings.get_int("gift_month_cap", 7))
    rows = [[btn(type_label(x), Gift(a="t", v=x)) for x in TYPES], [btn(t.BTN_BACK, Nav(to="vip"))]]
    await render(bot, uid, callback.message, text, kb(rows))
    await answer(callback)


@router.callback_query(Gift.filter(F.a == "t"))
async def gift_type(callback: CallbackQuery, callback_data: Gift, state: FSMContext, bot: Bot) -> None:
    kind = callback_data.v if callback_data.v in TYPES else "film"
    await state.clear()
    await state.set_state(GiftForm.title)
    await state.update_data(type=kind, files=[])
    await render(bot, callback.from_user.id, callback.message, t.GIFT_ASK_TITLE, kb([cancel_row()]))
    await answer(callback)


async def _ask_files(bot: Bot, chat_id: int, state: FSMContext, message: object = None) -> None:
    data = await state.get_data()
    await state.set_state(GiftForm.files)
    text = t.GIFT_ASK_FILES.format(type=type_label(data.get("type")), max=MAX_FILES)
    await render(bot, chat_id, message, text, kb([cancel_row()]))


@router.message(GiftForm.title, F.text)
async def gift_title(message: Message, state: FSMContext, bot: Bot) -> None:
    title = truncate(message.text.strip(), 120)
    if len(title) < 2:
        await message.answer(t.GIFT_ASK_TITLE)
        return
    await state.update_data(title=title)
    found = (await search.search(title))[:5]
    if found:
        items = "\n".join(f"• {esc(e.title)}" + (f" ({e.year})" if e.year else "") + f" [{e.code}]" for e in found)
        await state.set_state(GiftForm.dup)
        await message.answer(
            t.GIFT_DUP.format(items=items),
            reply_markup=kb([[btn(t.GIFT_BTN_CONTINUE, Gift(a="go"))], cancel_row()]),
        )
        return
    await _ask_files(bot, message.chat.id, state)


@router.callback_query(GiftForm.dup, Gift.filter(F.a == "go"))
async def gift_continue(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await _ask_files(bot, callback.from_user.id, state, callback.message)
    await answer(callback)


def _send_kb() -> InlineKeyboardMarkup:
    return kb([[btn(t.GIFT_BTN_SEND, Gift(a="send"))], cancel_row()])


@router.message(GiftForm.files)
async def gift_file(message: Message, state: FSMContext) -> None:
    file_id = media_file_id(message)
    if not file_id:
        await message.answer(t.GIFT_NEED_FILE)
        return
    async with _lock(message.from_user.id):  # type: ignore[union-attr]
        data = await state.get_data()
        files = list(data.get("files") or [])
        if len(files) >= MAX_FILES:
            await message.answer(t.GIFT_FILE_MAX.format(max=MAX_FILES), reply_markup=_send_kb())
            return
        files.append({"m": message.message_id, "f": file_id})
        await state.update_data(files=files)
    await message.answer(t.GIFT_FILE_OK.format(n=len(files)), reply_markup=_send_kb())


@router.callback_query(GiftForm.files, Gift.filter(F.a == "send"))
async def gift_send(callback: CallbackQuery, state: FSMContext, bot: Bot, db_user: Row) -> None:
    uid = callback.from_user.id
    data = await state.get_data()
    files = list(data.get("files") or [])
    if not files:
        await answer(callback, t.GIFT_NEED_FILE, alert=True)
        return
    blocked = await _limit_text(uid)
    if blocked:
        await state.clear()
        await render(bot, uid, callback.message, blocked, back_kb("vip"))
        await answer(callback)
        return
    await state.clear()
    gift_id = await gifts.add(uid, data.get("type", "film"), data.get("title", ""), files)
    caption = t.GIFT_ADMIN.format(
        id=gift_id, title=esc(data.get("title", "")), type=type_label(data.get("type")), n=len(files),
        name=esc(db_user.get("first_name") or ""), user_id=uid,
    )
    markup = _decision_kb(gift_id)
    for staff_id in users.staff_ids("moderator"):
        try:
            await bot.copy_message(staff_id, uid, files[0]["m"], caption=caption, reply_markup=markup)
            for extra in files[1:]:
                await bot.copy_message(staff_id, uid, extra["m"])
        except TelegramAPIError as exc:
            log.warning("Hadya xodimga yetmadi (%s): %s", staff_id, exc)
    await render(bot, uid, callback.message, t.GIFT_SENT, back_kb())
    await answer(callback)


@router.callback_query(Gift.filter(F.a == "x"), StateFilter("*"))
async def gift_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await render(bot, callback.from_user.id, callback.message, t.GIFT_CANCELLED, back_kb("vip"))
    await answer(callback)


# ---------- admin qarori ----------

def _decision_kb(gift_id: int) -> InlineKeyboardMarkup:
    return kb([[btn(t.GIFT_BTN_OK, Gift(a="ok", id=gift_id)), btn(t.GIFT_BTN_NO, Gift(a="no", id=gift_id))]])


def _add_kb(gift_id: int) -> InlineKeyboardMarkup:
    return kb([[btn(t.GIFT_BTN_ADD, Gift(a="add", id=gift_id))]])


def _reasons_kb(gift_id: int) -> InlineKeyboardMarkup:
    rows = [[btn(r, Gift(a="nr", id=gift_id, v=str(i)))] for i, r in enumerate(t.GIFT_REASONS)]
    rows.append([btn(t.BTN_BACK, Gift(a="bk", id=gift_id))])
    return kb(rows)


async def _mark(callback: CallbackQuery, status_text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    msg = callback.message
    if not isinstance(msg, Message):
        return
    base = msg.html_text or ""
    try:
        if msg.text is not None:
            await msg.edit_text(f"{base}\n\n{status_text}", reply_markup=markup)
        else:
            await msg.edit_caption(caption=f"{base}\n\n{status_text}", reply_markup=markup)
    except TelegramAPIError:
        pass


async def _open_gift(callback: CallbackQuery, callback_data: Gift) -> Row | None:
    """Xodim va 'new' holatni tekshiradi."""
    if not users.has_role(callback.from_user.id, "moderator"):
        await answer(callback, t.NO_ACCESS, alert=True)
        return None
    gift = await gifts.get(callback_data.id)
    if not gift or gift["status"] != "new":
        await answer(callback, t.GIFT_ALREADY, alert=True)
        await edit_kb(callback.message, None)
        return None
    return gift


@router.callback_query(Gift.filter(F.a == "no"))
async def gift_no(callback: CallbackQuery, callback_data: Gift) -> None:
    gift = await _open_gift(callback, callback_data)
    if gift:
        await edit_kb(callback.message, _reasons_kb(gift["id"]))
        await answer(callback)


@router.callback_query(Gift.filter(F.a == "bk"))
async def gift_back(callback: CallbackQuery, callback_data: Gift) -> None:
    gift = await _open_gift(callback, callback_data)
    if gift:
        await edit_kb(callback.message, _decision_kb(gift["id"]))
        await answer(callback)


@router.callback_query(Gift.filter(F.a == "nr"))
async def gift_reject(callback: CallbackQuery, callback_data: Gift, bot: Bot) -> None:
    gift = await _open_gift(callback, callback_data)
    if not gift:
        return
    idx = int(callback_data.v or 0)
    reason = t.GIFT_REASONS[idx] if 0 <= idx < len(t.GIFT_REASONS) else t.GIFT_REASONS[-1]
    if not await gifts.decide(gift["id"], "rejected", 0, reason):
        await answer(callback, t.GIFT_ALREADY, alert=True)
        return
    await _mark(callback, t.GIFT_ADMIN_NO.format(reason=reason))
    await answer(callback)
    try:
        await bot.send_message(gift["user_id"], t.GIFT_REJECTED_USER.format(title=esc(gift["title"]), reason=reason))
    except TelegramAPIError:
        pass


@router.callback_query(Gift.filter(F.a == "ok"))
async def gift_ok(callback: CallbackQuery, callback_data: Gift, bot: Bot) -> None:
    """Qabul qilish: VIP beriladi, kino esa admin 'Bazaga qo'shish' bosganda qo'shiladi."""
    gift = await _open_gift(callback, callback_data)
    if not gift:
        return
    user_id = int(gift["user_id"])
    days = settings.get_int("gift_vip_days", 1)
    cap = settings.get_int("gift_month_cap", 7)
    reward = max(0, min(days, cap - await gifts.rewarded_days(user_id)))
    if not await gifts.decide(gift["id"], "approved", reward):
        await answer(callback, t.GIFT_ALREADY, alert=True)
        return
    text = t.GIFT_APPROVED_NOREWARD.format(title=esc(gift["title"]))
    if reward > 0:
        until = await users.add_vip_days(user_id, reward)
        await users.add_event(user_id, "gift_vip", {"days": reward, "gift_id": gift["id"]})
        text = t.GIFT_APPROVED_USER.format(title=esc(gift["title"]), days=reward, date=fmt_date(until))
    await _mark(callback, t.GIFT_ADMIN_OK, _add_kb(gift["id"]))
    await answer(callback)
    try:
        await bot.send_message(user_id, text, reply_markup=back_kb())
    except TelegramAPIError:
        pass


@router.callback_query(Gift.filter(F.a == "add"), StateFilter("*"))
async def gift_add(callback: CallbackQuery, callback_data: Gift, state: FSMContext, bot: Bot) -> None:
    """Qabul qilingan hadyani 'Kino qo'shish' jarayoniga o'tkazadi (nom, tur, video oldindan to'ldirilgan)."""
    if not users.has_role(callback.from_user.id, "moderator"):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    gift = await gifts.get(callback_data.id)
    if not gift or gift["status"] != "approved":
        await answer(callback, t.GIFT_ALREADY, alert=True)
        return
    if gift["movie_id"]:
        await answer(callback, t.GIFT_ADDED_ALREADY, alert=True)
        await edit_kb(callback.message, None)
        return
    files = json.loads(gift["files"] or "[]")
    kind = gift["type"]
    await state.clear()
    await state.update_data(type=kind, gift_id=gift["id"])
    if kind != "serial":
        try:
            sid, bid, fid = await store_file(bot, int(gift["user_id"]), files[0])
        except (TelegramAPIError, IndexError) as exc:
            await answer(callback, t.GIFT_ADD_FAILED.format(error=str(exc)[:120]), alert=True)
            return
        await state.update_data(storage_message_id=sid, backup_message_id=bid, file_id=fid)
    await state.set_state(AddMovie.title)
    await answer(callback)
    await search_title(callback.message, gift["title"], state, bot)  # type: ignore[arg-type]
