"""Katalog bo'yicha nom qidiruvi (xotiradagi indeks + rapidfuzz)."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from database import movies
from utils.text import normalize

FUZZY_MIN = 70


@dataclass(slots=True)
class Entry:
    id: int
    code: int
    type: str
    title: str
    year: int | None
    is_vip: int
    views: int
    keys: tuple[str, ...]


_index: list[Entry] | None = None
_lock = asyncio.Lock()


def invalidate() -> None:
    global _index
    _index = None


async def _get_index() -> list[Entry]:
    global _index
    if _index is not None:
        return _index
    async with _lock:
        if _index is None:
            rows = await movies.all_for_index()
            _index = [
                Entry(
                    id=r["id"], code=r["code"], type=r["type"], title=r["title"] or "",
                    year=r["year"], is_vip=r["is_vip"], views=r["views"] or 0,
                    keys=tuple(k for k in (normalize(r["title"] or ""), normalize(r["original_title"] or "")) if k),
                )
                for r in rows
            ]
    return _index


async def search(query: str, limit: int = 200) -> list[Entry]:
    """Aniq moslik -> qisman moslik -> yaqin moslik (ball >= 70)."""
    q = normalize(query)
    if not q:
        return []
    index = await _get_index()
    exact, partial, seen = [], [], set()
    for e in index:
        if q in e.keys:
            exact.append(e)
            seen.add(e.id)
        elif any(q in k for k in e.keys) or (len(q) >= 3 and any(k in q for k in e.keys if len(k) >= 3)):
            partial.append(e)
            seen.add(e.id)
    exact.sort(key=lambda e: -e.views)
    partial.sort(key=lambda e: -e.views)

    choices = {i: " | ".join(e.keys) for i, e in enumerate(index) if e.id not in seen and e.keys}
    fuzzy = process.extract(q, choices, scorer=fuzz.WRatio, score_cutoff=FUZZY_MIN, limit=limit)
    fuzzy_entries = [index[key] for _, _, key in sorted(fuzzy, key=lambda x: (-x[1], -index[x[2]].views))]
    return (exact + partial + fuzzy_entries)[:limit]
