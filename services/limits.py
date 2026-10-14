"""Kunlik limit: `movie` (film, multfilm) va `series` (serial qismlari) alohida hisoblanadi.

Oyna birinchi ko'rishdan boshlanadi; `window_hours` o'tgach keyingi ko'rishda yangilanadi.
Oyna ichida bir xil element qayta ko'rilsa limit sarflanmaydi.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from database import settings
from database.db import db
from utils.time import from_db, now_db, utcnow


@dataclass(slots=True)
class Verdict:
    allowed: bool
    seconds_left: float = 0


def limit_of(kind: str) -> int:
    return settings.get_int("series_limit" if kind == "series" else "movie_limit", 3)


def window_hours() -> int:
    return max(1, settings.get_int("window_hours", 24))


async def _window(user_id: int, kind: str) -> tuple[str | None, int]:
    """Amaldagi oyna (boshlanishi, soni). Oyna eskirgan bo'lsa (None, 0)."""
    row = await db.fetchone(
        "SELECT window_start, count FROM usage_windows WHERE user_id = ? AND kind = ?", (user_id, kind)
    )
    start = from_db(row["window_start"]) if row else None
    if not start or utcnow() - start >= timedelta(hours=window_hours()):
        return None, 0
    return row["window_start"], row["count"]  # type: ignore[index]


async def check(user_id: int, kind: str, item_key: str) -> Verdict:
    start, count = await _window(user_id, kind)
    if start is None:
        return Verdict(True)
    if await db.fetchval(
        "SELECT 1 FROM usage_items WHERE user_id = ? AND kind = ? AND item_key = ? AND window_start = ?",
        (user_id, kind, item_key, start),
    ):
        return Verdict(True)
    if count < limit_of(kind):
        return Verdict(True)
    reset_at = from_db(start) + timedelta(hours=window_hours())  # type: ignore[operator]
    return Verdict(False, (reset_at - utcnow()).total_seconds())


async def consume(user_id: int, kind: str, item_key: str) -> None:
    async with db.tx():
        start, _ = await _window(user_id, kind)
        if start is None:
            start = now_db()
            await db.execute("DELETE FROM usage_items WHERE user_id = ? AND kind = ?", (user_id, kind))
            await db.execute(
                "INSERT OR REPLACE INTO usage_windows (user_id, kind, window_start, count) VALUES (?, ?, ?, 0)",
                (user_id, kind, start),
            )
        added = await db.execute(
            "INSERT OR IGNORE INTO usage_items (user_id, kind, item_key, window_start) VALUES (?, ?, ?, ?)",
            (user_id, kind, item_key, start),
        )
        if added:
            await db.execute(
                "UPDATE usage_windows SET count = count + 1 WHERE user_id = ? AND kind = ?", (user_id, kind)
            )


async def status(user_id: int) -> dict[str, tuple[int, int, float]]:
    """kind -> (ishlatilgan, limit, yangilanishgacha soniya)."""
    result = {}
    for kind in ("movie", "series"):
        start, count = await _window(user_id, kind)
        left = 0.0
        if start:
            left = (from_db(start) + timedelta(hours=window_hours()) - utcnow()).total_seconds()  # type: ignore[operator]
        result[kind] = (count, limit_of(kind), left)
    return result
