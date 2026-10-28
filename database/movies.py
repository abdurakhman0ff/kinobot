"""Kinolar, qismlar, reyting, saqlanganlar, ko'rishlar."""
from __future__ import annotations

from typing import Any

from database.db import db
from utils.text import split_csv
from utils.time import ago_db, now_db

Row = dict[str, Any]

MOVIE_FIELDS = {
    "code", "type", "title", "original_title", "year", "genres", "countries", "runtime_min",
    "quality", "languages", "description", "tmdb_id", "imdb_id", "poster_path", "poster_file_id",
    "storage_message_id", "backup_message_id", "file_id", "is_vip", "trailer_url", "price", "trailer_file_id",
}

# ro'yxatlarda kerak bo'ladigan qisqa ustunlar
SHORT = "m.id, m.code, m.type, m.title, m.year, m.is_vip, m.views"


def rating_of(movie: Row) -> float | None:
    count = movie.get("rating_count") or 0
    return round(movie["rating_sum"] / count, 2) if count else None


# ---------- kino ----------

async def get(movie_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM movies WHERE id = ?", (movie_id,))


async def by_code(code: int) -> Row | None:
    return await db.fetchone("SELECT * FROM movies WHERE code = ?", (code,))


async def next_code() -> int:
    return int(await db.fetchval("SELECT MAX(code) FROM movies", default=0)) + 1


async def code_taken(code: int, exclude_id: int | None = None) -> bool:
    return bool(await db.fetchval(
        "SELECT 1 FROM movies WHERE code = ? AND id != ?", (code, exclude_id or 0)
    ))


async def create(fields: dict[str, Any]) -> int:
    data = {k: v for k, v in fields.items() if k in MOVIE_FIELDS}
    data["created_at"] = data["updated_at"] = now_db()
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    return await db.insert(f"INSERT INTO movies ({cols}) VALUES ({marks})", tuple(data.values()))


async def update(movie_id: int, **fields: Any) -> None:
    data = {k: v for k, v in fields.items() if k in MOVIE_FIELDS}
    if not data:
        return
    data["updated_at"] = now_db()
    sets = ", ".join(f"{k} = ?" for k in data)
    await db.execute(f"UPDATE movies SET {sets} WHERE id = ?", (*data.values(), movie_id))


async def delete(movie_id: int) -> None:
    await db.execute("DELETE FROM movies WHERE id = ?", (movie_id,))


async def all_for_index() -> list[Row]:
    return await db.fetchall(
        "SELECT id, code, type, title, original_title, year, is_vip, views FROM movies"
    )


async def by_ids(ids: list[int]) -> list[Row]:
    if not ids:
        return []
    marks = ",".join("?" for _ in ids)
    rows = await db.fetchall(f"SELECT * FROM movies WHERE id IN ({marks})", ids)
    order = {mid: i for i, mid in enumerate(ids)}
    return sorted(rows, key=lambda r: order[r["id"]])


# ---------- ro'yxatlar ----------

def _type_cond(kind: str) -> str:
    return "m.type = 'serial'" if kind == "series" else "m.type != 'serial'"


async def catalog(kind: str, offset: int, limit: int) -> tuple[int, list[Row]]:
    cond = _type_cond(kind)
    total = int(await db.fetchval(f"SELECT COUNT(*) FROM movies m WHERE {cond}", default=0))
    rows = await db.fetchall(
        f"SELECT {SHORT} FROM movies m WHERE {cond} ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    return total, rows


async def newest(limit: int, offset: int = 0) -> list[Row]:
    return await db.fetchall(
        "SELECT * FROM movies m ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?", (limit, offset)
    )


async def top(period: str, offset: int, limit: int) -> tuple[int, list[Row]]:
    """period: w (hafta), m (oy), a (hammasi)."""
    if period == "a":
        total = int(await db.fetchval("SELECT COUNT(*) FROM movies WHERE views > 0", default=0))
        rows = await db.fetchall(
            f"SELECT {SHORT} FROM movies m WHERE m.views > 0 ORDER BY m.views DESC, m.id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return total, rows
    since = ago_db(days=7 if period == "w" else 30)
    total = int(await db.fetchval(
        "SELECT COUNT(DISTINCT movie_id) FROM views WHERE created_at >= ?", (since,), default=0
    ))
    rows = await db.fetchall(
        f"""SELECT {SHORT}, COUNT(v.id) AS cnt FROM views v JOIN movies m ON m.id = v.movie_id
            WHERE v.created_at >= ? GROUP BY m.id ORDER BY cnt DESC, m.id DESC LIMIT ? OFFSET ?""",
        (since, limit, offset),
    )
    return total, rows


async def top_since(since: str, limit: int) -> list[Row]:
    return await db.fetchall(
        """SELECT m.code, m.title, COUNT(v.id) AS cnt FROM views v JOIN movies m ON m.id = v.movie_id
           WHERE v.created_at >= ? GROUP BY m.id ORDER BY cnt DESC LIMIT ?""",
        (since, limit),
    )


async def random_one(exclude_id: int = 0) -> Row | None:
    row = await db.fetchone("SELECT * FROM movies WHERE id != ? ORDER BY RANDOM() LIMIT 1", (exclude_id,))
    return row or await db.fetchone("SELECT * FROM movies ORDER BY RANDOM() LIMIT 1")


# ---------- filter ----------

YEAR_RANGES: list[tuple[str, int, int]] = [
    ("2020-2026", 2020, 2026),
    ("2010-2019", 2010, 2019),
    ("2000-2009", 2000, 2009),
    ("2000 gacha", 0, 1999),
]
TYPE_CODES = {"f": "film", "s": "serial", "m": "multfilm"}


async def languages() -> list[str]:
    rows = await db.fetchall("SELECT DISTINCT languages FROM movies WHERE languages IS NOT NULL AND languages != ''")
    found: set[str] = set()
    for r in rows:
        found.update(split_csv(r["languages"]))
    return sorted(found)


def _filter_where(type_code: str, language: str | None, year_idx: int) -> tuple[str, list[Any]]:
    conds, params = ["1"], []
    if type_code in TYPE_CODES:
        conds.append("m.type = ?")
        params.append(TYPE_CODES[type_code])
    if language:
        conds.append("(',' || REPLACE(m.languages, ', ', ',') || ',') LIKE ?")
        params.append(f"%,{language},%")
    if 0 <= year_idx < len(YEAR_RANGES):
        _, lo, hi = YEAR_RANGES[year_idx]
        conds.append("m.year BETWEEN ? AND ?")
        params += [lo, hi]
    return " AND ".join(conds), params


async def filter_count(type_code: str, language: str | None, year_idx: int) -> int:
    where, params = _filter_where(type_code, language, year_idx)
    return int(await db.fetchval(f"SELECT COUNT(*) FROM movies m WHERE {where}", params, default=0))


async def filter_page(type_code: str, language: str | None, year_idx: int, offset: int, limit: int) -> list[Row]:
    where, params = _filter_where(type_code, language, year_idx)
    return await db.fetchall(
        f"SELECT {SHORT} FROM movies m WHERE {where} ORDER BY m.created_at DESC, m.id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    )


# ---------- o'xshash va TMDB ----------

async def similar(movie: Row, limit: int = 5) -> list[Row]:
    genres = set(split_csv(movie.get("genres")))
    if not genres:
        return []
    rows = await db.fetchall(
        "SELECT * FROM movies WHERE type = ? AND id != ? AND genres IS NOT NULL AND genres != ''",
        (movie["type"], movie["id"]),
    )
    scored = []
    for r in rows:
        common = len(genres & set(split_csv(r["genres"])))
        if common:
            scored.append((common, rating_of(r) or 0, r["views"], r))
    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    return [x[3] for x in scored[:limit]]


async def by_tmdb(tmdb_ids: list[int], series: bool) -> list[Row]:
    if not tmdb_ids:
        return []
    marks = ",".join("?" for _ in tmdb_ids)
    cond = "type = 'serial'" if series else "type != 'serial'"
    return await db.fetchall(
        f"SELECT * FROM movies WHERE {cond} AND tmdb_id IN ({marks}) ORDER BY views DESC", tmdb_ids
    )


async def missing_tmdb() -> list[Row]:
    return await db.fetchall("SELECT * FROM movies WHERE tmdb_id IS NULL ORDER BY id")


async def unfilled_next(after_id: int) -> Row | None:
    return await db.fetchone(
        """SELECT * FROM movies WHERE id > ? AND (type IS NULL OR type = ''
           OR languages IS NULL OR languages = '') ORDER BY id LIMIT 1""",
        (after_id,),
    )


async def unfilled_count() -> int:
    return int(await db.fetchval(
        "SELECT COUNT(*) FROM movies WHERE type IS NULL OR type = '' OR languages IS NULL OR languages = ''",
        default=0,
    ))


async def export_rows() -> list[Row]:
    return await db.fetchall(
        "SELECT code, title, type, year, languages, is_vip, views, description FROM movies ORDER BY code"
    )


# ---------- qismlar ----------

async def episode(episode_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM episodes WHERE id = ?", (episode_id,))


async def episode_by_number(movie_id: int, season: int, number: int) -> Row | None:
    return await db.fetchone(
        "SELECT * FROM episodes WHERE movie_id = ? AND season = ? AND number = ?", (movie_id, season, number)
    )


async def seasons(movie_id: int) -> list[int]:
    rows = await db.fetchall(
        "SELECT DISTINCT season FROM episodes WHERE movie_id = ? ORDER BY season", (movie_id,)
    )
    return [r["season"] for r in rows]


async def episodes(movie_id: int, season: int) -> list[Row]:
    return await db.fetchall(
        "SELECT id, season, number FROM episodes WHERE movie_id = ? AND season = ? ORDER BY number",
        (movie_id, season),
    )


async def episode_count(movie_id: int) -> int:
    return int(await db.fetchval("SELECT COUNT(*) FROM episodes WHERE movie_id = ?", (movie_id,), default=0))


async def neighbor(ep: Row, direction: int) -> Row | None:
    if direction > 0:
        return await db.fetchone(
            """SELECT * FROM episodes WHERE movie_id = ? AND (season > ? OR (season = ? AND number > ?))
               ORDER BY season, number LIMIT 1""",
            (ep["movie_id"], ep["season"], ep["season"], ep["number"]),
        )
    return await db.fetchone(
        """SELECT * FROM episodes WHERE movie_id = ? AND (season < ? OR (season = ? AND number < ?))
           ORDER BY season DESC, number DESC LIMIT 1""",
        (ep["movie_id"], ep["season"], ep["season"], ep["number"]),
    )


async def save_episode(movie_id: int, season: int, number: int, storage_id: int | None,
                       backup_id: int | None, file_id: str | None) -> bool:
    """Qism qo'shadi yoki almashtiradi. Almashtirilgan bo'lsa True."""
    existed = await episode_by_number(movie_id, season, number)
    await db.execute(
        """INSERT INTO episodes (movie_id, season, number, storage_message_id, backup_message_id, file_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (movie_id, season, number) DO UPDATE SET
             storage_message_id = excluded.storage_message_id,
             backup_message_id = excluded.backup_message_id,
             file_id = excluded.file_id""",
        (movie_id, season, number, storage_id, backup_id, file_id, now_db()),
    )
    await db.execute("UPDATE movies SET updated_at = ? WHERE id = ?", (now_db(), movie_id))
    return existed is not None


async def delete_episode(episode_id: int) -> None:
    await db.execute("DELETE FROM episodes WHERE id = ?", (episode_id,))


async def parts(movie_id: int) -> list[Row]:
    """Ko'p qismli film: 2, 3, ... qismlar (episodes jadvalida season = 0)."""
    return await db.fetchall(
        "SELECT id, number FROM episodes WHERE movie_id = ? AND season = 0 ORDER BY number", (movie_id,)
    )


# ---------- reyting va izohlar ----------

async def user_rating(user_id: int, movie_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM ratings WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))


async def set_rating(user_id: int, movie_id: int, score: int) -> None:
    async with db.tx():
        old = await user_rating(user_id, movie_id)
        if old:
            await db.execute("UPDATE ratings SET score = ?, created_at = ? WHERE user_id = ? AND movie_id = ?",
                             (score, now_db(), user_id, movie_id))
            await db.execute("UPDATE movies SET rating_sum = rating_sum + ? WHERE id = ?",
                             (score - old["score"], movie_id))
        else:
            await db.execute("INSERT INTO ratings (user_id, movie_id, score, created_at) VALUES (?, ?, ?, ?)",
                             (user_id, movie_id, score, now_db()))
            await db.execute("UPDATE movies SET rating_sum = rating_sum + ?, rating_count = rating_count + 1 WHERE id = ?",
                             (score, movie_id))


async def set_comment(user_id: int, movie_id: int, comment: str | None) -> None:
    await db.execute("UPDATE ratings SET comment = ? WHERE user_id = ? AND movie_id = ?",
                     (comment, user_id, movie_id))


async def comment_count(movie_id: int) -> int:
    return int(await db.fetchval(
        "SELECT COUNT(*) FROM ratings WHERE movie_id = ? AND comment IS NOT NULL AND comment != ''",
        (movie_id,), default=0,
    ))


async def comments(movie_id: int, offset: int, limit: int) -> list[Row]:
    return await db.fetchall(
        """SELECT r.user_id, r.score, r.comment, r.created_at, u.first_name
           FROM ratings r LEFT JOIN users u ON u.id = r.user_id
           WHERE r.movie_id = ? AND r.comment IS NOT NULL AND r.comment != ''
           ORDER BY r.created_at DESC LIMIT ? OFFSET ?""",
        (movie_id, limit, offset),
    )


# ---------- saqlanganlar ----------

async def is_saved(user_id: int, movie_id: int) -> bool:
    return bool(await db.fetchval("SELECT 1 FROM saved WHERE user_id = ? AND movie_id = ?", (user_id, movie_id)))


async def toggle_saved(user_id: int, movie_id: int) -> bool:
    """Yangi holat: True = saqlangan."""
    if await is_saved(user_id, movie_id):
        await db.execute("DELETE FROM saved WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))
        return False
    await db.execute("INSERT OR IGNORE INTO saved (user_id, movie_id, created_at) VALUES (?, ?, ?)",
                     (user_id, movie_id, now_db()))
    return True


async def saved_page(user_id: int, offset: int, limit: int) -> tuple[int, list[Row]]:
    total = int(await db.fetchval("SELECT COUNT(*) FROM saved WHERE user_id = ?", (user_id,), default=0))
    rows = await db.fetchall(
        f"""SELECT {SHORT} FROM saved s JOIN movies m ON m.id = s.movie_id
            WHERE s.user_id = ? ORDER BY s.created_at DESC LIMIT ? OFFSET ?""",
        (user_id, limit, offset),
    )
    return total, rows


# ---------- ko'rishlar va progress ----------

async def record_view(user_id: int, movie_id: int, episode_id: int | None) -> None:
    async with db.tx():
        await db.execute("INSERT INTO views (user_id, movie_id, episode_id, created_at) VALUES (?, ?, ?, ?)",
                         (user_id, movie_id, episode_id, now_db()))
        await db.execute("UPDATE movies SET views = views + 1 WHERE id = ?", (movie_id,))
        if episode_id:
            await db.execute("UPDATE episodes SET views = views + 1 WHERE id = ?", (episode_id,))


async def set_progress(user_id: int, movie_id: int, season: int, number: int) -> None:
    await db.execute(
        """INSERT INTO watch_progress (user_id, movie_id, season, episode, updated_at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (user_id, movie_id) DO UPDATE SET season = excluded.season,
             episode = excluded.episode, updated_at = excluded.updated_at""",
        (user_id, movie_id, season, number, now_db()),
    )


async def progress(user_id: int, movie_id: int) -> Row | None:
    return await db.fetchone("SELECT * FROM watch_progress WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))


async def history(user_id: int, limit: int = 20) -> list[Row]:
    return await db.fetchall(
        f"""SELECT {SHORT}, MAX(v.created_at) AS last_view FROM views v JOIN movies m ON m.id = v.movie_id
            WHERE v.user_id = ? GROUP BY m.id ORDER BY last_view DESC LIMIT ?""",
        (user_id, limit),
    )
