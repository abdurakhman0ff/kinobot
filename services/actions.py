"""Qidiruv natijalari va obunadan keyin saqlangan harakatni bajarish."""
from __future__ import annotations

from typing import Any

from aiogram import Bot

import texts as t
from database import movies
from keyboards.common import list_kb, pages_of
from keyboards.user import not_found_kb
from services import delivery, search
from services.tmdb import IMDB_RE, result_title, tmdb
from utils.text import esc, truncate
from utils.ui import render

Row = dict[str, Any]

SEARCH_PER_PAGE = 8

# foydalanuvchining oxirgi qidiruvi (sahifalash uchun) va "Kino so'rash" uchun tayyor matn
last_query: dict[int, str] = {}
prefill: dict[int, str] = {}


def _remember(store: dict[int, str], user_id: int, value: str) -> None:
    if len(store) > 20000:
        store.clear()
    store[user_id] = value


def set_prefill(user_id: int, text: str) -> None:
    _remember(prefill, user_id, truncate(text.strip(), 200))


async def show_search(bot: Bot, user: Row, chat_id: int, query: str, page: int = 0,
                      message: object = None) -> None:
    results = await search.search(query)
    if not results:
        set_prefill(user["id"], query)
        await render(bot, chat_id, message, t.SEARCH_NOT_FOUND.format(query=esc(query)), not_found_kb())
        return
    _remember(last_query, user["id"], query)
    pages = pages_of(len(results), SEARCH_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    part = results[page * SEARCH_PER_PAGE:(page + 1) * SEARCH_PER_PAGE]
    items = [{"id": e.id, "title": e.title, "year": e.year, "is_vip": e.is_vip} for e in part]
    text = t.SEARCH_RESULTS.format(query=esc(query), count=len(results))
    await render(bot, chat_id, message, text, list_kb(items, "s", page, pages))


async def imdb_lookup(bot: Bot, user: Row, chat_id: int, text: str) -> None:
    if not tmdb.enabled:
        await bot.send_message(chat_id, t.IMDB_DISABLED)
        await show_search(bot, user, chat_id, text)
        return
    found: tuple[str, int] | None = None
    name = text.strip()
    match = IMDB_RE.search(text)
    if match:
        found = await tmdb.find_imdb(match.group(1))
    else:
        results = await tmdb.multi_search(name)
        if results:
            found = (results[0]["media_type"], results[0]["id"])
            name = result_title(results[0])
    if found:
        kind, tmdb_id = found
        catalog = await movies.by_tmdb([tmdb_id], series=kind == "tv")
        if catalog:
            await delivery.open_movie(bot, user, chat_id, catalog[0], checked=True)
            return
        if match:
            name = await tmdb.localized_title(kind, tmdb_id) or name
    set_prefill(user["id"], name)
    await bot.send_message(chat_id, t.IMDB_NOT_IN_CATALOG.format(name=esc(name)), reply_markup=not_found_kb())


async def run_pending(bot: Bot, user: Row, chat_id: int, payload: dict[str, Any] | None) -> None:
    """Obuna tasdiqlangach foydalanuvchi so'ragan harakatni o'zi bajaradi."""
    action = (payload or {}).get("a")
    if action == "code":
        await delivery.open_by_code(bot, user, chat_id, int(payload["v"]), checked=True)  # type: ignore[index]
    elif action == "search":
        await show_search(bot, user, chat_id, str(payload["q"]))  # type: ignore[index]
    elif action == "imdb":
        await imdb_lookup(bot, user, chat_id, str(payload["q"]))  # type: ignore[index]
    elif action == "open":
        movie = await movies.get(int(payload["id"]))  # type: ignore[index]
        if movie:
            await delivery.open_movie(bot, user, chat_id, movie, checked=True)
        else:
            await bot.send_message(chat_id, t.MOVIE_GONE)
    elif action == "ep":
        await delivery.open_episode(bot, user, chat_id, int(payload["id"]), checked=True)  # type: ignore[index]
    elif action == "random":
        await delivery.show_random(bot, user, chat_id, checked=True)
    else:
        await bot.send_message(chat_id, t.SUB_OK)
