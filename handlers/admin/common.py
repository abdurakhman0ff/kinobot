"""Admin panel uchun umumiy yordamchilar."""
from __future__ import annotations

import logging
from typing import Any, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageOriginChannel,
    TelegramObject,
)

import config
import texts as t
from database import settings, users
from keyboards.callbacks import Adm, Nav
from keyboards.common import btn, chunk, kb
from utils.text import chat_ref
from utils.ui import answer, render

log = logging.getLogger(__name__)

LANGUAGES = ["O'zbek", "Rus", "Ingliz", "Qozoq", "Turk", "Hind", "Koreys"]
QUALITIES = ["720p", "1080p", "4K"]
TYPES = ["film", "serial", "multfilm"]

# (minimal rol, tugma matni, amal)
SECTIONS: list[tuple[str, str, str]] = [
    ("moderator", t.ADM_ADD, "add"),
    ("moderator", t.ADM_EDIT, "edit"),
    ("moderator", t.ADM_EPISODES, "eps"),
    ("admin", t.ADM_STATS, "st"),
    ("admin", t.ADM_BROADCAST, "bc"),
    ("admin", t.ADM_BAN, "ban"),
    ("admin", t.ADM_PROMO, "pr"),
    ("admin", t.ADM_SCHEDULED, "sch"),
    ("moderator", t.ADM_REQUESTS, "rq"),
    ("moderator", t.ADM_REPORTS, "rp"),
    ("admin", t.ADM_UNFILLED, "unf"),
    ("admin", t.ADM_ENRICH, "enr"),
    ("owner", t.ADM_ADMINS, "adm"),
    ("owner", t.ADM_TARIFFS, "tar"),
    ("owner", t.ADM_LIMITS, "lim"),
    ("owner", t.ADM_FORCED, "frc"),
    ("owner", t.ADM_SETTINGS, "set"),
    ("owner", t.ADM_BACKUP, "bak"),
]


class RoleFilter(BaseFilter):
    def __init__(self, minimum: str) -> None:
        self.minimum = minimum

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        return bool(user) and users.has_role(user.id, self.minimum)


def panel_kb(user_id: int) -> InlineKeyboardMarkup:
    buttons = [btn(text, Adm(a=action)) for role, text, action in SECTIONS if users.has_role(user_id, role)]
    rows = chunk(buttons, 2)
    rows.append([btn(t.BTN_HOME, Nav(to="menu"))])
    return kb(rows)


def panel_row() -> list[InlineKeyboardButton]:
    return [btn(t.BTN_ADMIN_PANEL, Adm(a="p"))]


def cancel_kb(*extra: Sequence[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    rows = [list(r) for r in extra]
    rows.append([btn(t.BTN_CANCEL, Adm(a="x"))])
    return kb(rows)


def back_panel_kb(*extra: Sequence[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    rows = [list(r) for r in extra]
    rows.append(panel_row())
    return kb(rows)


def languages_kb(selected: Sequence[str], action: str, done_action: str, item_id: int = 0,
                 extra: Sequence[str] = ()) -> InlineKeyboardMarkup:
    """Ko'p tanlovli tillar. `extra` — bazada uchragan boshqa tillar."""
    names = list(LANGUAGES) + [x for x in extra if x not in LANGUAGES]
    names += [x for x in selected if x not in names]
    buttons = [btn(("✅ " if name in selected else "") + name, Adm(a=action, id=item_id, v=name[:30])) for name in names]
    rows = chunk(buttons, 3)
    rows.append([btn(t.BTN_OTHER_LANG, Adm(a=action, id=item_id, v="+")),
                 btn(t.BTN_DONE, Adm(a=done_action, id=item_id))])
    return kb(rows)


def media_file_id(message: Message) -> str | None:
    if message.video:
        return message.video.file_id
    if message.document:
        return message.document.file_id
    if message.animation:
        return message.animation.file_id
    return None


async def store_media(bot: Bot, message: Message) -> tuple[int, int | None, str | None] | None:
    """Videoni saqlash kanaliga (va zaxira kanalga) joylaydi.

    Saqlash kanalidan forward qilingan bo'lsa, mavjud post ishlatiladi.
    (storage_message_id, backup_message_id, file_id) yoki media bo'lmasa None.
    """
    file_id = media_file_id(message)
    if not file_id:
        return None
    origin = message.forward_origin
    if isinstance(origin, MessageOriginChannel) and origin.chat.id == config.STORAGE_CHANNEL_ID:
        storage_id = origin.message_id
    else:
        res = await bot.copy_message(config.STORAGE_CHANNEL_ID, message.chat.id, message.message_id)
        storage_id = res.message_id
    backup_id = None
    backup = chat_ref(settings.get("backup_channel_id"))
    if backup:
        try:
            res = await bot.copy_message(backup, message.chat.id, message.message_id)
            backup_id = res.message_id
        except TelegramAPIError as exc:
            log.warning("Zaxira kanalga nusxa olinmadi: %s", exc)
    return storage_id, backup_id, file_id


async def reply(event: Message | CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Callback bo'lsa xabarni tahrirlaydi, aks holda yangi xabar yuboradi."""
    if isinstance(event, CallbackQuery):
        await render(event.bot, event.from_user.id, event.message, text, markup)  # type: ignore[arg-type]
        await answer(event)
    else:
        await event.answer(text, reply_markup=markup)


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
