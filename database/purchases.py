"""Kinolarni alohida sotib olish."""
from __future__ import annotations

from typing import Any

from database.db import db
from utils.time import now_db

Row = dict[str, Any]


async def owned(user_id: int, movie_id: int) -> bool:
    return bool(await db.fetchval(
        "SELECT 1 FROM purchases WHERE user_id = ? AND movie_id = ? AND status = 'paid'", (user_id, movie_id)))


async def pending_count(user_id: int) -> int:
    return int(await db.fetchval(
        "SELECT COUNT(*) FROM purchases WHERE user_id = ? AND status = 'pending'", (user_id,), default=0))


async def add(user_id: int, movie_id: int, price: int) -> int:
    return await db.insert(
        "INSERT INTO purchases (user_id, movie_id, price, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (user_id, movie_id, price, now_db()))


async def get(purchase_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM purchases WHERE id = ?", (purchase_id,))


async def decide(purchase_id: int, status: str) -> bool:
    """Atomar: faqat 'pending' holatidagini o'zgartiradi."""
    changed = await db.execute(
        "UPDATE purchases SET status = ?, decided_at = ? WHERE id = ? AND status = 'pending'",
        (status, now_db(), purchase_id))
    return bool(changed)
