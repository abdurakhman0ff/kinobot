"""Muhit o'zgaruvchilari.

Env faqat boshlang'ich qiymat beradi: ko'p sozlamalar keyin admin panel orqali
`settings` jadvalida o'zgaradi (database/settings.py).
"""
from __future__ import annotations

import os
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int | None = None) -> int | None:
    raw = _str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} butun son bo'lishi kerak") from exc


BOT_NAME = "Abdurakhmanjaan | MovieBot"

BOT_TOKEN = _str("BOT_TOKEN")
ADMIN_ID: int = _int("ADMIN_ID", 5751975734)  # type: ignore[assignment]
STORAGE_CHANNEL_ID: int = _int("STORAGE_CHANNEL_ID", -1004446986274)  # type: ignore[assignment]
BACKUP_CHANNEL_ID = _str("BACKUP_CHANNEL_ID")
PUBLIC_CHANNEL_ID = _str("PUBLIC_CHANNEL_ID")
PUBLIC_CHANNEL_URL = _str("PUBLIC_CHANNEL_URL")
SUPPORT_USERNAME = _str("SUPPORT_USERNAME").lstrip("@")
TMDB_API_KEY = _str("TMDB_API_KEY")
CLICK_PROVIDER_TOKEN = _str("CLICK_PROVIDER_TOKEN")
DB_PATH = _str("DB_PATH") or "/data/kinobot.db"

TZ = ZoneInfo("Asia/Tashkent")
