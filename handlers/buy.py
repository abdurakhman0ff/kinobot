"""Kinoni alohida sotib olish: karta orqali to'lov, chek va admin tasdig'i."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import movies, purchases, settings, users
from database.db import db
from keyboards.callbacks import Buy, Nav, Rnd
from keyboards.common import btn, kb
from keyboards.user import back_kb
from services import delivery
from utils.text import esc, money
from utils.ui import answer

router = Router()
log = logging.getLogger(__name__)

Row = dict[str, Any]


class BuyForm(StatesGroup):
    receipt = State()


@router.callback_query(Buy.filter(F.a == "go"))
async def buy_start(callback: CallbackQuery, callback_data: Buy, state: FSMContext, bot: Bot) -> None:
    movie = await movies.get(callback_data.id)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    price = int(movie.get("price") or 0)
    if price <= 0:
        await answer(callback, t.BM_FREE_NOW, alert=True)
        return
    if await purchases.owned(callback.from_user.id, movie["id"]):
        await answer(callback, t.BM_OWNED, alert=True)
        return
    card = settings.get("card_number")
    if not card:
        await answer(callback, t.BM_NO_CARD, alert=True)
        return
    await state.set_state(BuyForm.receipt)
    await state.update_data(movie_id=movie["id"])
    text = t.BM_CARD.format(title=esc(movie["title"]), card=esc(card),
                            owner=esc(settings.get("card_owner") or "—"), price=money(price))
    await bot.send_message(callback.from_user.id, text, reply_markup=kb([[btn(t.BM_BTN_BACK, Buy(a="x"))]]))
    await answer(callback)


@router.callback_query(Buy.filter(F.a == "x"), StateFilter("*"))
async def buy_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    try:
        await callback.message.delete()  # type: ignore[union-attr]
    except Exception:
        await bot.send_message(callback.from_user.id, t.BM_CANCELLED, reply_markup=back_kb())
    await answer(callback)


@router.message(BuyForm.receipt, F.photo | F.document)
async def buy_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    movie = await movies.get(int(data.get("movie_id", 0)))
    price = int((movie or {}).get("price") or 0)
    if not movie or price <= 0:
        await state.clear()
        await message.answer(t.MOVIE_GONE)
        return
    user = message.from_user
    if await purchases.pending_count(user.id) >= 3:  # type: ignore[union-attr]
        await message.answer(t.BM_TOO_MANY)
        return
    pid = await purchases.add(user.id, movie["id"], price)  # type: ignore[union-attr]
    caption = t.BM_ADMIN_CAPTION.format(name=esc(user.full_name), uid=user.id, title=esc(movie["title"]),  # type: ignore[union-attr]
                                        code=movie["code"], price=money(price), pid=pid)
    markup = kb([[btn(t.BM_BTN_OK, Buy(a="ok", id=pid)), btn(t.BM_BTN_NO, Buy(a="no", id=pid))]])
    sent = 0
    for admin_id in users.staff_ids("admin"):
        try:
            await message.copy_to(admin_id, caption=caption, reply_markup=markup)
            sent += 1
        except TelegramAPIError as exc:
            log.warning("Chek adminga yetmadi (%s): %s", admin_id, exc)
    if not sent:
        await purchases.decide(pid, "failed")
        await message.answer(t.INVOICE_FAILED)
        return
    await state.clear()
    await message.answer(t.BM_SENT, reply_markup=back_kb())


@router.message(BuyForm.receipt, F.text, ~F.text.startswith("/"))
async def buy_need_photo(message: Message) -> None:
    await message.answer(t.BM_NEED_PHOTO)


async def _mark(callback: CallbackQuery, status_text: str) -> None:
    msg = callback.message
    if not isinstance(msg, Message):
        return
    try:
        await msg.edit_caption(caption=f"{msg.html_text or ''}\n\n{status_text}", reply_markup=None)
    except TelegramAPIError:
        pass


@router.callback_query(Buy.filter(F.a.in_({"ok", "no"})))
async def buy_decide(callback: CallbackQuery, callback_data: Buy, bot: Bot) -> None:
    if not users.has_role(callback.from_user.id, "admin"):
        await answer(callback, "⛔", alert=True)
        return
    p = await purchases.get(callback_data.id)
    if not p or p["status"] != "pending":
        await answer(callback, t.BM_ALREADY, alert=True)
        await _mark(callback, t.BM_ALREADY)
        return
    approve = callback_data.a == "ok"
    if not await purchases.decide(p["id"], "paid" if approve else "rejected"):
        await answer(callback, t.BM_ALREADY, alert=True)
        return
    admin = esc(callback.from_user.full_name)
    await _mark(callback, (t.BM_ADMIN_OK if approve else t.BM_ADMIN_NO).format(admin=admin))
    await answer(callback)
    uid = int(p["user_id"])
    movie = await movies.get(int(p["movie_id"]))
    try:
        if not approve:
            await bot.send_message(uid, t.BM_REJECTED_USER, reply_markup=back_kb())
            return
        await users.add_event(uid, "movie_purchase", {"movie_id": p["movie_id"], "amount": p["price"]})
        await bot.send_message(uid, t.BM_APPROVED_USER.format(title=esc(movie["title"] if movie else "")))
        if movie:
            row = await db.fetchone("SELECT * FROM users WHERE id = ?", (uid,))
            if row:
                await delivery.open_movie(bot, row, uid, movie, checked=True)
    except TelegramAPIError:
        pass


@router.callback_query(Rnd.filter(F.a == "free5"))
async def free_top5(callback: CallbackQuery, callback_data: Rnd, bot: Bot) -> None:
    from keyboards.callbacks import Op
    from utils.ui import render as _render

    try:
        _, top_rows = await movies.top("a", 0, 40)
        ids = [r["id"] for r in top_rows]
    except Exception:
        ids = []
    marks = ",".join("?" * len(ids))
    rows_db = await db.fetchall(f"SELECT * FROM movies WHERE id IN ({marks})", tuple(ids)) if ids else []
    full = {m["id"]: m for m in rows_db}
    ordered = [full[i] for i in ids if i in full]
    if len(ordered) < 5:
        have = {m["id"] for m in ordered}
        ordered += [m for m in await movies.newest(40) if m["id"] not in have]
    free = [m for m in ordered if not int(m.get("price") or 0) and not m.get("is_vip")][:5]

    rows = []
    for m in free:
        label = m["title"] + (f" ({m['year']})" if m.get("year") else "")
        rows.append([btn(label[:60], Op(id=m["id"]))])
    back = Op(id=callback_data.id) if callback_data.id else Nav(to="menu")
    rows.append([btn(t.BM_BTN_BACK, back)])
    await _render(bot, callback.from_user.id, callback.message,
                  t.BM_FREE_TITLE if free else t.BM_FREE_EMPTY, kb(rows))
    await answer(callback)
