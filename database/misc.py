"""Majburiy obuna, zayavkalar, kutilayotgan harakatlar, so'rovlar, shikoyatlar, rejalashtirilgan postlar."""
from __future__ import annotations

import json
from typing import Any

from database.db import db
from utils.time import ago_db, local_day_start_db, now_db

Row = dict[str, Any]

PENDING_TTL_MIN = 30


# ---------- majburiy obuna ----------

async def forced_items(active_only: bool = True) -> list[Row]:
    cond = "WHERE is_active = 1" if active_only else ""
    return await db.fetchall(f"SELECT * FROM forced_items {cond} ORDER BY sort, id")


async def forced_item(item_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM forced_items WHERE id = ?", (item_id,))


async def add_forced_item(type_: str, title: str, chat_id: int | None, username: str | None,
                          invite_link: str | None) -> int:
    sort = int(await db.fetchval("SELECT MAX(sort) FROM forced_items", default=0)) + 1
    return await db.insert(
        """INSERT INTO forced_items (type, title, chat_id, username, invite_link, is_active, sort)
           VALUES (?, ?, ?, ?, ?, 1, ?)""",
        (type_, title, chat_id, username, invite_link, sort),
    )


async def toggle_forced_item(item_id: int) -> None:
    await db.execute("UPDATE forced_items SET is_active = 1 - is_active WHERE id = ?", (item_id,))


async def delete_forced_item(item_id: int) -> None:
    await db.execute("DELETE FROM forced_items WHERE id = ?", (item_id,))
    await db.execute("DELETE FROM bot_confirms WHERE item_id = ?", (item_id,))


async def add_join_request(user_id: int, chat_id: int) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO join_requests (user_id, chat_id, created_at) VALUES (?, ?, ?)",
        (user_id, chat_id, now_db()),
    )


async def has_join_request(user_id: int, chat_id: int) -> bool:
    return bool(await db.fetchval(
        "SELECT 1 FROM join_requests WHERE user_id = ? AND chat_id = ?", (user_id, chat_id)
    ))


async def confirmed_bots(user_id: int) -> set[int]:
    rows = await db.fetchall("SELECT item_id FROM bot_confirms WHERE user_id = ?", (user_id,))
    return {r["item_id"] for r in rows}


async def confirm_bots(user_id: int, item_ids: list[int]) -> None:
    await db.executemany(
        "INSERT OR IGNORE INTO bot_confirms (user_id, item_id, created_at) VALUES (?, ?, ?)",
        [(user_id, i, now_db()) for i in item_ids],
    )


# ---------- kutilayotgan harakat ----------

async def save_pending(user_id: int, payload: dict[str, Any]) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO pending_actions (user_id, payload, created_at) VALUES (?, ?, ?)",
        (user_id, json.dumps(payload, ensure_ascii=False), now_db()),
    )


async def pop_pending(user_id: int) -> dict[str, Any] | None:
    row = await db.fetchone(
        "SELECT payload FROM pending_actions WHERE user_id = ? AND created_at >= ?",
        (user_id, ago_db(minutes=PENDING_TTL_MIN)),
    )
    await db.execute("DELETE FROM pending_actions WHERE user_id = ?", (user_id,))
    if not row:
        return None
    try:
        return json.loads(row["payload"])
    except ValueError:
        return None


async def cleanup_pending() -> int:
    return await db.execute("DELETE FROM pending_actions WHERE created_at < ?", (ago_db(minutes=PENDING_TTL_MIN),))


# ---------- kino so'rash ----------

async def requests_today(user_id: int) -> int:
    return int(await db.fetchval(
        "SELECT COUNT(*) FROM requests WHERE user_id = ? AND created_at >= ?",
        (user_id, local_day_start_db()), default=0,
    ))


async def add_request(user_id: int, text: str) -> int:
    return await db.insert(
        "INSERT INTO requests (user_id, text, status, created_at) VALUES (?, ?, 'new', ?)",
        (user_id, text, now_db()),
    )


async def get_request(request_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM requests WHERE id = ?", (request_id,))


async def set_request_status(request_id: int, status: str, movie_code: int | None = None) -> None:
    await db.execute("UPDATE requests SET status = ?, movie_code = ? WHERE id = ?", (status, movie_code, request_id))


async def open_requests(limit: int = 20) -> list[Row]:
    return await db.fetchall(
        "SELECT * FROM requests WHERE status = 'new' ORDER BY created_at LIMIT ?", (limit,)
    )


# ---------- shikoyatlar ----------

async def reported_recently(user_id: int, movie_id: int) -> bool:
    return bool(await db.fetchval(
        "SELECT 1 FROM reports WHERE user_id = ? AND movie_id = ? AND created_at >= ?",
        (user_id, movie_id, ago_db(days=1)),
    ))


async def add_report(user_id: int, movie_id: int, episode_id: int | None, reason: str) -> int:
    return await db.insert(
        "INSERT INTO reports (user_id, movie_id, episode_id, reason, status, created_at) VALUES (?, ?, ?, ?, 'new', ?)",
        (user_id, movie_id, episode_id, reason, now_db()),
    )


async def open_reports(limit: int = 20) -> list[Row]:
    return await db.fetchall(
        """SELECT r.*, m.code, m.title, e.season, e.number FROM reports r
           JOIN movies m ON m.id = r.movie_id LEFT JOIN episodes e ON e.id = r.episode_id
           WHERE r.status = 'new' ORDER BY r.created_at LIMIT ?""",
        (limit,),
    )


async def close_report(report_id: int) -> None:
    await db.execute("UPDATE reports SET status = 'done' WHERE id = ?", (report_id,))


# ---------- rejalashtirilgan postlar ----------

async def add_scheduled(movie_id: int, run_at: str, created_by: int) -> int:
    return await db.insert(
        "INSERT INTO scheduled_posts (movie_id, run_at, status, created_by, created_at) VALUES (?, ?, 'pending', ?, ?)",
        (movie_id, run_at, created_by, now_db()),
    )


async def pending_scheduled() -> list[Row]:
    return await db.fetchall(
        """SELECT s.*, m.code, m.title FROM scheduled_posts s JOIN movies m ON m.id = s.movie_id
           WHERE s.status = 'pending' ORDER BY s.run_at"""
    )


async def due_scheduled() -> list[Row]:
    return await db.fetchall(
        "SELECT * FROM scheduled_posts WHERE status = 'pending' AND run_at <= ? ORDER BY run_at", (now_db(),)
    )


async def set_scheduled_status(post_id: int, status: str) -> None:
    await db.execute("UPDATE scheduled_posts SET status = ? WHERE id = ?", (status, post_id))
