"""💎 VIP egalari ro'yxati va qo'lda VIP berish."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import users
from handlers.admin.common import RoleFilter, back_panel_kb, cancel_kb
from keyboards.callbacks import Adm
from keyboards.common import NOOP, btn, pages_of
from utils.text import esc
from utils.time import fmt_local, from_db, utcnow
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("admin"))
router.callback_query.filter(RoleFilter("admin"))

PER_PAGE = 10


class VipForm(StatesGroup):
    target = State()
    days = State()


def left_text(until: Any) -> str:
    secs = max(0, int((until - utcnow()).total_seconds()))
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    if days:
        return f"{days} kun {hours} soat"
    if hours:
        return f"{hours} soat {rem // 60} daqiqa"
    return f"{max(1, rem // 60)} daqiqa"


def user_name(row: dict[str, Any]) -> str:
    name = esc(" ".join(x for x in (row.get("first_name"), row.get("last_name")) if x) or "—")
    return name + (f" @{row['username']}" if row.get("username") else "")


async def vips_view(bot: Bot, chat_id: int, page: int = 0, message: object = None) -> None:
    total = await users.count_vip()
    pages = pages_of(total, PER_PAGE)
    page = max(0, min(page, pages - 1))
    rows = await users.list_vip(PER_PAGE, page * PER_PAGE)
    soon = await users.count_vip_expiring(3)
    lines = [t.VIP_LIST_TITLE.format(total=total, soon=soon)]
    if not rows:
        lines.append(t.VIP_LIST_EMPTY)
    for i, r in enumerate(rows, page * PER_PAGE + 1):
        until = from_db(r["vip_until"])
        if until:
            lines.append(f"{i}. <b>{user_name(r)}</b> · <code>{r['id']}</code>\n"
                         f"    ⏳ {left_text(until)} · {fmt_local(until)} gacha")
    buttons = []
    if pages > 1:
        buttons.append([
            btn("⬅️", Adm(a="vips", id=page - 1) if page > 0 else NOOP),
            btn(f"{page + 1}/{pages}", NOOP),
            btn("➡️", Adm(a="vips", id=page + 1) if page < pages - 1 else NOOP),
        ])
    buttons.append([btn(t.ADM_VIP_GIVE, Adm(a="vipg"))])
    await render(bot, chat_id, message, "\n\n".join(lines), back_panel_kb(*buttons))


@router.callback_query(Adm.filter(F.a == "vips"), StateFilter("*"))
async def vips(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await vips_view(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "vipg"), StateFilter("*"))
async def vip_give(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(VipForm.target)
    await render(bot, callback.from_user.id, callback.message, t.VIP_ASK_TARGET, cancel_kb())
    await answer(callback)


@router.message(VipForm.target, F.text)
async def vip_target(message: Message, state: FSMContext) -> None:
    row = await users.find(message.text)
    if not row:
        await message.answer(t.VIP_NOT_FOUND, reply_markup=cancel_kb())
        return
    until = users.vip_until(row)
    status = f"{left_text(until)} ({fmt_local(until)} gacha)" if until else t.VIP_NONE
    await state.update_data(uid=row["id"], name=user_name(row))
    await state.set_state(VipForm.days)
    await message.answer(t.VIP_ASK_DAYS.format(name=user_name(row), status=status), reply_markup=cancel_kb())


@router.message(VipForm.days, F.text)
async def vip_days(message: Message, state: FSMContext, bot: Bot) -> None:
    try:
        days = int(message.text.strip())
    except ValueError:
        days = 0
    if days == 0 or abs(days) > 3650:
        await message.answer(t.VIP_BAD_DAYS, reply_markup=cancel_kb())
        return
    data = await state.get_data()
    await state.clear()
    uid = int(data["uid"])
    until = await users.add_vip_days(uid, days)
    await users.add_event(uid, "vip_admin", {"days": days, "by": message.from_user.id})  # type: ignore[union-attr]
    active = until > utcnow()
    await message.answer(t.VIP_DONE.format(name=data["name"], date=fmt_local(until) if active else t.VIP_NONE))
    if days > 0:
        try:
            await bot.send_message(uid, t.VIP_GIVEN_USER.format(days=days, date=fmt_local(until)))
        except TelegramAPIError:
            pass
    await vips_view(bot, message.chat.id)
