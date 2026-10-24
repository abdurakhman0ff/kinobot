"""Kino hadyalari (kino evaziga VIP)."""
from __future__ import annotations

import json
from typing import Any

from database.db import db
from utils.time import ago_db, now_db

Row = dict[str, Any]


async def add(user_id: int, type_: str, title: str, files: list[dict[str, Any]]) -> int:
    return await db.insert(
        "INSERT INTO gifts (user_id, type, title, files, status, created_at) VALUES (?, ?, ?, ?, 'new', ?)",
        (user_id, type_, title, json.dumps(files), now_db()),
    )


async def get(gift_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM gifts WHERE id = ?", (gift_id,))


async def pending_count(user_id: int) -> int:
    return int(await db.fetchval(
        "SELECT COUNT(*) FROM gifts WHERE user_id = ? AND status = 'new'", (user_id,), default=0))


async def rewarded_days(user_id: int, days: int = 30) -> int:
    return int(await db.fetchval(
        "SELECT COALESCE(SUM(reward_days), 0) FROM gifts WHERE user_id = ? AND status = 'approved' AND decided_at >= ?",
        (user_id, ago_db(days=days)), default=0))


async def decide(gift_id: int, status: str, reward_days: int = 0, reason: str | None = None) -> bool:
    """Faqat 'new' holatdagi hadyani yopadi. Muvaffaqiyatli bo'lsa True (ikki marta bosishdan himoya)."""
    changed = await db.execute(
        "UPDATE gifts SET status = ?, reward_days = ?, reason = ?, decided_at = ? WHERE id = ? AND status = 'new'",
        (status, reward_days, reason, now_db(), gift_id),
    )
    return bool(changed)


async def reopen(gift_id: int) -> None:
    await db.execute("UPDATE gifts SET status = 'new', reward_days = 0, decided_at = NULL WHERE id = ?", (gift_id,))


async def set_movie(gift_id: int, movie_id: int) -> None:
    await db.execute("UPDATE gifts SET movie_id = ? WHERE id = ?", (movie_id, gift_id))
