"""Umumiy tugma yordamchilari."""
from __future__ import annotations

from typing import Any, Sequence

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

import texts as t
from keyboards.callbacks import Nav, Op, Pg

NOOP = "noop"

Btn = InlineKeyboardButton


def btn(text: str, cb: CallbackData | str | None = None, *, url: str | None = None,
        inline: str | None = None) -> InlineKeyboardButton:
    if url:
        return Btn(text=text, url=url)
    if inline is not None:
        return Btn(text=text, switch_inline_query_current_chat=inline)
    data = cb.pack() if isinstance(cb, CallbackData) else (cb or NOOP)
    return Btn(text=text, callback_data=data)


def kb(rows: Sequence[Sequence[InlineKeyboardButton]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[list(r) for r in rows if r])


def chunk(items: Sequence[Any], size: int) -> list[list[Any]]:
    return [list(items[i:i + size]) for i in range(0, len(items), size)]


def nav_row(back: CallbackData | str | None = None) -> list[InlineKeyboardButton]:
    row = []
    if back is not None:
        row.append(btn(t.BTN_BACK, back))
    row.append(btn(t.BTN_HOME, Nav(to="menu")))
    return row


def pager_row(kind: str, page: int, pages: int, extra: str | None = None) -> list[InlineKeyboardButton]:
    if pages <= 1:
        return []
    return [
        btn("⬅️", Pg(k=kind, p=page - 1, x=extra) if page > 0 else NOOP),
        btn(f"{page + 1}/{pages}", NOOP),
        btn("➡️", Pg(k=kind, p=page + 1, x=extra) if page < pages - 1 else NOOP),
    ]


def pages_of(total: int, per_page: int) -> int:
    return max(1, (total + per_page - 1) // per_page)


def movie_label(movie: dict[str, Any]) -> str:
    year = f" ({movie['year']})" if movie.get("year") else ""
    vip = ""
    return f"🎬 {movie.get('title') or '—'}{year}{vip}"[:60]


def movie_buttons(movies: Sequence[dict[str, Any]]) -> list[list[InlineKeyboardButton]]:
    return [[btn(movie_label(m), Op(id=m["id"]))] for m in movies]


def list_kb(movies: Sequence[dict[str, Any]], kind: str, page: int, pages: int,
            extra: str | None = None, back: CallbackData | str | None = None,
            top_rows: Sequence[Sequence[InlineKeyboardButton]] = ()) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [list(r) for r in top_rows]
    rows += movie_buttons(movies)
    rows.append(pager_row(kind, page, pages, extra))
    rows.append(nav_row(back))
    return kb(rows)
