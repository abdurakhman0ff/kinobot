"""Jadval sxemalari. Ustunlar ro'yxat ko'rinishida: migratsiya yetishmaganlarini qo'shadi."""
from __future__ import annotations

import re

NOW = "(datetime('now'))"
MOVIE_FK = "INTEGER NOT NULL REFERENCES movies(id) ON DELETE CASCADE"

# jadval -> (ustunlar [(nom, e'lon)], qo'shimcha cheklovlar)
TABLES: dict[str, tuple[list[tuple[str, str]], list[str]]] = {
    "settings": ([("key", "TEXT PRIMARY KEY"), ("value", "TEXT")], []),
    "users": (
        [
            ("id", "INTEGER PRIMARY KEY"),
            ("first_name", "TEXT"),
            ("last_name", "TEXT"),
            ("username", "TEXT"),
            ("joined_at", f"TEXT DEFAULT {NOW}"),
            ("last_active", f"TEXT DEFAULT {NOW}"),
            ("is_blocked_bot", "INTEGER NOT NULL DEFAULT 0"),
            ("is_banned", "INTEGER NOT NULL DEFAULT 0"),
            ("vip_until", "TEXT"),
            ("notify_new", "INTEGER NOT NULL DEFAULT 1"),
            ("pinned_message_id", "INTEGER"),
            ("menu_message_id", "INTEGER"),
            # eslatmalar bir marta yuborilishi uchun: qaysi vip_until uchun yuborilgani
            ("vip_remind_for", "TEXT"),
            ("vip_expired_for", "TEXT"),
        ],
        [],
    ),
    "admins": (
        [
            ("user_id", "INTEGER PRIMARY KEY"),
            ("role", "TEXT NOT NULL DEFAULT 'moderator'"),
            ("added_by", "INTEGER"),
            ("added_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "movies": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("code", "INTEGER NOT NULL UNIQUE"),
            ("type", "TEXT NOT NULL DEFAULT 'film'"),
            ("title", "TEXT NOT NULL DEFAULT ''"),
            ("original_title", "TEXT"),
            ("year", "INTEGER"),
            ("genres", "TEXT"),
            ("countries", "TEXT"),
            ("runtime_min", "INTEGER"),
            ("quality", "TEXT"),
            ("languages", "TEXT"),
            ("description", "TEXT"),
            ("tmdb_id", "INTEGER"),
            ("imdb_id", "TEXT"),
            ("poster_path", "TEXT"),
            ("poster_file_id", "TEXT"),
            ("storage_message_id", "INTEGER"),
            ("backup_message_id", "INTEGER"),
            ("file_id", "TEXT"),
            ("is_vip", "INTEGER NOT NULL DEFAULT 0"),
            ("views", "INTEGER NOT NULL DEFAULT 0"),
            ("rating_sum", "INTEGER NOT NULL DEFAULT 0"),
            ("rating_count", "INTEGER NOT NULL DEFAULT 0"),
            ("trailer_url", "TEXT"),  # NULL = hali so'ralmagan, '' = topilmadi
            ("created_at", f"TEXT DEFAULT {NOW}"),
            ("updated_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "episodes": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("movie_id", MOVIE_FK),
            ("season", "INTEGER NOT NULL DEFAULT 1"),
            ("number", "INTEGER NOT NULL DEFAULT 1"),
            ("storage_message_id", "INTEGER"),
            ("backup_message_id", "INTEGER"),
            ("file_id", "TEXT"),
            ("views", "INTEGER NOT NULL DEFAULT 0"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        ["UNIQUE (movie_id, season, number)"],
    ),
    "ratings": (
        [
            ("user_id", "INTEGER NOT NULL"),
            ("movie_id", MOVIE_FK),
            ("score", "INTEGER NOT NULL"),
            ("comment", "TEXT"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        ["PRIMARY KEY (user_id, movie_id)"],
    ),
    "saved": (
        [("user_id", "INTEGER NOT NULL"), ("movie_id", MOVIE_FK), ("created_at", f"TEXT DEFAULT {NOW}")],
        ["PRIMARY KEY (user_id, movie_id)"],
    ),
    "views": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("user_id", "INTEGER NOT NULL"),
            ("movie_id", MOVIE_FK),
            ("episode_id", "INTEGER"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "watch_progress": (
        [
            ("user_id", "INTEGER NOT NULL"),
            ("movie_id", MOVIE_FK),
            ("season", "INTEGER"),
            ("episode", "INTEGER"),
            ("updated_at", f"TEXT DEFAULT {NOW}"),
        ],
        ["PRIMARY KEY (user_id, movie_id)"],
    ),
    "usage_windows": (
        [
            ("user_id", "INTEGER NOT NULL"),
            ("kind", "TEXT NOT NULL"),
            ("window_start", "TEXT"),
            ("count", "INTEGER NOT NULL DEFAULT 0"),
        ],
        ["PRIMARY KEY (user_id, kind)"],
    ),
    "usage_items": (
        [
            ("user_id", "INTEGER NOT NULL"),
            ("kind", "TEXT NOT NULL"),
            ("item_key", "TEXT NOT NULL"),
            ("window_start", "TEXT"),
        ],
        ["PRIMARY KEY (user_id, kind, item_key)"],
    ),
    "tariffs": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("days", "INTEGER NOT NULL DEFAULT 30"),
            ("price_uzs", "INTEGER NOT NULL DEFAULT 0"),
            ("price_stars", "INTEGER"),
            ("is_active", "INTEGER NOT NULL DEFAULT 1"),
            ("sort", "INTEGER NOT NULL DEFAULT 0"),
        ],
        [],
    ),
    "payments": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("user_id", "INTEGER NOT NULL"),
            ("tariff_id", "INTEGER"),
            ("method", "TEXT"),
            ("amount", "INTEGER"),
            ("currency", "TEXT"),
            ("days", "INTEGER NOT NULL DEFAULT 0"),
            ("payload", "TEXT"),
            ("telegram_charge_id", "TEXT UNIQUE"),
            ("provider_charge_id", "TEXT"),
            ("status", "TEXT NOT NULL DEFAULT 'paid'"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "promo_codes": (
        [
            ("code", "TEXT PRIMARY KEY"),
            ("days", "INTEGER NOT NULL DEFAULT 1"),
            ("max_uses", "INTEGER NOT NULL DEFAULT 1"),
            ("used_count", "INTEGER NOT NULL DEFAULT 0"),
            ("expires_at", "TEXT"),
            ("is_active", "INTEGER NOT NULL DEFAULT 1"),
            ("created_by", "INTEGER"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "promo_uses": (
        [("code", "TEXT NOT NULL"), ("user_id", "INTEGER NOT NULL"), ("used_at", f"TEXT DEFAULT {NOW}")],
        ["PRIMARY KEY (code, user_id)"],
    ),
    "forced_items": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("type", "TEXT NOT NULL DEFAULT 'channel'"),
            ("title", "TEXT NOT NULL DEFAULT ''"),
            ("chat_id", "INTEGER"),
            ("username", "TEXT"),
            ("invite_link", "TEXT"),
            ("is_active", "INTEGER NOT NULL DEFAULT 1"),
            ("sort", "INTEGER NOT NULL DEFAULT 0"),
        ],
        [],
    ),
    "join_requests": (
        [("user_id", "INTEGER NOT NULL"), ("chat_id", "INTEGER NOT NULL"), ("created_at", f"TEXT DEFAULT {NOW}")],
        ["PRIMARY KEY (user_id, chat_id)"],
    ),
    "bot_confirms": (
        [("user_id", "INTEGER NOT NULL"), ("item_id", "INTEGER NOT NULL"), ("created_at", f"TEXT DEFAULT {NOW}")],
        ["PRIMARY KEY (user_id, item_id)"],
    ),
    "pending_actions": (
        [("user_id", "INTEGER PRIMARY KEY"), ("payload", "TEXT NOT NULL DEFAULT '{}'"), ("created_at", f"TEXT DEFAULT {NOW}")],
        [],
    ),
    "requests": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("user_id", "INTEGER NOT NULL"),
            ("text", "TEXT NOT NULL DEFAULT ''"),
            ("status", "TEXT NOT NULL DEFAULT 'new'"),
            ("movie_code", "INTEGER"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "reports": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("user_id", "INTEGER NOT NULL"),
            ("movie_id", MOVIE_FK),
            ("episode_id", "INTEGER"),
            ("reason", "TEXT"),
            ("status", "TEXT NOT NULL DEFAULT 'new'"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "scheduled_posts": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("movie_id", MOVIE_FK),
            ("run_at", "TEXT NOT NULL DEFAULT ''"),
            ("status", "TEXT NOT NULL DEFAULT 'pending'"),
            ("created_by", "INTEGER"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
    "events": (
        [
            ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
            ("user_id", "INTEGER"),
            ("kind", "TEXT NOT NULL DEFAULT ''"),
            ("meta", "TEXT"),
            ("created_at", f"TEXT DEFAULT {NOW}"),
        ],
        [],
    ),
}

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_movies_created ON movies(created_at)",
    "CREATE INDEX IF NOT EXISTS ix_movies_tmdb ON movies(tmdb_id)",
    "CREATE INDEX IF NOT EXISTS ix_views_movie ON views(movie_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_views_user ON views(user_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_users_active ON users(last_active)",
    "CREATE INDEX IF NOT EXISTS ix_episodes_movie ON episodes(movie_id)",
    "CREATE INDEX IF NOT EXISTS ix_ratings_movie ON ratings(movie_id)",
    "CREATE INDEX IF NOT EXISTS ix_events_kind ON events(kind, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_payments_user ON payments(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_requests_status ON requests(status, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_reports_status ON reports(status, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_scheduled_status ON scheduled_posts(status, run_at)",
]

_STRIP_RE = re.compile(
    r"PRIMARY KEY( AUTOINCREMENT)?|UNIQUE|REFERENCES \w+\(\w+\)( ON DELETE CASCADE)?|DEFAULT \(.*\)"
)


def create_sql(name: str) -> str:
    columns, constraints = TABLES[name]
    parts = [f"{col} {decl}" for col, decl in columns] + constraints
    return f"CREATE TABLE IF NOT EXISTS {name} (\n    " + ",\n    ".join(parts) + "\n)"


def alter_decl(decl: str) -> str:
    """`ALTER TABLE ADD COLUMN` uchun xavfsiz e'lon (PK/UNIQUE/ifoda default bo'lmaydi)."""
    result = _STRIP_RE.sub("", decl)
    if "NOT NULL" in result and "DEFAULT" not in result:
        result = result.replace("NOT NULL", "")
    return " ".join(result.split())
