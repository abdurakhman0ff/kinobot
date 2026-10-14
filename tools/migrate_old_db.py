"""Eski bot bazasini yangi SQLite bazaga ko'chirish.

Eski bot PostgreSQL ishlatgan (jadvallar: users, movies, channels, purchases).
Manba sifatida PostgreSQL URL yoki eski SQLite fayl yo'li berilishi mumkin:

    python tools/migrate_old_db.py postgresql://user:pass@host:5432/railway
    python tools/migrate_old_db.py /data/old.db
    python tools/migrate_old_db.py            # OLD_DATABASE_URL yoki DATABASE_URL env dan

Manba bazaga faqat o'qish uchun ulaniladi, undagi hech narsa o'zgarmaydi.
Takror ishga tushirish xavfsiz: mavjud kodlar va foydalanuvchilar qayta yozilmaydi.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aiosqlite  # noqa: E402

import config  # noqa: E402
from database.db import db  # noqa: E402
from database.migrations import migrate  # noqa: E402
from utils.time import now_db, to_db  # noqa: E402

MOVIE_COLS = {
    "code": ["code", "kod", "movie_code"],
    "title": ["title", "name", "nom", "movie_name"],
    "is_vip": ["is_vip", "vip", "is_paid", "paid", "pullik"],
    "storage_message_id": ["storage_message_id", "storage_msg_id", "message_id", "msg_id", "post_id"],
    "file_id": ["file_id"],
    "views": ["views", "view_count", "views_count"],
    "created_at": ["created_at", "added_at", "date"],
}
USER_COLS = {
    "id": ["id", "user_id", "telegram_id", "tg_id", "chat_id"],
    "first_name": ["first_name", "full_name", "name"],
    "username": ["username"],
    "joined_at": ["joined_at", "created_at", "date"],
    "is_blocked_bot": ["is_blocked_bot", "is_blocked", "blocked"],
}
TRUTHY = {"1", "true", "t", "vip", "yes", "ha", "pullik", "paid"}


def pick(row: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        if row.get(name) is not None:
            return row[name]
    return None


def as_bool(value: Any) -> int:
    return 1 if str(value).strip().lower() in TRUTHY else 0


def as_time(value: Any) -> str:
    if isinstance(value, datetime):
        return to_db(value)
    return str(value)[:19] if value else now_db()


async def read_postgres(dsn: str) -> dict[str, list[dict[str, Any]]]:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        tables = {r["table_name"] for r in await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        )}
        data = {}
        for name in ("movies", "users", "channels", "purchases"):
            data[name] = [dict(r) for r in await conn.fetch(f"SELECT * FROM {name}")] if name in tables else []
        return data
    finally:
        await conn.close()


async def read_sqlite(path: str) -> dict[str, list[dict[str, Any]]]:
    async with aiosqlite.connect(f"file:{path}?mode=ro", uri=True) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cur:
            tables = {r[0] for r in await cur.fetchall()}
        data = {}
        for name in ("movies", "users", "channels", "purchases"):
            if name in tables:
                async with conn.execute(f"SELECT * FROM {name}") as cur:
                    data[name] = [dict(r) for r in await cur.fetchall()]
            else:
                data[name] = []
        return data


async def import_data(data: dict[str, list[dict[str, Any]]]) -> None:
    movies_added = users_added = channels_added = skipped = 0
    for row in data["movies"]:
        code = pick(row, MOVIE_COLS["code"])
        try:
            code = int(code)
        except (TypeError, ValueError):
            skipped += 1
            continue
        added = await db.execute(
            """INSERT OR IGNORE INTO movies (code, type, title, is_vip, storage_message_id, file_id, views,
               created_at, updated_at) VALUES (?, 'film', ?, ?, ?, ?, ?, ?, ?)""",
            (
                code,
                str(pick(row, MOVIE_COLS["title"]) or ""),
                as_bool(pick(row, MOVIE_COLS["is_vip"])),
                pick(row, MOVIE_COLS["storage_message_id"]),
                pick(row, MOVIE_COLS["file_id"]),
                int(pick(row, MOVIE_COLS["views"]) or 0),
                as_time(pick(row, MOVIE_COLS["created_at"])),
                now_db(),
            ),
        )
        movies_added += added

    for row in data["users"]:
        user_id = pick(row, USER_COLS["id"])
        if user_id is None:
            continue
        added = await db.execute(
            """INSERT OR IGNORE INTO users (id, first_name, username, joined_at, last_active, is_blocked_bot)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                int(user_id),
                pick(row, USER_COLS["first_name"]),
                pick(row, USER_COLS["username"]),
                as_time(pick(row, USER_COLS["joined_at"])),
                as_time(pick(row, USER_COLS["joined_at"])),
                as_bool(pick(row, USER_COLS["is_blocked_bot"])),
            ),
        )
        users_added += added

    existing = {r["chat_id"] for r in await db.fetchall("SELECT chat_id FROM forced_items WHERE chat_id IS NOT NULL")}
    for row in data["channels"]:
        chat_id = row.get("chat_id")
        if chat_id is None or int(chat_id) in existing:
            continue
        await db.execute(
            "INSERT INTO forced_items (type, title, chat_id, invite_link, is_active, sort) VALUES ('channel', ?, ?, ?, 1, ?)",
            (row.get("title") or "Kanal", int(chat_id), row.get("link"), channels_added + 1),
        )
        channels_added += 1

    print(f"Kinolar: {movies_added} ta qo'shildi (manbada {len(data['movies'])}, kodi noto'g'ri: {skipped})")
    print(f"Foydalanuvchilar: {users_added} ta qo'shildi (manbada {len(data['users'])})")
    print(f"Majburiy obuna kanallari: {channels_added} ta qo'shildi")
    if data["purchases"]:
        # eski tizimda alohida kinolar sotilgan; yangi tizimda VIP obuna. Xaridlar manbada saqlanib qoladi.
        print(f"Eski xaridlar: {len(data['purchases'])} ta (ko'chirilmadi, manba bazada saqlanib qoladi)")
    print("Eslatma: eski kinolar turi 'film', tillari bo'sh. Admin panel -> 🧩 To'ldirilmaganlar.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Eski bazani yangi SQLite bazaga ko'chirish")
    parser.add_argument("source", nargs="?", default=os.getenv("OLD_DATABASE_URL") or os.getenv("DATABASE_URL"),
                        help="PostgreSQL URL yoki eski SQLite fayl yo'li")
    args = parser.parse_args()
    if not args.source:
        parser.error("manba ko'rsatilmagan")

    if args.source.startswith(("postgres://", "postgresql://")):
        data = await read_postgres(args.source)
    else:
        if os.path.abspath(args.source) == os.path.abspath(config.DB_PATH):
            parser.error("manba va yangi baza bir xil fayl: bunday holda bot o'zi migratsiya qiladi")
        data = await read_sqlite(args.source)

    await db.connect(config.DB_PATH)
    try:
        await migrate()
        await import_data(data)
    finally:
        await db.close()
    print(f"Tayyor. Yangi baza: {config.DB_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
