"""Faqat asosiy admin: 👥 Adminlar, 💎 Tariflar, ⏱ Limitlar, ⚙️ Sozlamalar."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import texts as t
from database import payments, settings, users
from handlers.admin.common import RoleFilter, back_panel_kb, cancel_kb
from keyboards.callbacks import Adm
from keyboards.common import btn
from utils.text import esc, parse_int, som
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("owner"))
router.callback_query.filter(RoleFilter("owner"))

Row = dict[str, Any]

LIMIT_KEYS = {"movie_limit": t.LIM_MOVIE, "series_limit": t.LIM_SERIES, "window_hours": t.LIM_WINDOW}
SETTING_KEYS = {
    "support_username": t.SET_SUPPORT,
    "public_channel_url": t.SET_CHANNEL_URL,
    "public_channel_id": t.SET_CHANNEL_ID,
    "backup_channel_id": t.SET_BACKUP_ID,
    "card_number": t.SET_CARD,
    "card_owner": t.SET_CARD_OWNER,
}
TARIFF_FIELDS = {"days": t.TAR_DAYS, "price_uzs": t.TAR_UZS, "price_stars": t.TAR_STARS}


class OwnerForm(StatesGroup):
    admin_id = State()
    tariff_value = State()
    tariff_new = State()
    limit_value = State()
    setting_value = State()


# ---------- adminlar ----------

async def admins_view(bot: Bot, chat_id: int, message: object = None) -> None:
    rows = await users.list_admins()
    lines = [t.ADMINS_TITLE.format(owner=config.ADMIN_ID)]
    buttons = []
    for a in rows:
        name = esc(a.get("first_name") or "") + (f" @{a['username']}" if a.get("username") else "")
        lines.append(f"• <code>{a['user_id']}</code> {name} — {t.ROLE_NAMES.get(a['role'], a['role'])}")
        buttons.append([btn(f"❌ {a['user_id']}", Adm(a="admx", id=a["user_id"]))])
    buttons.insert(0, [btn(t.BTN_ADD_MODERATOR, Adm(a="adma", v="moderator")),
                       btn(t.BTN_ADD_ADMIN, Adm(a="adma", v="admin"))])
    await render(bot, chat_id, message, "\n".join(lines), back_panel_kb(*buttons))


@router.callback_query(Adm.filter(F.a == "adm"), StateFilter("*"))
async def admins(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await admins_view(bot, callback.from_user.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "adma"))
async def admin_add(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    await state.set_state(OwnerForm.admin_id)
    await state.update_data(role=callback_data.v if callback_data.v in ("moderator", "admin") else "moderator")
    await render(bot, callback.from_user.id, callback.message, t.ADMIN_ASK_ID, cancel_kb())
    await answer(callback)


@router.message(OwnerForm.admin_id, F.text)
async def admin_add_id(message: Message, state: FSMContext, bot: Bot) -> None:
    user_id = parse_int(message.text)
    if not user_id or user_id == config.ADMIN_ID:
        await message.answer(t.BAD_NUMBER)
        return
    data = await state.get_data()
    await state.clear()
    await users.set_admin(user_id, data["role"], message.from_user.id)  # type: ignore[union-attr]
    await message.answer(t.ADMIN_ADDED.format(user_id=user_id, role=t.ROLE_NAMES[data["role"]]))
    await admins_view(bot, message.chat.id)


@router.callback_query(Adm.filter(F.a == "admx"))
async def admin_remove(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await users.remove_admin(callback_data.id)
    await answer(callback, t.DELETED)
    await admins_view(bot, callback.from_user.id, callback.message)


# ---------- tariflar ----------

def tariff_line(x: Row) -> str:
    stars = f"{x['price_stars']} ⭐" if x.get("price_stars") else "—"
    status = "✅" if x["is_active"] else "⛔"
    return f"{status} {x['days']} kun — {som(x['price_uzs'])} / {stars}"


async def tariffs_view(bot: Bot, chat_id: int, message: object = None) -> None:
    rows = await payments.tariffs(active_only=False)
    buttons = [[btn(tariff_line(x), Adm(a="tr", id=x["id"]))] for x in rows]
    buttons.append([btn(t.BTN_NEW_TARIFF, Adm(a="tra"))])
    await render(bot, chat_id, message, t.TARIFFS_TITLE, back_panel_kb(*buttons))


async def tariff_view(bot: Bot, chat_id: int, tariff_id: int, message: object = None) -> None:
    x = await payments.tariff(tariff_id)
    if not x:
        await tariffs_view(bot, chat_id, message)
        return
    buttons = [
        [btn(label, Adm(a="trf", id=tariff_id, v=key)) for key, label in TARIFF_FIELDS.items()],
        [btn(t.BTN_DEACTIVATE if x["is_active"] else t.BTN_ACTIVATE, Adm(a="trt", id=tariff_id))],
        [btn(t.BTN_BACK, Adm(a="tar"))],
    ]
    await render(bot, chat_id, message, t.TARIFF_ONE.format(line=tariff_line(x)), back_panel_kb(*buttons))


@router.callback_query(Adm.filter(F.a == "tar"), StateFilter("*"))
async def tariffs(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await tariffs_view(bot, callback.from_user.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "tr"))
async def tariff_open(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await tariff_view(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "trt"))
async def tariff_toggle(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    x = await payments.tariff(callback_data.id)
    if x:
        await payments.update_tariff(x["id"], is_active=0 if x["is_active"] else 1)
    await tariff_view(bot, callback.from_user.id, callback_data.id, callback.message)
    await answer(callback, t.SAVED_OK)


@router.callback_query(Adm.filter(F.a == "trf"))
async def tariff_field(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v not in TARIFF_FIELDS:
        await answer(callback)
        return
    await state.set_state(OwnerForm.tariff_value)
    await state.update_data(tariff_id=callback_data.id, field=callback_data.v)
    hint = t.TAR_STARS_HINT if callback_data.v == "price_stars" else ""
    await render(bot, callback.from_user.id, callback.message,
                 t.EDIT_ENTER.format(field=TARIFF_FIELDS[callback_data.v]) + hint, cancel_kb())
    await answer(callback)


@router.message(OwnerForm.tariff_value, F.text)
async def tariff_value(message: Message, state: FSMContext, bot: Bot) -> None:
    value = parse_int(message.text)
    data = await state.get_data()
    field = data["field"]
    if value is None or value < 0 or (value == 0 and field != "price_stars"):
        await message.answer(t.BAD_NUMBER)
        return
    await state.clear()
    await payments.update_tariff(int(data["tariff_id"]), **{field: value or None})
    await message.answer(t.SAVED_OK)
    await tariff_view(bot, message.chat.id, int(data["tariff_id"]))


@router.callback_query(Adm.filter(F.a == "tra"))
async def tariff_new(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(OwnerForm.tariff_new)
    await render(bot, callback.from_user.id, callback.message, t.TARIFF_NEW_FORMAT, cancel_kb())
    await answer(callback)


@router.message(OwnerForm.tariff_new, F.text)
async def tariff_new_value(message: Message, state: FSMContext, bot: Bot) -> None:
    parts = message.text.split()
    days = parse_int(parts[0]) if parts else None
    uzs = parse_int(parts[1]) if len(parts) > 1 else None
    stars = parse_int(parts[2]) if len(parts) > 2 else None
    if not days or days < 1 or not uzs or uzs < 1:
        await message.answer(t.TARIFF_NEW_FORMAT)
        return
    await state.clear()
    await payments.add_tariff(days, uzs, stars or None)
    await message.answer(t.SAVED_OK)
    await tariffs_view(bot, message.chat.id)


# ---------- limitlar ----------

async def limits_view(bot: Bot, chat_id: int, message: object = None) -> None:
    text = t.LIMITS_TITLE.format(
        movie=settings.get_int("movie_limit", 3), series=settings.get_int("series_limit", 3),
        hours=settings.get_int("window_hours", 24),
    )
    buttons = [[btn(label, Adm(a="lm", v=key))] for key, label in LIMIT_KEYS.items()]
    await render(bot, chat_id, message, text, back_panel_kb(*buttons))


@router.callback_query(Adm.filter(F.a == "lim"), StateFilter("*"))
async def limits(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await limits_view(bot, callback.from_user.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "lm"))
async def limit_edit(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v not in LIMIT_KEYS:
        await answer(callback)
        return
    await state.set_state(OwnerForm.limit_value)
    await state.update_data(key=callback_data.v)
    await render(bot, callback.from_user.id, callback.message,
                 t.EDIT_ENTER.format(field=LIMIT_KEYS[callback_data.v]), cancel_kb())
    await answer(callback)


@router.message(OwnerForm.limit_value, F.text)
async def limit_value(message: Message, state: FSMContext, bot: Bot) -> None:
    value = parse_int(message.text)
    data = await state.get_data()
    if value is None or value < 1 or value > 10000:
        await message.answer(t.BAD_NUMBER)
        return
    await state.clear()
    await settings.set_value(data["key"], str(value))
    await message.answer(t.SAVED_OK)
    await limits_view(bot, message.chat.id)


# ---------- sozlamalar ----------

async def settings_view(bot: Bot, chat_id: int, message: object = None) -> None:
    lines = [t.SETTINGS_TITLE]
    lines += [f"{label}: <code>{esc(settings.get(key) or '—')}</code>" for key, label in SETTING_KEYS.items()]
    buttons = [[btn(label, Adm(a="sv2", v=key))] for key, label in SETTING_KEYS.items()]
    await render(bot, chat_id, message, "\n".join(lines), back_panel_kb(*buttons))


@router.callback_query(Adm.filter(F.a == "set"), StateFilter("*"))
async def settings_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await settings_view(bot, callback.from_user.id, callback.message)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "sv2"))
async def setting_edit(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if callback_data.v not in SETTING_KEYS:
        await answer(callback)
        return
    await state.set_state(OwnerForm.setting_value)
    await state.update_data(key=callback_data.v)
    await render(bot, callback.from_user.id, callback.message,
                 t.EDIT_ENTER.format(field=SETTING_KEYS[callback_data.v]) + t.SET_CLEAR_HINT, cancel_kb())
    await answer(callback)


@router.message(OwnerForm.setting_value, F.text)
async def setting_value(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    key = data["key"]
    raw = message.text.strip()
    value = "" if raw == "-" else raw
    if key == "support_username":
        value = value.lstrip("@").replace("https://t.me/", "")
    elif key == "public_channel_url" and value and not value.startswith(("https://", "http://")):
        await message.answer(t.BAD_URL)
        return
    elif key in ("public_channel_id", "backup_channel_id") and value:
        if not (value.lstrip("-").isdigit() or value.startswith("@")):
            await message.answer(t.BAD_CHAT_ID)
            return
    await state.clear()
    await settings.set_value(key, value)
    await message.answer(t.SAVED_OK)
    await settings_view(bot, message.chat.id)
