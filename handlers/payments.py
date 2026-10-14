"""To'lovlar: Telegram Stars (avto) va Karta orqali to'lov (manual chek)."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, PreCheckoutQuery

import config
import texts as t
from database import payments, users
from keyboards.user import back_kb
from services import notify
from utils.text import esc, parse_int
from utils.time import fmt_date

router = Router()
log = logging.getLogger(__name__)

Row = dict[str, Any]


class ManualPaymentState(StatesGroup):
    waiting_for_receipt = State()


def parse_payload(payload: str) -> tuple[int, int, str] | None:
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "vip":
        return None
    tariff_id, days = parse_int(parts[1]), parse_int(parts[2])
    if tariff_id is None or not days or parts[3] not in ("stars", "click"):
        return None
    return tariff_id, days, parts[3]


# ==========================================
# 1. TELEGRAM STARS (AVTO) TO'LOV QISMI
# ==========================================
@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    parsed = parse_payload(query.invoice_payload)
    tariff = await payments.tariff(parsed[0]) if parsed else None
    ok = bool(parsed and tariff and tariff["is_active"])
    if ok and parsed:
        _, _, method = parsed
        if method == "stars":
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


# ==========================================
# 2. KARTA ORQALI QO'LDA (MANUAL) TO'LOV QISMI
# ==========================================
@router.callback_query(F.data.startswith("buy_manual:"))
async def start_manual_payment(callback: CallbackQuery, callback_data: str, state: FSMContext) -> None:
    await callback.answer()
    
    parts = callback_data.split(":")
    tariff_id = int(parts[1]) if len(parts) > 1 else 0
    
    await state.update_data(tariff_id=tariff_id)
    await state.set_state(ManualPaymentState.waiting_for_receipt)
    
    await callback.message.answer(
        "💳 **Karta orqali to'lov rekvizitlari:**\n\n"
        "Karta: `9860350140057646`\n"
        "Karta egasi: A. K\n\n"
        "To'lovni amalga oshirgach, iltimos, **chek (skrinshot) rasmini** shu chatga yuboring."
    )


@router.message(ManualPaymentState.waiting_for_receipt, F.photo)
async def receive_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    photo_id = message.photo[-1].file_id
    user_id = message.from_user.id
    username = message.from_user.username or "Mavjud emas"
    
    data = await state.get_data()
    tariff_id = data.get("tariff_id", 0)
    
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_app:{user_id}:{tariff_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_rej:{user_id}")
        ]
    ])
    
    await bot.send_photo(
        chat_id=config.ADMIN_ID,
        photo=photo_id,
        caption=f"📥 **Yangi to'lov cheki (Karta)!**\n\nFoydalanuvchi: @{username}\nID: `{user_id}`\nTarif ID: `{tariff_id}`",
        reply_markup=admin_kb
    )
    
    await message.answer("✅ Chekingiz adminga yuborildi. Tekshirilib, tez orada VIP obuna faollashtiriladi.", reply_markup=back_kb())
    await state.clear()


@router.callback_query(F.data.startswith("pay_app:"), F.from_user.id == config.ADMIN_ID)
async def approve_manual_payment(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("To'lov tasdiqlandi!")
    
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    tariff_id = int(parts[2]) if len(parts) > 2 else 0
    
    tariff = await payments.tariff(tariff_id) if tariff_id else None
    days = tariff["days"] if tariff else 30
    
    until = await users.add_vip_days(target_user_id, days)
    await users.add_event(target_user_id, "manual_vip_purchase", {"days": days})
    
    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n✅ **Status:** Tasdiqlandi (Admin: @{callback.from_user.username})"
    )
    
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text=t.PAYMENT_OK.format(days=days, date=fmt_date(until)),
            reply_markup=back_kb()
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_rej:"), F.from_user.id == config.ADMIN_ID)
async def reject_manual_payment(callback: CallbackQuery, bot: Bot) -> None:
    await callback.answer("To'lov rad etildi.")
    
    parts = callback.data.split(":")
    target_user_id = int(parts[1])
    
    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n❌ **Status:** Rad etildi"
    )
    
    try:
        await bot.send_message(
            chat_id=target_user_id,
            text="❌ Siz yuborgan to'lov cheki admin tomonidan rad etildi. Savollar bo'lsa qo'llab-quvvatlash xizmatiga murojaat qiling."
        )
    except Exception:
        pass


# ==========================================
# 3. REFUND QISMI (Stars uchun)
# ==========================================
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
