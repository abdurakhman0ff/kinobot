"""Vaqt yordamchilari: bazada UTC ("YYYY-MM-DD HH:MM:SS"), foydalanuvchiga Tashkent vaqti."""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from config import TZ

UTC = timezone.utc
DB_FMT = "%Y-%m-%d %H:%M:%S"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def to_db(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime(DB_FMT)


def now_db() -> str:
    return to_db(utcnow())


def ago_db(**delta: float) -> str:
    return to_db(utcnow() - timedelta(**delta))


def from_db(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:19].replace("T", " "), DB_FMT).replace(tzinfo=UTC)
    except ValueError:
        return None


def fmt_local(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%d.%m.%Y %H:%M")


def fmt_date(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%d.%m.%Y")


def parse_local(text: str) -> datetime | None:
    """`DD.MM.YYYY HH:MM` (Tashkent) -> UTC datetime."""
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=TZ).astimezone(UTC)
        except ValueError:
            continue
    return None


def fmt_duration(seconds: float) -> str:
    """14 soat 20 daqiqa."""
    minutes = max(1, math.ceil(seconds / 60))
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} soat")
    if minutes:
        parts.append(f"{minutes} daqiqa")
    return " ".join(parts)


def fmt_runtime(minutes: int | None) -> str:
    """112 -> 1s 52min."""
    if not minutes:
        return ""
    hours, mins = divmod(int(minutes), 60)
    if hours and mins:
        return f"{hours}s {mins}min"
    return f"{hours}s" if hours else f"{mins}min"


def days_left(until: datetime) -> int:
    return max(0, math.ceil((until - utcnow()).total_seconds() / 86400))


def local_day_start_db() -> str:
    """Bugungi kun boshi (Tashkent) UTC formatda."""
    local = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return to_db(local)
