"""Matndagi oddiy emoji'larni premium (custom) emoji teglariga almashtirish."""
from __future__ import annotations

import re

from utils import emoji

_TAG = re.compile(r"(<[^>]*>)")
_SKIP_TAG = re.compile(r"</?\s*(code|pre|tg-emoji)\b", re.I)
_pattern: re.Pattern[str] | None = None


def _get_pattern() -> re.Pattern[str]:
    global _pattern
    if _pattern is None:
        keys = sorted(emoji.PREMIUM, key=len, reverse=True)
        _pattern = re.compile("|".join(re.escape(k) for k in keys))
    return _pattern


def premiumize(text: str) -> str:
    """HTML matndagi jadvalda bor emoji'larni <tg-emoji> bilan almashtiradi."""
    if not text or not emoji.ENABLED or not emoji.PREMIUM:
        return text
    pattern = _get_pattern()
    out: list[str] = []
    skip = 0
    for part in _TAG.split(text):
        if part.startswith("<") and part.endswith(">"):
            if _SKIP_TAG.match(part):
                skip = max(0, skip - 1) if part.startswith("</") else skip + 1
            out.append(part)
        elif skip:
            out.append(part)
        else:
            out.append(pattern.sub(
                lambda m: f'<tg-emoji emoji-id="{emoji.PREMIUM[m.group(0)]}">{m.group(0)}</tg-emoji>', part))
    return "".join(out)
