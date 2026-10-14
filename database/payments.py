"""Tariflar, to'lovlar, promo-kodlar."""
from __future__ import annotations

from typing import Any

from database.db import db
from utils.time import now_db

Row = dict[str, Any]


# ---------- tariflar ----------

async def tariffs(active_only: bool = True) -> list[Row]:
    cond = "WHERE is_active = 1" if active_only else ""
    return await db.fetchall(f"SELECT * FROM tariffs {cond} ORDER BY sort, days")


async def tariff(tariff_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM tariffs WHERE id = ?", (tariff_id,))


async def add_tariff(days: int, price_uzs: int, price_stars: int | None) -> int:
    sort = int(await db.fetchval("SELECT MAX(sort) FROM tariffs", default=0)) + 1
    return await db.insert(
        "INSERT INTO tariffs (days, price_uzs, price_stars, is_active, sort) VALUES (?, ?, ?, 1, ?)",
        (days, price_uzs, price_stars, sort),
    )


async def update_tariff(tariff_id: int, **fields: Any) -> None:
    allowed = {k: v for k, v in fields.items() if k in {"days", "price_uzs", "price_stars", "is_active", "sort"}}
    if not allowed:
        return
    sets = ", ".join(f"{k} = ?" for k in allowed)
    await db.execute(f"UPDATE tariffs SET {sets} WHERE id = ?", (*allowed.values(), tariff_id))


# ---------- to'lovlar ----------

async def payment_exists(charge_id: str) -> bool:
    return bool(await db.fetchval("SELECT 1 FROM payments WHERE telegram_charge_id = ?", (charge_id,)))


async def add_payment(**fields: Any) -> int | None:
    """Dublikat bo'lsa None (telegram_charge_id UNIQUE)."""
    fields.setdefault("created_at", now_db())
    cols = ", ".join(fields)
    marks = ", ".join("?" for _ in fields)
    before = await payment_exists(fields["telegram_charge_id"])
    if before:
        return None
    pid = await db.insert(f"INSERT OR IGNORE INTO payments ({cols}) VALUES ({marks})", tuple(fields.values()))
    return pid or None


async def payment_by_charge(user_id: int, charge_id: str) -> Row | None:
    return await db.fetchone(
        "SELECT * FROM payments WHERE user_id = ? AND telegram_charge_id = ?", (user_id, charge_id)
    )


async def set_payment_status(payment_id: int, status: str) -> None:
    await db.execute("UPDATE payments SET status = ? WHERE id = ?", (status, payment_id))


# ---------- promo-kodlar ----------

async def promo(code: str) -> Row | None:
    return await db.fetchone("SELECT * FROM promo_codes WHERE code = ? COLLATE NOCASE", (code,))


async def promo_used(code: str, user_id: int) -> bool:
    return bool(await db.fetchval(
        "SELECT 1 FROM promo_uses WHERE code = ? AND user_id = ?", (code, user_id)
    ))


async def use_promo(code: str, user_id: int) -> bool:
    """Atomar: limit va qayta ishlatishni tekshirib, foydalanishni yozadi."""
    async with db.tx():
        row = await db.fetchone("SELECT * FROM promo_codes WHERE code = ?", (code,))
        if not row or not row["is_active"] or row["used_count"] >= row["max_uses"]:
            return False
        if await promo_used(code, user_id):
            return False
        await db.execute("INSERT INTO promo_uses (code, user_id, used_at) VALUES (?, ?, ?)", (code, user_id, now_db()))
        await db.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
    return True


async def create_promo(code: str, days: int, max_uses: int, expires_at: str | None, created_by: int) -> bool:
    if await promo(code):
        return False
    await db.execute(
        """INSERT INTO promo_codes (code, days, max_uses, used_count, expires_at, is_active, created_by, created_at)
           VALUES (?, ?, ?, 0, ?, 1, ?, ?)""",
        (code, days, max_uses, expires_at, created_by, now_db()),
    )
    return True


async def promos() -> list[Row]:
    return await db.fetchall("SELECT * FROM promo_codes ORDER BY created_at DESC LIMIT 50")


async def delete_promo(code: str) -> None:
    await db.execute("DELETE FROM promo_codes WHERE code = ?", (code,))
