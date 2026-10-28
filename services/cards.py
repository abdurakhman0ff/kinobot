"""Kartochka matnlari va poster yordamchilari."""
from __future__ import annotations

from typing import Any

from aiogram.types import Message

import texts as t
from database import movies
from services.tmdb import poster_url
from utils.text import esc, truncate, visible_len
from utils.time import fmt_runtime

CAPTION_LIMIT = 1024


def fmt_rating(movie: dict[str, Any]) -> str:
    value = movies.rating_of(movie)
    if value is None:
        return t.NOT_RATED
    number = f"{value:.2f}".rstrip("0").rstrip(".")
    return t.RATING_VALUE.format(value=number, count=movie["rating_count"])


def type_label(movie_type: str | None) -> str:
    return t.TYPE_LABELS.get(movie_type or "film", t.TYPE_LABELS["film"])


def languages_label(movie: dict[str, Any]) -> str:
    return movie.get("languages") or t.UNKNOWN


def _title_line(movie: dict[str, Any]) -> str:
    title = esc(movie.get("title") or "—")
    original = movie.get("original_title")
    if original and original.strip().lower() != (movie.get("title") or "").strip().lower():
        return f"🎬 <b>{title}</b> ({esc(original)})"
    return f"🎬 <b>{title}</b>"


def _info_lines(movie: dict[str, Any], *, short: bool = False) -> list[str]:
    pairs = [
        ("📅 Yil", movie.get("year")),
        ("🎭 Janr", movie.get("genres")),
        ("🌍 Davlat", None if short else movie.get("countries")),
        ("⏱ Davomiylik", None if short else fmt_runtime(movie.get("runtime_min"))),
        ("📺 Sifat", movie.get("quality")),
        ("🗣 Til", movie.get("languages")),
    ]
    return [f"{label}: {esc(value)}" for label, value in pairs if value]


def card_caption(movie: dict[str, Any], extra: str = "", hide_title: bool = False) -> str:
    title = t.BM_HIDDEN_TITLE if hide_title else _title_line(movie)
    head = [title, ""] + _info_lines(movie) + [f"⭐ Reyting: {fmt_rating(movie)}"]
    if extra:
        head.append(extra)
    tail = f"\n\n📥 Kod: <code>{movie['code']}</code>"
    body = "\n".join(head)
    description = (movie.get("description") or "").strip()
    if description:
        prefix = "\n\n📝 Tavsif: "
        room = CAPTION_LIMIT - visible_len(body + tail) - len(prefix)
        if room > 20:
            body += prefix + esc(truncate(description, room))
    return body + tail


def locked_caption(movie: dict[str, Any]) -> str:
    info = _info_lines(movie, short=True)
    lines = [_title_line(movie), ""] + (info + [""] if info else [])
    lines += [f"📥 Kod: <code>{movie['code']}</code>", "", t.VIP_ONLY]
    return "\n".join(lines)


def episode_caption(movie: dict[str, Any], ep: dict[str, Any]) -> str:
    return t.EPISODE_CAPTION.format(
        title=esc(movie.get("title") or ""), season=ep["season"], number=ep["number"], code=movie["code"]
    )


def short_post(movie: dict[str, Any]) -> str:
    """Yangi kino bildirishnomasi va ochiq kanal posti uchun qisqa matn."""
    lines = [_title_line(movie), ""] + _info_lines(movie, short=True)
    rating = movies.rating_of(movie)
    if rating:
        lines.append(f"⭐ Reyting: {fmt_rating(movie)}")
    description = (movie.get("description") or "").strip()
    if description:
        lines += ["", esc(truncate(description, 300))]
    lines += ["", f"📥 Kod: <code>{movie['code']}</code>"]
    return "\n".join(lines)


def poster_of(movie: dict[str, Any]) -> str | None:
    return movie.get("poster_file_id") or poster_url(movie.get("poster_path"))


async def remember_poster(movie: dict[str, Any], message: Message | None) -> None:
    """Telegramga birinchi yuborilgan posterning file_id sini keshlaydi."""
    if not message or not message.photo or movie.get("poster_file_id"):
        return
    file_id = message.photo[-1].file_id
    movie["poster_file_id"] = file_id
    await movies.update(movie["id"], poster_file_id=file_id)
