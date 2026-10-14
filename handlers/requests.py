"""📝 Kino so'rash (foydalanuvchi) va so'rovni yopish (admin/moderator)."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import misc, movies, users
from keyboards.callbacks import Nav, Req
from keyboards.common import btn, kb
from keyboards.user import back_kb, watch_url_kb
from services import actions, delivery, notify
from utils.text import esc, parse_int, truncate
from utils.ui import answer, render

router = Router()

Row = dict[str, Any]

DAILY_LIMIT = 3
TEXT_MAX = 300


class RequestForm(StatesGroup):
    text = State()


class RequestDone(StatesGroup):
    code = State()


def admin_request_kb(request_id: int) -> InlineKeyboardMarkup:
    return kb([[btn(t.BTN_REQ_DONE, Req(a="ok", id=request_id)), btn(t.BTN_REQ_REJECT, Req(a="no", id=request_id))]])


def request_admin_text(request: Row, user: Row | None) -> str:
    name = esc((user or {}).get("first_name") or "")
    username = f" @{user['username']}" if user and user.get("username") else ""
    return t.ADMIN_NEW_REQUEST.format(id=request["id"], text=esc(request["text"]), name=name,
                                      username=username, user_id=request["user_id"])


async def _submit(bot: Bot, user: Row, text: str) -> str:
    if await misc.requests_today(user["id"]) >= DAILY_LIMIT:
        return t.REQUEST_LIMIT.format(n=DAILY_LIMIT)
    request_id = await misc.add_request(user["id"], truncate(text, TEXT_MAX))
    request = await misc.get_request(request_id)
    await notify.staff(bot, request_admin_text(request, user), kb=admin_request_kb(request_id))  # type: ignore[arg-type]
    return t.REQUEST_SENT


@router.callback_query(Nav.filter(F.to == "req"))
async def request_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(RequestForm.text)
    await render(bot, callback.from_user.id, callback.message, t.REQUEST_PROMPT.format(max=TEXT_MAX), back_kb())
    await answer(callback)


@router.message(RequestForm.text, F.text)
async def request_text(message: Message, state: FSMContext, bot: Bot, db_user: Row) -> None:
    text = message.text.strip()
    if len(text) > TEXT_MAX:
        await message.answer(t.REQUEST_TOO_LONG.format(max=TEXT_MAX))
        return
    await state.clear()
    await message.answer(await _submit(bot, db_user, text), reply_markup=back_kb())


@router.callback_query(Req.filter(F.a == "pf"))
async def request_prefilled(callback: CallbackQuery, state: FSMContext, bot: Bot, db_user: Row) -> None:
    text = actions.prefill.pop(db_user["id"], None)
    if not text:
        await request_start(callback, state, bot)
        return
    await render(bot, callback.from_user.id, callback.message, await _submit(bot, db_user, text), back_kb())
    await answer(callback)


# ---------- admin tomoni ----------

async def _notify_requester(bot: Bot, request: Row, code: int | None) -> None:
    try:
        if code is not None:
            await bot.send_message(
                request["user_id"], t.REQUEST_DONE_USER.format(text=esc(request["text"])),
                reply_markup=watch_url_kb(await delivery.bot_username(bot), code),
            )
        else:
            await bot.send_message(request["user_id"], t.REQUEST_DONE_USER.format(text=esc(request["text"])))
    except TelegramAPIError:
        pass


@router.callback_query(Req.filter(F.a.in_({"ok", "no", "skip"})))
async def request_admin(callback: CallbackQuery, callback_data: Req, state: FSMContext, bot: Bot) -> None:
    if not users.has_role(callback.from_user.id, "moderator"):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    request = await misc.get_request(callback_data.id)
    if not request or (request["status"] != "new" and callback_data.a != "skip"):
        await answer(callback, t.REQUEST_ALREADY, alert=True)
        return
    if callback_data.a == "no":
        await misc.set_request_status(request["id"], "rejected")
        try:
            await bot.send_message(request["user_id"], t.REQUEST_REJECTED_USER.format(text=esc(request["text"])))
        except TelegramAPIError:
            pass
        await render(bot, callback.from_user.id, callback.message,
                     t.ADMIN_REQUEST_CLOSED.format(id=request["id"], status=t.REQ_STATUS_REJECTED))
    elif callback_data.a == "ok":
        await state.set_state(RequestDone.code)
        await state.update_data(request_id=request["id"])
        await callback.message.answer(  # type: ignore[union-attr]
            t.ADMIN_REQUEST_CODE.format(id=request["id"]),
            reply_markup=kb([[btn(t.BTN_SKIP, Req(a="skip", id=request["id"]))]]),
        )
    else:
        await state.clear()
        await misc.set_request_status(request["id"], "done")
        await _notify_requester(bot, request, None)
        await render(bot, callback.from_user.id, callback.message,
                     t.ADMIN_REQUEST_CLOSED.format(id=request["id"], status=t.REQ_STATUS_DONE))
    await answer(callback)


@router.message(RequestDone.code, F.text)
async def request_code(message: Message, state: FSMContext, bot: Bot) -> None:
    code = parse_int(message.text)
    if code is None or not await movies.by_code(code):
        await message.answer(t.ADMIN_CODE_NOT_FOUND)
        return
    data = await state.get_data()
    await state.clear()
    request = await misc.get_request(int(data.get("request_id", 0)))
    if not request:
        await message.answer(t.REQUEST_ALREADY)
        return
    await misc.set_request_status(request["id"], "done", code)
    await _notify_requester(bot, request, code)
    await message.answer(t.ADMIN_REQUEST_CLOSED.format(id=request["id"], status=t.REQ_STATUS_DONE))
