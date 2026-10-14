"""Zayavkalarni ushlash (avtomatik qabul qilinmaydi) va obuna tekshiruvi tugmasi."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, Router
from aiogram.types import CallbackQuery, ChatJoinRequest

import texts as t
from database import misc
from keyboards.callbacks import SubCheck
from keyboards.user import subscribe_kb
from services import actions, subscription
from utils.ui import answer, edit_kb, safe_delete

router = Router()

Row = dict[str, Any]


@router.chat_join_request()
async def on_join_request(request: ChatJoinRequest) -> None:
    await misc.add_join_request(request.from_user.id, request.chat.id)


@router.callback_query(SubCheck.filter())
async def check_subscription(callback: CallbackQuery, bot: Bot, db_user: Row) -> None:
    uid = callback.from_user.id
    # bot turidagi elementlar "Tekshirish" bosilganda tasdiqlangan hisoblanadi
    await subscription.confirm_bot_items(uid)
    items = await subscription.missing(bot, uid)
    if items:
        await answer(callback, t.SUB_NOT_YET, alert=True)
        await edit_kb(callback.message, subscribe_kb(items))
        return
    await answer(callback, t.SUB_THANKS)
    if callback.message:
        await safe_delete(bot, uid, callback.message.message_id)
    payload = await misc.pop_pending(uid)
    await actions.run_pending(bot, db_user, uid, payload)
