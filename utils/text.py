"""Matn yordamchilari."""
from __future__ import annotations

import html
import re

_APOSTROPHES = "‘’ʻʼ`´′"
_TAG_RE = re.compile(r"<[^>]+>")
_NON_WORD_RE = re.compile(r"[\W_]+")


def esc(value: object) -> str:
    return "" if value is None else html.escape(str(value), quote=False)


def normalize(text: str) -> str:
    """Qidiruv uchun: kichik harf, o'/g' variantlari bir xil, tinish belgilarisiz."""
    text = text.lower().replace("ё", "е")
    for ch in _APOSTROPHES:
        text = text.replace(ch, "'")
    text = text.replace("'", "")
    return _NON_WORD_RE.sub(" ", text).strip()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def visible_len(html_text: str) -> int:
    """HTML teglarisiz uzunlik (Telegram limiti shunday hisoblanadi)."""
    return len(html.unescape(_TAG_RE.sub("", html_text)))


def som(amount: int) -> str:
    return f"{amount:,}".replace(",", " ") + " so'm"


def split_csv(value: str | None) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def parse_int(value: str | None) -> int | None:
    try:
        return int((value or "").strip())
    except ValueError:
        return None


def chat_ref(value: object) -> int | str | None:
    """Sozlamadagi kanal qiymati: -100... ID yoki @username."""
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw if raw.startswith("@") else "@" + raw
