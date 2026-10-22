"""💎 Obuna ekrani va invoice yuborish."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
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
    # kun soni payload ichida: invoice va to'lov orasida tarif o'zgarsa ham to'g'ri hisoblanadi
    return f"vip:{tariff['id']}:{tariff['days']}:{method}"


@router.callback_query(Nav.filter(F.to == "vip"))
async def nav_vip(callback: CallbackQuery, bot: Bot, db_user: Row) -> None:
    text, markup = await vip_view(db_user)
    await render(bot, callback.from_user.id, callback.message, text, markup)
    await answer(callback)


@router.message(Command("vip"))
async def cmd_vip(message: Message, bot: Bot, db_user: Row) -> None:
    text, markup = await vip_view(db_user)
    await render(bot, message.chat.id, None, text, markup)


@router.callback_query(Vip.filter(F.a == "t"))
async def choose_tariff(callback: CallbackQuery, callback_data: Vip, bot: Bot) -> None:
    tariff = await payments.tariff(callback_data.t)
    if not tariff or not tariff["is_active"]:
        await answer(callback, t.TARIFF_GONE, alert=True)
        return
    text = t.TARIFF_CHOSEN.format(days=tariff["days"], price=som(tariff["price_uzs"]))
    if tariff.get("price_stars"):
        text += "\n" + t.TARIFF_STARS.format(stars=tariff["price_stars"])
    await render(bot, callback.from_user.id, callback.message, text,
                 pay_methods_kb(tariff, bool(config.CLICK_PROVIDER_TOKEN)))
    await answer(callback)


@router.callback_query(Vip.filter(F.a.in_({"stars"})))
async def send_invoice(callback: CallbackQuery, callback_data: Vip, bot: Bot) -> None:
    tariff = await payments.tariff(callback_data.t)
    if not tariff or not tariff["is_active"]:
        await answer(callback, t.TARIFF_GONE, alert=True)
        return
    title = t.INVOICE_TITLE.format(days=tariff["days"])
    description = t.INVOICE_DESCRIPTION.format(days=tariff["days"])
    try:
        if callback_data.a == "stars":
            if not tariff.get("price_stars"):
                await answer(callback, t.TARIFF_GONE, alert=True)
                return
            await bot.send_invoice(
                callback.from_user.id, title=title, description=description,
                payload=payload_of(tariff, "stars"), currency="XTR", provider_token="",
                prices=[LabeledPrice(label=title, amount=int(tariff["price_stars"]))],
            )
        else:
            if not config.CLICK_PROVIDER_TOKEN:
                await answer(callback, t.CLICK_DISABLED, alert=True)
                return
            await bot.send_invoice(
                callback.from_user.id, title=title, description=description,
                payload=payload_of(tariff, "click"), currency="UZS",
                provider_token=config.CLICK_PROVIDER_TOKEN,
                prices=[LabeledPrice(label=title, amount=int(tariff["price_uzs"]) * 100)],  # tiyinda
            )
    except TelegramBadRequest as exc:
        log.warning("Invoice yuborilmadi (%s): %s", callback_data.a, exc)
        await answer(callback, t.INVOICE_FAILED, alert=True)
        return
    await answer(callback)
