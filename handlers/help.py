"""🆘 Yordam, /paysupport."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import settings
from keyboards.callbacks import Nav
from keyboards.common import btn, kb, nav_row
from services import limits
from utils.ui import answer, render

router = Router()


def support_line() -> str:
    username = settings.get("support_username").lstrip("@")
    return f"@{username}" if username else t.SUPPORT_NOT_SET


def paysupport_text() -> str:
    return t.PAYSUPPORT.format(support=support_line())


def help_view() -> tuple[str, InlineKeyboardMarkup]:
    rows = []
    channel = settings.get("public_channel_url")
    if channel:
        rows.append([btn(t.BTN_CHANNEL, url=channel)])
    support = settings.get("support_username").lstrip("@")
    if support:
        rows.append([btn(t.BTN_CONTACT_ADMIN, url=f"https://t.me/{support}")])
    rows += [
        [btn(t.BTN_HOWTO, Nav(to="howto"))],
        [btn(t.BTN_PAYHELP, Nav(to="paysup"))],
        nav_row(),
    ]
    return t.HELP_TEXT, kb(rows)


def howto_text() -> str:
    return t.HOWTO.format(movie=limits.limit_of("movie"), series=limits.limit_of("series"),
                          hours=limits.window_hours())


@router.callback_query(Nav.filter(F.to.in_({"help", "howto", "paysup"})))
async def nav_help(callback: CallbackQuery, callback_data: Nav, bot: Bot) -> None:
    if callback_data.to == "help":
        text, markup = help_view()
    elif callback_data.to == "howto":
        text, markup = howto_text(), kb([nav_row(Nav(to="help"))])
    else:
        text, markup = paysupport_text(), kb([nav_row(Nav(to="help"))])
    await render(bot, callback.from_user.id, callback.message, text, markup)
    await answer(callback)


@router.message(Command("paysupport"))
async def cmd_paysupport(message: Message) -> None:
    await message.answer(paysupport_text())
