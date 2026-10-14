"""Kinolarni TMDB ma'lumotlari bilan ommaviy to'ldirish.

Kod, nom va VIP belgisiga tegilmaydi. Faqat bo'sh maydonlar to'ldiriladi
(tmdb_id, imdb_id doim yoziladi).
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from rapidfuzz import fuzz

from database import movies
from services import search
from services.tmdb import kind_of, result_title, result_year, tmdb
from utils.text import normalize

log = logging.getLogger(__name__)

AUTO_SCORE = 85
REQUEST_DELAY = 0.3

Row = dict[str, Any]


@dataclass
class Candidate:
    tmdb_id: int
    kind: str
    title: str
    year: int | None
    score: float


@dataclass
class Report:
    total: int = 0
    filled: list[tuple[Row, Candidate]] = field(default_factory=list)
    uncertain: list[tuple[Row, list[Candidate]]] = field(default_factory=list)
    not_found: list[Row] = field(default_factory=list)


def score(movie: Row, item: dict[str, Any]) -> float:
    own = normalize(movie.get("title") or "")
    names = {item.get(k) for k in ("title", "original_title", "name", "original_name")} - {None, ""}
    best = max((fuzz.ratio(own, normalize(str(n))) for n in names), default=0.0)
    year = result_year(item)
    if movie.get("year") and year and abs(int(movie["year"]) - year) > 1:
        best -= 15
    return best


async def candidates(movie: Row) -> list[Candidate]:
    kind = kind_of(movie.get("type") or "film")
    results = await tmdb.search(kind, movie["title"], movie.get("year"))
    if not results and movie.get("year"):
        results = await tmdb.search(kind, movie["title"])
    scored = [
        Candidate(r["id"], kind, result_title(r), result_year(r), score(movie, r))
        for r in results[:10]
    ]
    return sorted(scored, key=lambda c: -c.score)


async def apply(movie: Row, kind: str, tmdb_id: int) -> bool:
    fields = await tmdb.fields(kind, tmdb_id)
    if not fields:
        return False
    update: dict[str, Any] = {"tmdb_id": tmdb_id, "imdb_id": fields.get("imdb_id") or movie.get("imdb_id")}
    for key in ("original_title", "year", "genres", "countries", "runtime_min", "poster_path", "description"):
        if not movie.get(key) and fields.get(key):
            update[key] = fields[key]
    await movies.update(movie["id"], **update)
    search.invalidate()
    return True


async def run(dry_run: bool = False,
              progress: Callable[[int, int], Awaitable[None]] | None = None) -> Report:
    report = Report()
    rows = await movies.missing_tmdb()
    report.total = len(rows)
    for index, movie in enumerate(rows, 1):
        if not (movie.get("title") or "").strip():
            report.not_found.append(movie)
            continue
        found = await candidates(movie)
        good = [c for c in found if c.score >= AUTO_SCORE]
        if len(good) == 1:
            ok = True if dry_run else await apply(movie, good[0].kind, good[0].tmdb_id)
            if ok:
                report.filled.append((movie, good[0]))
            else:
                report.uncertain.append((movie, found[:3]))
        elif found:
            report.uncertain.append((movie, found[:3]))
        else:
            report.not_found.append(movie)
        if progress and index % 25 == 0:
            await progress(index, report.total)
        await asyncio.sleep(REQUEST_DELAY)
    return report


def csv_report(report: Report) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["holat", "kod", "nom", "tmdb_id", "tmdb_nomi", "yil", "ball"])
    for movie, c in report.filled:
        writer.writerow(["to'ldirildi", movie["code"], movie["title"], c.tmdb_id, c.title, c.year or "", round(c.score)])
    for movie, cands in report.uncertain:
        for c in cands:
            writer.writerow(["shubhali", movie["code"], movie["title"], c.tmdb_id, c.title, c.year or "", round(c.score)])
    for movie in report.not_found:
        writer.writerow(["topilmadi", movie["code"], movie["title"], "", "", "", ""])
    return buf.getvalue().encode("utf-8-sig")
