"""To'lovlar: Telegram Stars (avto) va karta orqali qo'lda to'lov (chek + admin tasdig'i)."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

import config
import texts as t
from database import payments, settings, users
from database.db import db
from keyboards.callbacks import Pay, Vip
from keyboards.common import btn, kb
from keyboards.user import back_kb
from services import notify
from utils.text import esc, parse_int, som
from utils.time import fmt_date
from utils.ui import answer, render

router = Router()
log = logging.getLogger(__name__)

Row = dict[str, Any]


class ManualPay(StatesGroup):
    receipt = State()


def parse_payload(payload: str) -> tuple[int, int, str] | None:
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "vip":
        return None
    tariff_id, days = parse_int(parts[1]), parse_int(parts[2])
    if tariff_id is None or not days or parts[3] not in ("stars", "click"):
        return None
    return tariff_id, days, parts[3]


# ================= 1. TELEGRAM STARS (avtomatik) =================

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    parsed = parse_payload(query.invoice_payload)
    tariff = await payments.tariff(parsed[0]) if parsed else None
    # faqat Stars: Click avtomatik to'lovi o'chirilgan
    ok = bool(parsed and tariff and tariff["is_active"] and parsed[2] == "stars")
    if ok:
        ok = query.currency == "XTR" and query.total_amount == tariff["price_stars"]  # type: ignore[index]
    await query.answer(ok=ok, error_message=None if ok else t.PRECHECKOUT_FAILED)


@router.message(F.successful_payment)
async def successful_payment(message: Message, bot: Bot) -> None:
    sp = message.successful_payment
    user_id = message.from_user.id  # type: ignore[union-attr]
    parsed = parse_payload(sp.invoice_payload)  # type: ignore[union-attr]
    if not parsed:
        log.error("Noma'lum to'lov payload: %s", sp.invoice_payload)  # type: ignore[union-attr]
        await notify.owner(bot, t.ADMIN_BAD_PAYMENT.format(user_id=user_id, charge=sp.telegram_payment_charge_id))  # type: ignore[union-attr]
        return
    tariff_id, days, method = parsed
    charge = sp.telegram_payment_charge_id  # type: ignore[union-attr]
    if await payments.payment_exists(charge):
        return
    amount = sp.total_amount if sp.currency == "XTR" else sp.total_amount // 100  # type: ignore[union-attr]
    payment_id = await payments.add_payment(
        user_id=user_id, tariff_id=tariff_id, method=method, amount=amount, currency=sp.currency,  # type: ignore[union-attr]
        days=days, payload=sp.invoice_payload, telegram_charge_id=charge,  # type: ignore[union-attr]
        provider_charge_id=sp.provider_payment_charge_id, status="paid",  # type: ignore[union-attr]
    )
    if payment_id is None:
        return
    until = await users.add_vip_days(user_id, days)
    await users.add_event(user_id, "vip_purchase", {"days": days, "method": method, "amount": amount})
    await message.answer(t.PAYMENT_OK.format(days=days, date=fmt_date(until)), reply_markup=back_kb())
    unit = "⭐" if sp.currency == "XTR" else "so'm"  # type: ignore[union-attr]
    name = esc(message.from_user.full_name)  # type: ignore[union-attr]
    await notify.owner(bot, t.ADMIN_NEW_PAYMENT.format(
        name=name, user_id=user_id, days=days, amount=amount, unit=unit, method=method, charge=charge,
    ))


# ================= 2. KARTA ORQALI QO'LDA TO'LOV =================

@router.callback_query(Vip.filter(F.a == "card"))
async def card_start(callback: CallbackQuery, callback_data: Vip, state: FSMContext, bot: Bot) -> None:
    tariff = await payments.tariff(callback_data.t)
    if not tariff or not tariff["is_active"]:
        await answer(callback, t.TARIFF_GONE, alert=True)
        return
    card = settings.get("card_number")
    if not card:
        await answer(callback, t.CARD_OFF, alert=True)
        return
    owner = settings.get("card_owner") or "—"
    await state.set_state(ManualPay.receipt)
    await state.update_data(tariff_id=tariff["id"])
    text = t.CARD_INFO.format(days=tariff["days"], price=som(tariff["price_uzs"]),
                              card=esc(card), owner=esc(owner))
    await render(bot, callback.from_user.id, callback.message, text, kb([[btn(t.BTN_CANCEL, Pay(a="x"))]]))
    await answer(callback)


@router.callback_query(Pay.filter(F.a == "x"), StateFilter("*"))
async def card_cancel(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await render(bot, callback.from_user.id, callback.message, t.CARD_CANCELLED, back_kb())
    await answer(callback)


@router.message(ManualPay.receipt, F.photo | F.document)
async def card_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    tariff = await payments.tariff(int(data.get("tariff_id", 0)))
    if not tariff or not tariff["is_active"]:
        await state.clear()
        await message.answer(t.TARIFF_GONE)
        return
    user = message.from_user
    pending = await db.fetchval(
        "SELECT COUNT(*) FROM payments WHERE user_id = ? AND method = 'card' AND status = 'pending'", (user.id,))  # type: ignore[union-attr]
    if int(pending or 0) >= 3:
        await message.answer(t.CARD_TOO_MANY)
        return
    amount = int(tariff["price_uzs"])
    pid = await payments.add_payment(
        user_id=user.id, tariff_id=tariff["id"], method="card", amount=amount, currency="UZS",  # type: ignore[union-attr]
        days=int(tariff["days"]), payload=f"vip:{tariff['id']}:{tariff['days']}:card",
        telegram_charge_id=f"card:{user.id}:{message.message_id}",  # type: ignore[union-attr]
        provider_charge_id="manual", status="pending",
    )
    if pid is None:
        await message.answer(t.INVOICE_FAILED)
        return
    caption = t.CARD_ADMIN_CAPTION.format(
        name=esc(user.full_name), user_id=user.id, days=tariff["days"], amount=som(amount), pid=pid)  # type: ignore[union-attr]
    markup = kb([[btn(t.CARD_BTN_OK, Pay(a="ok", id=pid)), btn(t.CARD_BTN_NO, Pay(a="no", id=pid))]])
    sent = 0
    for admin_id in users.staff_ids("admin"):
        try:
            await message.copy_to(admin_id, caption=caption, reply_markup=markup)
            sent += 1
        except TelegramAPIError as exc:
            log.warning("Chek adminga yetmadi (%s): %s", admin_id, exc)
    if not sent:
        await payments.set_payment_status(pid, "failed")
        await message.answer(t.INVOICE_FAILED)
        return
    await state.clear()
    await message.answer(t.CARD_SENT, reply_markup=back_kb())


@router.message(ManualPay.receipt, F.text, ~F.text.startswith("/"))
async def card_need_photo(message: Message) -> None:
    await message.answer(t.CARD_NEED_PHOTO)


async def _mark(callback: CallbackQuery, status_text: str) -> None:
    msg = callback.message
    if not isinstance(msg, Message):
        return
    base = msg.html_text or ""
    try:
        await msg.edit_caption(caption=f"{base}\n\n{status_text}", reply_markup=None)
    except TelegramAPIError:
        pass


@router.callback_query(Pay.filter(F.a.in_({"ok", "no"})))
async def card_decide(callback: CallbackQuery, callback_data: Pay, bot: Bot) -> None:
    if not users.has_role(callback.from_user.id, "admin"):
        await answer(callback, "⛔", alert=True)
        return
    p = await db.fetchone("SELECT * FROM payments WHERE id = ?", (callback_data.id,))
    if not p or p["method"] != "card" or p["status"] != "pending":
        await answer(callback, t.CARD_ALREADY, alert=True)
        await _mark(callback, t.CARD_ALREADY)
        return
    admin = esc(callback.from_user.full_name)
    user_id = int(p["user_id"])
    if callback_data.a == "ok":
        await payments.set_payment_status(p["id"], "paid")
        days = int(p["days"] or 0)
        until = await users.add_vip_days(user_id, days)
        await users.add_event(user_id, "vip_purchase", {"days": days, "method": "card", "amount": p["amount"]})
        text = t.PAYMENT_OK.format(days=days, date=fmt_date(until))
        status = t.CARD_ADMIN_OK.format(admin=admin)
    else:
        await payments.set_payment_status(p["id"], "rejected")
        text = t.CARD_REJECTED_USER
        status = t.CARD_ADMIN_NO.format(admin=admin)
    await _mark(callback, status)
    await answer(callback)
    try:
        await bot.send_message(user_id, text, reply_markup=back_kb())
    except TelegramAPIError:
        pass


# ================= 3. REFUND (Stars uchun) =================

@router.message(Command("refund"), F.from_user.id == config.ADMIN_ID)
async def cmd_refund(message: Message, command: CommandObject, bot: Bot) -> None:
    args = (command.args or "").split()
    user_id = parse_int(args[0]) if args else None
    if user_id is None or len(args) != 2:
        await message.answer(t.REFUND_USAGE)
        return
    charge = args[1]
    payment = await payments.payment_by_charge(user_id, charge)
    if not payment or payment["method"] != "stars":
        await message.answer(t.REFUND_NOT_FOUND)
        return
    if payment["status"] == "refunded":
        await message.answer(t.REFUND_ALREADY)
        return
    try:
        await bot.refund_star_payment(user_id, charge)
    except TelegramAPIError as exc:
        await message.answer(t.REFUND_FAILED.format(error=esc(str(exc))))
        return
    await payments.set_payment_status(payment["id"], "refunded")
    until = await users.add_vip_days(user_id, -int(payment["days"] or 0))
    await users.add_event(user_id, "refund", {"payment_id": payment["id"]})
    await message.answer(t.REFUND_OK.format(user_id=user_id, days=payment["days"], date=fmt_date(until)))
    try:
        await bot.send_message(user_id, t.REFUND_USER)
    except TelegramAPIError:
        pass
