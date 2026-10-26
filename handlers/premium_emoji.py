"""Bot yuboradigan hamma matn/izohdagi emoji'larni premium emoji'ga almashtiradi."""
from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.client.default import Default
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.methods import (
    CopyMessage,
    EditMessageCaption,
    EditMessageText,
    SendAnimation,
    SendDocument,
    SendMessage,
    SendPhoto,
    SendVideo,
)

from utils.premium import premiumize

log = logging.getLogger(__name__)
router = Router()

TEXT_METHODS = (SendMessage, EditMessageText)
CAPTION_METHODS = (EditMessageCaption, SendPhoto, SendVideo, SendDocument, SendAnimation, CopyMessage)


def _is_html(bot: Bot, method: object) -> bool:
    mode = getattr(method, "parse_mode", None)
    if isinstance(mode, Default):
        mode = getattr(bot.default, "parse_mode", None)
    return str(getattr(mode, "value", mode) or "").upper() == "HTML"


class PremiumEmoji(BaseRequestMiddleware):
    async def __call__(self, make_request, bot, method):  # type: ignore[no-untyped-def]
        try:
            if isinstance(method, TEXT_METHODS):
                field, entities = "text", getattr(method, "entities", None)
            elif isinstance(method, CAPTION_METHODS):
                field, entities = "caption", getattr(method, "caption_entities", None)
            else:
                field = entities = None
            if field and not entities and _is_html(bot, method):
                value = getattr(method, field, None)
                if isinstance(value, str) and value:
                    setattr(method, field, premiumize(value))
        except Exception:  # noqa: BLE001
            log.exception("Premium emoji almashtirishda xato (asl matn yuboriladi)")
        return await make_request(bot, method)


@router.startup()
async def install(bot: Bot) -> None:
    if not getattr(bot.session, "_premium_emoji", False):
        bot.session.middleware(PremiumEmoji())
        bot.session._premium_emoji = True  # type: ignore[attr-defined]
        log.info("Premium emoji almashtirish yoqildi")
