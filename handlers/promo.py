"""🎁 Promo-kod."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import payments, users
from keyboards.callbacks import Nav
from keyboards.user import back_kb
from utils.time import fmt_date, from_db, utcnow
from utils.ui import answer, render

router = Router()

Row = dict[str, Any]


class PromoForm(StatesGroup):
    code = State()


@router.callback_query(Nav.filter(F.to == "promo"))
async def promo_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(PromoForm.code)
    await render(bot, callback.from_user.id, callback.message, t.PROMO_PROMPT, back_kb())
    await answer(callback)


@router.message(PromoForm.code, F.text)
async def promo_code(message: Message, state: FSMContext, db_user: Row) -> None:
    code = message.text.strip().upper()[:32]
    promo = await payments.promo(code)
    error = None
    if not promo or not promo["is_active"]:
        error = t.PROMO_INVALID
    else:
        expires = from_db(promo["expires_at"])
        if expires and expires < utcnow():
            error = t.PROMO_EXPIRED
        elif promo["used_count"] >= promo["max_uses"]:
            error = t.PROMO_EXHAUSTED
        elif await payments.promo_used(promo["code"], db_user["id"]):
            error = t.PROMO_USED
    if error:
        await message.answer(error, reply_markup=back_kb())
        return
    await state.clear()
    if not await payments.use_promo(promo["code"], db_user["id"]):  # type: ignore[index]
        await message.answer(t.PROMO_EXHAUSTED, reply_markup=back_kb())
        return
    until = await users.add_vip_days(db_user["id"], promo["days"])  # type: ignore[index]
    await users.add_event(db_user["id"], "promo", {"code": promo["code"], "days": promo["days"]})  # type: ignore[index]
    await message.answer(t.PROMO_OK.format(days=promo["days"], date=fmt_date(until)), reply_markup=back_kb())  # type: ignore[index]
