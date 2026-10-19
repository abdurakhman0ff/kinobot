"""⚙️ Admin panel: kirish, bekor qilish."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import texts as t
from handlers.admin.common import RoleFilter, panel_kb
from keyboards.callbacks import Adm, Nav
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("moderator"))
router.callback_query.filter(RoleFilter("moderator"))


def panel_text(role: str | None) -> str:
    return t.ADMIN_PANEL.format(role=t.ROLE_NAMES.get(role or "", ""))


@router.message(Command("admin"), StateFilter("*"))
async def cmd_admin(message: Message, state: FSMContext, role: str | None) -> None:
    await state.clear()
    await message.answer(panel_text(role), reply_markup=panel_kb(message.from_user.id))  # type: ignore[union-attr]


@router.callback_query(Nav.filter(F.to == "admin"), StateFilter("*"))
@router.callback_query(Adm.filter(F.a.in_({"p", "x"})), StateFilter("*"))
async def show_panel(callback: CallbackQuery, state: FSMContext, bot: Bot, role: str | None) -> None:
    cancelled = await state.get_state() is not None
    await state.clear()
    await render(bot, callback.from_user.id, callback.message, panel_text(role), panel_kb(callback.from_user.id))
    await answer(callback, t.CANCELLED if cancelled else None)
