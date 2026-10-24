"""Inline qidiruv va bot chatida tanlangan inline natija."""
from __future__ import annotations

import re
from typing import Any

from aiogram import Bot, F, Router
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
    Message,
)

import texts as t
from database import movies, users
from keyboards.user import watch_url_kb
from services import delivery, search, subscription
from services.cards import languages_label, type_label
from services.tmdb import poster_url
from utils.text import esc
from utils.ui import safe_delete

router = Router()

Row = dict[str, Any]

PAGE = 20
_CODE_RE = re.compile(r"Kod:\s*(\d+)")


def _result(movie: Row, bot_username: str) -> InlineQueryResultArticle:
    title = f"{movie['title']}"
    if movie.get("year"):
        title += f" ({movie['year']})"
    first = f"{type_label(movie['type'])} · #{movie['code']}"
    if movie.get("quality"):
        first += f" · {movie['quality']}"
    description = f"{first}\n{languages_label(movie)} · 👁 {movie.get('views') or 0}"
    return InlineQueryResultArticle(
        id=str(movie["id"]),
        title=title[:100],
        description=description,
        thumbnail_url=poster_url(movie.get("poster_path"), "w154"),
        input_message_content=InputTextMessageContent(
            message_text=t.INLINE_MESSAGE.format(title=esc(movie["title"]), code=movie["code"]),
        ),
        reply_markup=watch_url_kb(bot_username, movie["code"]),
    )


@router.inline_query()
async def inline_search(query: InlineQuery, bot: Bot, db_user: Row | None = None) -> None:
    user = db_user or {"id": query.from_user.id}
    if not users.is_privileged(user) and await subscription.missing(bot, query.from_user.id):
        await query.answer(
            [], cache_time=5, is_personal=True,
            button=InlineQueryResultsButton(text=t.INLINE_SUBSCRIBE, start_parameter="sub"),
        )
        return

    offset = int(query.offset) if query.offset.isdigit() else 0
    text = query.query.strip()
    if not text:
        if offset:
            await query.answer([], cache_time=10, is_personal=True)
            return
        rows = await movies.newest(PAGE)
        next_offset = ""
    else:
        found = await search.search(text)
        part = found[offset:offset + PAGE]
        rows = await movies.by_ids([e.id for e in part])
        next_offset = str(offset + PAGE) if offset + PAGE < len(found) else ""

    username = await delivery.bot_username(bot)
    await query.answer(
        [_result(m, username) for m in rows],
        cache_time=10,
        is_personal=True,
        next_offset=next_offset,
    )


@router.message(F.via_bot)
async def chosen_in_bot_chat(message: Message, bot: Bot, db_user: Row) -> None:
    """Bot o'z chatida inline natija tanlansa: xabarni o'chirib, kinoni yuboradi."""
    me = await bot.me()
    if message.via_bot.id != me.id:  # type: ignore[union-attr]
        return
    match = _CODE_RE.search(message.text or message.caption or "")
    await safe_delete(bot, message.chat.id, message.message_id)
    if match:
        await delivery.open_by_code(bot, db_user, message.chat.id, int(match.group(1)))
