"""💎 Obuna ekrani va invoice yuborish."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LabeledPrice, Message

import config
import texts as t
from database import payments, users
from keyboards.callbacks import Nav, Vip
from keyboards.user import pay_methods_kb, tariffs_kb
from utils.text import som
from utils.time import days_left, fmt_date
from utils.ui import answer, render

router = Router()
log = logging.getLogger(__name__)

Row = dict[str, Any]


async def vip_view(user: Row) -> tuple[str, InlineKeyboardMarkup]:
    tariffs = await payments.tariffs()
    until = users.vip_until(user)
    if until:
        text = t.VIP_ACTIVE.format(days=days_left(until), date=fmt_date(until))
    else:
        text = t.VIP_OFFER
    if not tariffs:
        text += "\n\n" + t.NO_TARIFFS
    return text, tariffs_kb(tariffs)


def payload_of(tariff: Row, method: str) -> str:
    return f"vip:{tariff['id']}:{tariff['days']}:{method}"


@router.callback_query(Nav.filter(F.to == "vip"))
async def nav_vip(callback: CallbackQuery, bot: Bot, db_user: Row) -> None:
    # ⚡ Darhol javob berish
    await answer(callback)
    
    text, markup = await vip_view(db_user)
    await render(bot, callback.from_user.id, callback.message, text, markup)


@router.message(Command("vip"))
async def cmd_vip(message: Message, bot: Bot, db_user: Row) -> None:
    text, markup = await vip_view(db_user)
    await render(bot, message.chat.id, None, text, markup)


@router.callback_query(Vip.filter(F.a == "t"))
async def choose_tariff(callback: CallbackQuery, callback_data: Vip, bot: Bot) -> None:
    # ⚡ Darhol javob berish
    await answer(callback)
    
    tariff = await payments.tariff(callback_data.t)
    if not tariff or not tariff["is_active"]:
        await answer(callback, t.TARIFF_GONE, alert=True)
        return
    text = t.TARIFF_CHOSEN.format(days=tariff["days"], price=som(tariff["price_uzs"]))
    if tariff.get("price_stars"):
        text += "\n" + t.TARIFF_STARS.format(stars=tariff["price_stars"])
    
    # Karta orqali to'lov tugmasi har doim aktiv bo'lishi uchun True uzatamiz
    await render(bot, callback.from_user.id, callback.message, text,
                 pay_methods_kb(tariff, True))


# 1. Telegram Stars orqali avto-to'lov
@router.callback_query(Vip.filter(F.a == "stars"))
async def send_stars_invoice(callback: CallbackQuery, callback_data: Vip, bot: Bot) -> None:
    await answer(callback)
    
    tariff = await payments.tariff(callback_data.t)
    if not tariff or not tariff["is_active"] or not tariff.get("price_stars"):
        await answer(callback, t.TARIFF_GONE, alert=True)
        return
        
    title = t.INVOICE_TITLE.format(days=tariff["days"])
    description = t.INVOICE_DESCRIPTION.format(days=tariff["days"])
    try:
        await bot.send_invoice(
            callback.from_user.id, title=title, description=description,
            payload=payload_of(tariff, "stars"), currency="XTR", provider_token="",
            prices=[LabeledPrice(label=title, amount=int(tariff["price_stars"]))],
        )
    except TelegramBadRequest as exc:
        log.warning("Invoice yuborilmadi (stars): %s", exc)
        await answer(callback, t.INVOICE_FAILED, alert=True)


# 2. Karta orqali qo'lda (manual) to'lov (Click o'rniga rekvizit ko'rsatish)
@router.callback_query(Vip.filter(F.a == "click"))
async def send_manual_card_info(callback: CallbackQuery, callback_data: Vip, state: FSMContext) -> None:
    await answer(callback)
    
    tariff = await payments.tariff(callback_data.t)
    if not tariff or not tariff["is_active"]:
        await answer(callback, t.TARIFF_GONE, alert=True)
        return
        
    # ManualPaymentState import qilmasdan ham payments.py fayliga uzatish uchun state o'rnatamiz
    from handlers.payments import ManualPaymentState
    
    await state.update_data(tariff_id=tariff["id"])
    await state.set_state(ManualPaymentState.waiting_for_receipt)
    
    await callback.message.answer(
        f"💳 **Karta orqali to'lov rekvizitlari:**\n\n"
        f"📌 **Tarif:** {tariff['days']} kunlik VIP obuna\n"
        f"💰 **Summa:** {som(tariff['price_uzs'])}\n\n"
        f"💳 **Karta raqam:** `9860350140057646`\n"
        f"👤 **Karta egasi:** A. K\n\n"
        f"To'lovni amalga oshirgach, iltimos, **chek (skrinshot) rasmini** shu chatga yuboring."
    )
