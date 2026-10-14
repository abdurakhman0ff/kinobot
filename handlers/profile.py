"""👤 Profil, ko'rish tarixi, bildirishnoma sozlamasi."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

import texts as t
from database import movies, users
from keyboards.callbacks import Nav
from keyboards.common import btn, kb, movie_buttons, nav_row
from services import limits
from utils.text import esc
from utils.time import days_left, fmt_date, fmt_duration
from utils.ui import answer, render

router = Router()

Row = dict[str, Any]


async def profile_view(user: Row, role: str | None) -> tuple[str, InlineKeyboardMarkup]:
    until = users.vip_until(user)
    if until:
        vip = t.PROFILE_VIP_ON.format(days=days_left(until), date=fmt_date(until))
        limit_line = t.PROFILE_NO_LIMIT
    else:
        vip = t.PROFILE_VIP_OFF
        if role:
            limit_line = t.PROFILE_NO_LIMIT
        else:
            status = await limits.status(user["id"])
            m_used, m_limit, m_left = status["movie"]
            s_used, s_limit, s_left = status["series"]
            lefts = [x for x in (m_left, s_left) if x > 0]
            reset = t.PROFILE_RESET.format(left=fmt_duration(min(lefts))) if lefts else ""
            limit_line = t.PROFILE_LIMIT.format(m=m_used, ml=m_limit, s=s_used, sl=s_limit, reset=reset)
    notify_on = bool(user.get("notify_new", 1))
    text = t.PROFILE_TEXT.format(
        name=esc(user.get("first_name") or ""), id=user["id"], vip=vip, limit=limit_line,
        notify=t.ON if notify_on else t.OFF,
    )
    markup = kb([
        [btn(t.BTN_NOTIFY.format(state=t.ON if notify_on else t.OFF), Nav(to="notify"))],
        [btn(t.BTN_HISTORY, Nav(to="history")), btn(t.BTN_REQUEST, Nav(to="req"))],
        [btn(t.BTN_VIP, Nav(to="vip"))],
        nav_row(),
    ])
    return text, markup


@router.callback_query(Nav.filter(F.to == "profile"))
async def nav_profile(callback: CallbackQuery, bot: Bot, db_user: Row, role: str | None) -> None:
    text, markup = await profile_view(db_user, role)
    await render(bot, callback.from_user.id, callback.message, text, markup)
    await answer(callback)


@router.callback_query(Nav.filter(F.to == "notify"))
async def toggle_notify(callback: CallbackQuery, bot: Bot, db_user: Row, role: str | None) -> None:
    value = 0 if db_user.get("notify_new", 1) else 1
    await users.set_field(db_user["id"], "notify_new", value)
    db_user["notify_new"] = value
    text, markup = await profile_view(db_user, role)
    await render(bot, callback.from_user.id, callback.message, text, markup)
    await answer(callback, t.NOTIFY_ON if value else t.NOTIFY_OFF)


@router.callback_query(Nav.filter(F.to == "history"))
async def history(callback: CallbackQuery, bot: Bot) -> None:
    rows = await movies.history(callback.from_user.id)
    text = t.HISTORY_TITLE if rows else t.HISTORY_EMPTY
    markup = kb(movie_buttons(rows) + [nav_row(Nav(to="profile"))])
    await render(bot, callback.from_user.id, callback.message, text, markup)
    await answer(callback)
