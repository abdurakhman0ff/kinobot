"""Foydalanuvchilar, adminlar va hodisalar."""
from __future__ import annotations

import json
import time
from datetime import timedelta
from typing import Any

from aiogram.types import User

import config
from database.db import db
from utils.time import ago_db, from_db, now_db, to_db, utcnow

ROLE_LEVEL = {"moderator": 1, "admin": 2, "owner": 3}

_admins: dict[int, str] = {}
_touched: dict[int, float] = {}
TOUCH_INTERVAL = 60.0


# ---------- rollar ----------

async def load_admins() -> None:
    rows = await db.fetchall("SELECT user_id, role FROM admins")
    _admins.clear()
    _admins.update({r["user_id"]: r["role"] for r in rows if r["role"] in ROLE_LEVEL})


def role_of(user_id: int) -> str | None:
    if user_id == config.ADMIN_ID:
        return "owner"
    return _admins.get(user_id)


def has_role(user_id: int, minimum: str) -> bool:
    role = role_of(user_id)
    return role is not None and ROLE_LEVEL[role] >= ROLE_LEVEL[minimum]


def staff_ids(minimum: str = "moderator") -> list[int]:
    ids = {config.ADMIN_ID}
    ids.update(uid for uid, role in _admins.items() if ROLE_LEVEL[role] >= ROLE_LEVEL[minimum])
    return sorted(ids)


async def list_admins() -> list[dict[str, Any]]:
    return await db.fetchall(
        """SELECT a.user_id, a.role, a.added_at, u.first_name, u.username
           FROM admins a LEFT JOIN users u ON u.id = a.user_id ORDER BY a.added_at"""
    )


async def set_admin(user_id: int, role: str, added_by: int) -> None:
    await db.execute(
        "INSERT OR REPLACE INTO admins (user_id, role, added_by, added_at) VALUES (?, ?, ?, ?)",
        (user_id, role, added_by, now_db()),
    )
    await load_admins()


async def remove_admin(user_id: int) -> None:
    await db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    await load_admins()


# ---------- foydalanuvchi ----------

async def get(user_id: int) -> dict[str, Any] | None:
    return await db.fetchone("SELECT * FROM users WHERE id = ?", (user_id,))


async def touch(user: User, *, interacted: bool) -> tuple[dict[str, Any], bool]:
    """Foydalanuvchini yozadi/yangilaydi. (qator, yangimi) qaytaradi."""
    row = await get(user.id)
    now = now_db()
    if row is None:
        await db.execute(
            """INSERT OR IGNORE INTO users (id, first_name, last_name, username, joined_at, last_active)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user.id, user.first_name, user.last_name, user.username, now, now),
        )
        _touched[user.id] = time.monotonic()
        return (await get(user.id)) or {"id": user.id}, True

    changed = (
        row["first_name"] != user.first_name
        or row["last_name"] != user.last_name
        or row["username"] != user.username
        or (interacted and row["is_blocked_bot"])
    )
    stale = time.monotonic() - _touched.get(user.id, 0) > TOUCH_INTERVAL
    if changed or stale:
        blocked = 0 if interacted else row["is_blocked_bot"]
        await db.execute(
            """UPDATE users SET first_name = ?, last_name = ?, username = ?, last_active = ?,
               is_blocked_bot = ? WHERE id = ?""",
            (user.first_name, user.last_name, user.username, now, blocked, user.id),
        )
        _touched[user.id] = time.monotonic()
        if len(_touched) > 50000:
            _touched.clear()
        row.update(first_name=user.first_name, last_name=user.last_name, username=user.username,
                   last_active=now, is_blocked_bot=blocked)
    return row, False


_FIELDS = {"pinned_message_id", "menu_message_id", "notify_new", "is_blocked_bot", "is_banned",
           "vip_remind_for", "vip_expired_for"}


async def set_field(user_id: int, field: str, value: Any) -> None:
    if field not in _FIELDS:
        raise ValueError(field)
    await db.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id))


async def ensure_exists(user_id: int) -> None:
    await db.execute("INSERT OR IGNORE INTO users (id, joined_at, last_active) VALUES (?, ?, ?)",
                     (user_id, now_db(), now_db()))


async def set_banned(user_id: int, banned: bool) -> None:
    await ensure_exists(user_id)
    await set_field(user_id, "is_banned", int(banned))


# ---------- VIP ----------

def vip_until(user: dict[str, Any] | None) -> Any:
    if not user:
        return None
    until = from_db(user.get("vip_until"))
    return until if until and until > utcnow() else None


def is_vip(user: dict[str, Any] | None) -> bool:
    return vip_until(user) is not None


def is_privileged(user: dict[str, Any] | None) -> bool:
    """VIP yoki xodim: majburiy obuna va limitdan ozod."""
    return bool(user) and (is_vip(user) or role_of(user["id"]) is not None)  # type: ignore[index]


async def add_vip_days(user_id: int, days: int) -> Any:
    """Mavjud VIP ustiga qo'shadi (manfiy bo'lsa ayiradi). Yangi muddatni qaytaradi."""
    async with db.tx():
        await ensure_exists(user_id)
        row = await db.fetchone("SELECT vip_until FROM users WHERE id = ?", (user_id,))
        now = utcnow()
        current = from_db(row["vip_until"]) if row else None
        base = current if current and current > now else now
        new_until = base + timedelta(days=days)
        if new_until <= now:
            new_until = now
        await db.execute("UPDATE users SET vip_until = ? WHERE id = ?", (to_db(new_until), user_id))
    return new_until


# ---------- hodisalar ----------

async def add_event(user_id: int | None, kind: str, meta: dict[str, Any] | None = None) -> None:
    await db.execute(
        "INSERT INTO events (user_id, kind, meta, created_at) VALUES (?, ?, ?, ?)",
        (user_id, kind, json.dumps(meta, ensure_ascii=False) if meta else None, now_db()),
    )


# ---------- tarqatish segmentlari ----------

SEGMENTS = ("all", "vip", "regular", "expired", "active", "inactive", "notify")


async def segment_ids(segment: str) -> list[int]:
    now = now_db()
    month = ago_db(days=30)
    where = {
        "all": "1",
        "vip": "vip_until > :now",
        "regular": "(vip_until IS NULL OR vip_until <= :now)",
        "expired": "vip_until IS NOT NULL AND vip_until <= :now",
        "active": "last_active >= :month",
        "inactive": "(last_active IS NULL OR last_active < :month)",
        "notify": "notify_new = 1",
    }[segment]
    rows = await db.fetchall(
        f"SELECT id FROM users WHERE is_blocked_bot = 0 AND is_banned = 0 AND {where} ORDER BY id",
        {"now": now, "month": month},
    )
    return [r["id"] for r in rows]
