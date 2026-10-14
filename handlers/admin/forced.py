"""🔗 Majburiy obuna elementlari (faqat asosiy admin)."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import misc
from handlers.admin.common import RoleFilter, back_panel_kb, cancel_kb
from keyboards.callbacks import Adm
from keyboards.common import btn
from utils.text import esc
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("owner"))
router.callback_query.filter(RoleFilter("owner"))

TYPE_NAMES = {"channel": t.FORCED_CHANNEL, "group": t.FORCED_GROUP, "bot": t.FORCED_BOT}


class ForcedForm(StatesGroup):
    title = State()
    chat = State()
    link = State()


async def forced_view(bot: Bot, chat_id: int, message: object = None) -> None:
    items = await misc.forced_items(active_only=False)
    lines = [t.FORCED_TITLE] if items else [t.FORCED_EMPTY]
    buttons = []
    for i in items:
        status = "✅" if i["is_active"] else "⛔"
        target = i.get("chat_id") or ("@" + i["username"] if i.get("username") else "—")
        lines.append(f"{status} {TYPE_NAMES.get(i['type'], i['type'])}: {esc(i['title'])} · <code>{target}</code>")
        buttons.append([
            btn(("⛔ " if i["is_active"] else "✅ ") + i["title"][:25], Adm(a="frt", id=i["id"])),
            btn("🗑", Adm(a="frx", id=i["id"])),
        ])
    buttons.insert(0, [btn(t.BTN_FORCED_ADD, Adm(a="fra"))])
    await render(bot, chat_id, message, "\n".join(lines), back_panel_kb(*buttons))


@router.callback_query(Adm.filter(F.a == "frc"), StateFilter("*"))
async def forced_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await forced_view(bot, callback.from_user.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "frt"))
async def forced_toggle(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await misc.toggle_forced_item(callback_data.id)
    await forced_view(bot, callback.from_user.id, callback.message)
    await answer(callback, t.SAVED_OK)


@router.callback_query(Adm.filter(F.a == "frx"))
async def forced_delete(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await misc.delete_forced_item(callback_data.id)
    await forced_view(bot, callback.from_user.id, callback.message)
    await answer(callback, t.DELETED)


@router.callback_query(Adm.filter(F.a == "fra"))
async def forced_add(callback: CallbackQuery, bot: Bot) -> None:
    buttons = [btn(name, Adm(a="frty", v=key)) for key, name in TYPE_NAMES.items()]
    await render(bot, callback.from_user.id, callback.message, t.FORCED_CHOOSE_TYPE, cancel_kb(buttons))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "frty"))
async def forced_type(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.set_state(ForcedForm.title)
    await state.update_data(type=callback_data.v if callback_data.v in TYPE_NAMES else "channel")
    await render(bot, callback.from_user.id, callback.message, t.FORCED_ASK_TITLE, cancel_kb())
    await answer(callback)


@router.message(ForcedForm.title, F.text)
async def forced_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text.strip()[:60])
    data = await state.get_data()
    await state.set_state(ForcedForm.chat)
    await message.answer(t.FORCED_ASK_BOT if data["type"] == "bot" else t.FORCED_ASK_CHAT, reply_markup=cancel_kb())


@router.message(ForcedForm.chat, F.text)
async def forced_chat(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    raw = message.text.strip().replace("https://t.me/", "")
    if data["type"] == "bot":
        username = raw.lstrip("@")
        if not username.lower().endswith("bot"):
            await message.answer(t.FORCED_ASK_BOT)
            return
        await state.clear()
        await misc.add_forced_item("bot", data["title"], None, username, f"https://t.me/{username}")
        await message.answer(t.FORCED_ADDED)
        await forced_view(bot, message.chat.id)
        return

    ref: int | str = int(raw) if raw.lstrip("-").isdigit() else "@" + raw.lstrip("@")
    try:
        chat = await bot.get_chat(ref)
    except TelegramAPIError as exc:
        await message.answer(t.FORCED_CHAT_ERROR.format(error=esc(str(exc))))
        return
    warning = ""
    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat.id, me.id)
        if member.status != ChatMemberStatus.ADMINISTRATOR:
            warning = t.FORCED_NOT_ADMIN
    except TelegramAPIError:
        warning = t.FORCED_NOT_ADMIN
    await state.update_data(chat_id=chat.id, username=chat.username, warning=warning)
    await state.set_state(ForcedForm.link)
    skip = [btn(t.BTN_USE_PUBLIC_LINK, Adm(a="frl"))] if chat.username else []
    await message.answer(warning + t.FORCED_ASK_LINK, reply_markup=cancel_kb(skip))


async def _save(bot: Bot, chat_id: int, state: FSMContext, link: str | None) -> None:
    data = await state.get_data()
    await state.clear()
    if not link and data.get("username"):
        link = f"https://t.me/{data['username']}"
    await misc.add_forced_item(data["type"], data["title"], data["chat_id"], data.get("username"), link)
    await bot.send_message(chat_id, t.FORCED_ADDED)
    await forced_view(bot, chat_id)


@router.callback_query(ForcedForm.link, Adm.filter(F.a == "frl"))
async def forced_public_link(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await answer(callback)
    await _save(bot, callback.from_user.id, state, None)


@router.message(ForcedForm.link, F.text)
async def forced_link(message: Message, state: FSMContext, bot: Bot) -> None:
    link = message.text.strip()
    if not link.startswith(("https://t.me/", "http://t.me/", "tg://")):
        await message.answer(t.BAD_URL)
        return
    # zayavkali yopiq kanal havolasi admin kiritganicha saqlanadi
    await _save(bot, message.chat.id, state, link)
