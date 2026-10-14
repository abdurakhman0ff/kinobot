"""📢 Xabar yuborish: segment -> kontent -> tugma -> preview -> fon vazifasi."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

import texts as t
from database import users
from handlers.admin.common import RoleFilter, back_panel_kb, cancel_kb
from keyboards.callbacks import Adm
from keyboards.common import btn, chunk, kb
from services import broadcast
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("admin"))
router.callback_query.filter(RoleFilter("admin"))

SEGMENT_NAMES = {
    "all": t.SEG_ALL, "vip": t.SEG_VIP, "regular": t.SEG_REGULAR,
    "expired": t.SEG_EXPIRED, "active": t.SEG_ACTIVE, "inactive": t.SEG_INACTIVE,
}


class Bc(StatesGroup):
    content = State()
    button = State()
    confirm = State()


def button_markup(text: str | None, url: str | None) -> InlineKeyboardMarkup | None:
    return kb([[btn(text, url=url)]]) if text and url else None


@router.callback_query(Adm.filter(F.a == "bc"), StateFilter("*"))
async def bc_start(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    buttons = [btn(name, Adm(a="bs", v=key)) for key, name in SEGMENT_NAMES.items()]
    await render(bot, callback.from_user.id, callback.message, t.BC_SEGMENT, back_panel_kb(*chunk(buttons, 2)))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "bs"))
async def bc_segment(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v not in SEGMENT_NAMES:
        await answer(callback)
        return
    count = len(await users.segment_ids(callback_data.v))
    await state.set_state(Bc.content)
    await state.update_data(segment=callback_data.v)
    await render(bot, callback.from_user.id, callback.message,
                 t.BC_SEND_CONTENT.format(segment=SEGMENT_NAMES[callback_data.v], n=count), cancel_kb())
    await answer(callback)


@router.message(Bc.content)
async def bc_content(message: Message, state: FSMContext) -> None:
    if not (message.text or message.photo or message.video or message.animation or message.document):
        await message.answer(t.BC_BAD_CONTENT)
        return
    await state.update_data(from_chat=message.chat.id, message_id=message.message_id)
    await message.answer(t.BC_ASK_BUTTON, reply_markup=cancel_kb(
        [btn(t.BTN_ADD_BUTTON, Adm(a="bb")), btn(t.BTN_NO_BUTTON, Adm(a="bn"))]
    ))


@router.callback_query(Bc.content, Adm.filter(F.a == "bb"))
async def bc_ask_button(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(Bc.button)
    await render(bot, callback.from_user.id, callback.message, t.BC_BUTTON_FORMAT, cancel_kb())
    await answer(callback)


async def _preview(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(Bc.confirm)
    markup = button_markup(data.get("btn_text"), data.get("btn_url"))
    try:
        await bot.copy_message(chat_id, data["from_chat"], data["message_id"], reply_markup=markup)
    except TelegramBadRequest as exc:
        await bot.send_message(chat_id, t.BC_PREVIEW_FAILED.format(error=str(exc)[:200]), reply_markup=cancel_kb())
        return
    count = len(await users.segment_ids(data["segment"]))
    await bot.send_message(chat_id, t.BC_CONFIRM.format(segment=SEGMENT_NAMES[data["segment"]], n=count),
                           reply_markup=cancel_kb([btn(t.BTN_SEND, Adm(a="bgo"))]))


@router.callback_query(Bc.content, Adm.filter(F.a == "bn"))
async def bc_no_button(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.update_data(btn_text=None, btn_url=None)
    await answer(callback)
    await _preview(bot, callback.from_user.id, state)


@router.message(Bc.button, F.text)
async def bc_button(message: Message, state: FSMContext, bot: Bot) -> None:
    parts = [p.strip() for p in message.text.split("|", 1)]
    if len(parts) != 2 or not parts[0] or not parts[1].startswith(("http://", "https://", "tg://")):
        await message.answer(t.BC_BUTTON_FORMAT)
        return
    await state.update_data(btn_text=parts[0][:60], btn_url=parts[1])
    await _preview(bot, message.chat.id, state)


@router.callback_query(Bc.confirm, Adm.filter(F.a == "bgo"))
async def bc_go(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    ids = await users.segment_ids(data["segment"])
    markup = button_markup(data.get("btn_text"), data.get("btn_url"))
    from_chat, message_id = data["from_chat"], data["message_id"]

    async def send(user_id: int) -> None:
        await bot.copy_message(user_id, from_chat, message_id, reply_markup=markup)

    job = broadcast.Job(title=t.JOB_BROADCAST.format(segment=SEGMENT_NAMES[data["segment"]]), user_ids=ids,
                        send=send, report_chat=callback.from_user.id)
    ahead = await broadcast.enqueue(bot, job)
    await render(bot, callback.from_user.id, callback.message,
                 t.BC_STARTED + (t.QUEUE_AHEAD.format(n=ahead) if ahead else ""), back_panel_kb())
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "bstop"), StateFilter("*"))
async def bc_stop(callback: CallbackQuery, callback_data: Adm) -> None:
    await answer(callback, t.BC_STOPPING if broadcast.stop(callback_data.id) else t.BC_NOT_RUNNING, alert=True)
