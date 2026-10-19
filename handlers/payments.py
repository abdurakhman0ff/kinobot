"""To'lovlar: pre_checkout, successful_payment, /refund."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, PreCheckoutQuery

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


def parse_payload(payload: str) -> tuple[int, int, str] | None:
    parts = payload.split(":")
    if len(parts) != 4 or parts[0] != "vip":
        return None
    tariff_id, days = parse_int(parts[1]), parse_int(parts[2])
    if tariff_id is None or not days or parts[3] not in ("stars", "click"):
        return None
    return tariff_id, days, parts[3]


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    parsed = parse_payload(query.invoice_payload)
    tariff = await payments.tariff(parsed[0]) if parsed else None
    ok = bool(parsed and tariff and tariff["is_active"])
    if ok and parsed:
        _, _, method = parsed
        if method == "stars":
            ok = query.currency == "XTR" and query.total_amount == tariff["price_stars"]  # type: ignore[index]
        else:
            ok = query.currency == "UZS" and query.total_amount == int(tariff["price_uzs"]) * 100  # type: ignore[index]
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
