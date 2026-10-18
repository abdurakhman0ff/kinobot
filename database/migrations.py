"""Moslashuvchan migratsiya.

Qoidalar: eski ma'lumot hech qachon o'chmaydi. Yetishmagan jadval va ustunlar qo'shiladi
(`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN`). Eski ustun nomlari
(`kod`, `nom`, `vip`, `msg_id` ...) `PRAGMA table_info` orqali aniqlanib, yangi ustunlarga ko'chiriladi.

Agar eski `movies`/`users` jadvalida butun sonli `id` PRIMARY KEY bo'lmasa (masalan PK = kod),
uni ALTER bilan tuzatib bo'lmaydi: jadval `<nom>_legacy_<vaqt>` ga qayta nomlanadi (ma'lumot
joyida qoladi) va yangi jadvalga nusxa olinadi.
"""
from __future__ import annotations

import logging
import sqlite3

import config
from database.db import db
from database.schema import INDEXES, TABLES, alter_decl, create_sql
from utils.time import utcnow

log = logging.getLogger(__name__)

# yangi ustun -> eski bazada uchrashi mumkin bo'lgan nomlar (birinchi topilgani olinadi)
ALIASES: dict[str, dict[str, list[str]]] = {
    "movies": {
        "code": ["code", "kod", "movie_code"],
        "title": ["title", "name", "nom", "movie_name"],
        "is_vip": ["is_vip", "vip", "is_paid", "paid", "pullik"],
        "storage_message_id": ["storage_message_id", "message_id", "msg_id", "storage_msg_id", "post_id"],
        "file_id": ["file_id"],
        "views": ["views", "view_count", "views_count"],
        "created_at": ["created_at", "added_at", "date"],
    },
    "users": {
        "id": ["id", "user_id", "telegram_id", "tg_id", "chat_id"],
        "first_name": ["first_name", "full_name", "name"],
        "last_name": ["last_name"],
        "username": ["username"],
        "joined_at": ["joined_at", "created_at", "date"],
        "is_blocked_bot": ["is_blocked_bot", "is_blocked", "blocked"],
        "is_banned": ["is_banned", "banned"],
    },
}

_TRUTHY = "('1','true','vip','yes','ha','pullik','paid','t')"


def _expr(table: str, target: str, source: str) -> str:
    if target == "is_vip":
        return f"CASE WHEN lower(trim(CAST({source} AS TEXT))) IN {_TRUTHY} THEN 1 ELSE 0 END"
    if target in ("is_blocked_bot", "is_banned"):
        return f"CASE WHEN lower(trim(CAST({source} AS TEXT))) IN {_TRUTHY} THEN 1 ELSE 0 END"
    if target == "code":
        # raqam bo'lmagan kodlar vaqtincha manfiy (noyob) qiymat oladi, keyin yangi kod beriladi
        return f"CASE WHEN CAST({source} AS INTEGER) > 0 THEN CAST({source} AS INTEGER) ELSE -rowid END"
    if target in ("id", "storage_message_id", "views"):
        return f"CAST({source} AS INTEGER)"
    if target == "title":
        return f"COALESCE(CAST({source} AS TEXT), '')"
    if target in ("created_at", "joined_at"):
        return f"COALESCE({source}, datetime('now'))"
    return source


async def _columns(table: str) -> dict[str, dict]:
    rows = await db.fetchall(f"PRAGMA table_info({table})")
    return {r["name"]: r for r in rows}


def _has_int_id_pk(cols: dict[str, dict]) -> bool:
    col = cols.get("id")
    return bool(col and col["pk"] == 1 and str(col["type"]).upper() == "INTEGER")


async def _flag(key: str) -> bool:
    return bool(await db.fetchval("SELECT value FROM settings WHERE key = ?", (key,)))


async def _set_flag(key: str) -> None:
    await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, '1')", (key,))


async def _rebuild(table: str, cols: dict[str, dict]) -> None:
    legacy = f"{table}_legacy_{utcnow():%Y%m%d%H%M%S}"
    log.warning("%s jadvali mos emas: %s ga qayta nomlanib, yangisiga ko'chiriladi", table, legacy)
    await db.execute(f"ALTER TABLE {table} RENAME TO {legacy}")
    await db.execute(create_sql(table))
    targets, exprs = [], []
    for target, names in ALIASES[table].items():
        source = next((n for n in names if n in cols), None)
        if source:
            targets.append(target)
            exprs.append(_expr(table, target, source))
    if table == "movies":
        targets.append("type")
        exprs.append("'film'")
    if not targets:
        return
    copied = await db.execute(
        f"INSERT OR IGNORE INTO {table} ({', '.join(targets)}) SELECT {', '.join(exprs)} FROM {legacy}"
    )
    log.warning("%s: %s ta qator ko'chirildi (eski jadval saqlanib qoldi: %s)", table, copied, legacy)


async def _fill_aliases(table: str, before: dict[str, dict]) -> None:
    """Moslashgan jadvalda eski ustumdagi qiymatlarni yangi ustunga bir marta ko'chirish."""
    flag = f"migrated_aliases_{table}"
    if table not in ALIASES or await _flag(flag):
        return
    for target, names in ALIASES[table].items():
        source = next((n for n in names if n in before and n != target), None)
        if not source or target == "id":
            continue
        if target in before:
            # ustun oldin ham bo'lgan: faqat bo'sh joylarni to'ldiramiz
            cond = f"{target} IS NULL" if target not in ("is_vip", "views") else f"{target} = 0"
        else:
            cond = "1"
        await db.execute(f"UPDATE {table} SET {target} = {_expr(table, target, source)} WHERE {cond}")
    await _set_flag(flag)


async def _ensure_movie_codes() -> None:
    """Kodi yo'q kinolarga yangi kod beradi va kodni noyob qiladi."""
    rows = await db.fetchall("SELECT id FROM movies WHERE code IS NULL OR code <= 0 ORDER BY id")
    if rows:
        next_code = int(await db.fetchval("SELECT MAX(code) FROM movies", default=0)) + 1
        for row in rows:
            await db.execute("UPDATE movies SET code = ? WHERE id = ?", (next_code, row["id"]))
            next_code += 1
    try:
        await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_movies_code ON movies(code)")
    except sqlite3.IntegrityError:
        log.error("movies.code da dublikatlar bor: noyob indeks o'rniga oddiy indeks yaratildi")
        await db.execute("CREATE INDEX IF NOT EXISTS ix_movies_code ON movies(code)")


async def _ensure_table(table: str) -> None:
    cols = await _columns(table)
    if not cols:
        await db.execute(create_sql(table))
        return
    if table in ("movies", "users") and not _has_int_id_pk(cols):
        await _rebuild(table, cols)
        return
    for col, decl in TABLES[table][0]:
        if col not in cols:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {alter_decl(decl)}")
            log.info("%s.%s ustuni qo'shildi", table, col)
    await _fill_aliases(table, cols)
    # ALTER orqali qo'shilgan vaqt ustunlarida default bo'lmaydi
    for col, decl in TABLES[table][0]:
        if "datetime('now')" in decl:
            await db.execute(f"UPDATE {table} SET {col} = datetime('now') WHERE {col} IS NULL")


async def _seed() -> None:
    defaults = {
        "movie_limit": "3",
        "series_limit": "3",
        "window_hours": "24",
        "support_username": config.SUPPORT_USERNAME,
        "public_channel_url": config.PUBLIC_CHANNEL_URL,
        "public_channel_id": config.PUBLIC_CHANNEL_ID,
        "backup_channel_id": config.BACKUP_CHANNEL_ID,
    }
    await db.executemany(
        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", list(defaults.items())
    )
    if not await db.fetchval("SELECT COUNT(*) FROM tariffs", default=0):
        await db.executemany(
            "INSERT INTO tariffs (days, price_uzs, price_stars, is_active, sort) VALUES (?, ?, ?, 1, ?)",
            [(10, 9000, None, 1), (30, 29000, 100, 2), (90, 99000, 200, 3)],
        )
    # eski kinolar: tur film, tillar bo'sh qoladi ("Noma'lum")
    await db.execute("UPDATE movies SET type = 'film' WHERE type IS NULL OR type = ''")


async def migrate() -> None:
    # 1. Asosiy jadvallarni tekshirish va yaratish/yangilash
    for table in TABLES:
        await _ensure_table(table)
    
    # 2. movie_parts jadvalini yaratish (franshiza/qismlar uchun)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS movie_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id INTEGER NOT NULL,
            part_number INTEGER NOT NULL,
            file_id TEXT NOT NULL,
            storage_message_id INTEGER,
            backup_message_id INTEGER,
            created_at TEXT,
            FOREIGN KEY (movie_id) REFERENCES movies(id) ON DELETE CASCADE
        );
    """)

    await _ensure_movie_codes()
    for sql in INDEXES:
        await db.execute(sql)
    await _seed()
    log.info("Migratsiya tugadi")
