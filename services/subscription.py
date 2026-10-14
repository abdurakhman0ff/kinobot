"""Majburiy obuna tekshiruvi."""
from __future__ import annotations

import logging
import time
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest

import texts as t
from database import misc, users
from keyboards.user import subscribe_kb
from services import notify
from utils.text import esc

log = logging.getLogger(__name__)

POSITIVE_TTL = 600  # ijobiy natija 10 daqiqa keshlanadi
ALERT_EVERY = 3600  # bir element bo'yicha adminga soatiga bir marta

_positive: dict[tuple[int, int], float] = {}
_NOT_MEMBER_ERRORS = ("user not found", "participant_id_invalid", "member not found", "user_not_participant")
_MEMBER_STATUSES = {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER}


def _chat_of(item: dict[str, Any]) -> int | str | None:
    if item.get("chat_id"):
        return int(item["chat_id"])
    if item.get("username"):
        return "@" + str(item["username"]).lstrip("@")
    return None


async def _check_chat(bot: Bot, item: dict[str, Any], user_id: int) -> bool | None:
    """True = a'zo, False = a'zo emas, None = tekshirib bo'lmadi (element o'tkazib yuboriladi)."""
    chat = _chat_of(item)
    if chat is None:
        return None
    member = None
    try:
        member = await bot.get_chat_member(chat, user_id)
    except TelegramBadRequest as exc:
        if not any(e in str(exc).lower() for e in _NOT_MEMBER_ERRORS):
            await _alert(bot, item, exc)
            return None
    except TelegramAPIError as exc:
        await _alert(bot, item, exc)
        return None
    if member is not None:
        if member.status in _MEMBER_STATUSES:
            return True
        if member.status == ChatMemberStatus.RESTRICTED and getattr(member, "is_member", False):
            return True
    # zayavka tashlagan foydalanuvchi a'zo hisoblanadi
    if item.get("chat_id") and await misc.has_join_request(user_id, int(item["chat_id"])):
        return True
    return False


async def _alert(bot: Bot, item: dict[str, Any], exc: Exception) -> None:
    log.warning("Majburiy obuna elementi #%s tekshirilmadi: %s", item["id"], exc)
    await notify.owner(
        bot,
        t.ADMIN_FORCED_ERROR.format(title=esc(item["title"]), error=esc(str(exc)[:200])),
        key=f"forced:{item['id']}",
        every=ALERT_EVERY,
    )


async def missing(bot: Bot, user_id: int) -> list[dict[str, Any]]:
    items = await misc.forced_items()
    if not items:
        return []
    confirmed = await misc.confirmed_bots(user_id)
    now = time.monotonic()
    result = []
    for item in items:
        if item["type"] == "bot":
            if item["id"] not in confirmed:
                result.append(item)
            continue
        key = (user_id, item["id"])
        if _positive.get(key, 0) > now:
            continue
        ok = await _check_chat(bot, item, user_id)
        if ok:
            _positive[key] = now + POSITIVE_TTL
        elif ok is False:
            result.append(item)
    if len(_positive) > 100000:
        _positive.clear()
    return result


async def ensure(bot: Bot, user: dict[str, Any], chat_id: int, payload: dict[str, Any]) -> bool:
    """Obuna bo'lsa True. Aks holda harakatni saqlab, obuna so'rovini yuboradi."""
    if users.is_privileged(user):
        return True
    items = await missing(bot, user["id"])
    if not items:
        return True
    await misc.save_pending(user["id"], payload)
    await bot.send_message(chat_id, t.SUBSCRIBE, reply_markup=subscribe_kb(items))
    return False


async def confirm_bot_items(user_id: int) -> None:
    items = [i["id"] for i in await misc.forced_items() if i["type"] == "bot"]
    if items:
        await misc.confirm_bots(user_id, items)
