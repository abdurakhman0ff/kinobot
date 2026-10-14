"""`settings` jadvali (keshlangan)."""
from __future__ import annotations

from database.db import db

_cache: dict[str, str] = {}


async def load() -> None:
    rows = await db.fetchall("SELECT key, value FROM settings")
    _cache.clear()
    _cache.update({r["key"]: r["value"] or "" for r in rows})


def get(key: str, default: str = "") -> str:
    return _cache.get(key, default) or default


def get_int(key: str, default: int = 0) -> int:
    try:
        return int(_cache.get(key) or default)
    except ValueError:
        return default


async def set_value(key: str, value: str) -> None:
    await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    _cache[key] = value
