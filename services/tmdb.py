"""TMDB API mijozi (aiohttp)."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any

import aiohttp

import config

log = logging.getLogger(__name__)

BASE = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/"

GENRES_UZ = {
    28: "Jangari", 12: "Sarguzasht", 16: "Animatsiya", 35: "Komediya", 80: "Kriminal",
    99: "Hujjatli", 18: "Drama", 10751: "Oilaviy", 14: "Fentezi", 36: "Tarixiy",
    27: "Qo'rqinchli", 10402: "Musiqiy", 9648: "Sirli", 10749: "Romantik",
    878: "Ilmiy fantastika", 10770: "Telefilm", 53: "Triller", 10752: "Harbiy", 37: "Vestern",
    10759: "Jangari va sarguzasht", 10762: "Bolalar", 10763: "Yangiliklar", 10764: "Realiti",
    10765: "Fantastika va fentezi", 10766: "Melodrama", 10767: "Tok-shou", 10768: "Urush va siyosat",
}

COUNTRIES_UZ = {
    "US": "AQSH", "GB": "Buyuk Britaniya", "FR": "Fransiya", "DE": "Germaniya", "IT": "Italiya",
    "ES": "Ispaniya", "RU": "Rossiya", "UZ": "O'zbekiston", "KZ": "Qozog'iston", "KR": "Janubiy Koreya",
    "KP": "Shimoliy Koreya", "JP": "Yaponiya", "CN": "Xitoy", "IN": "Hindiston", "TR": "Turkiya",
    "CA": "Kanada", "AU": "Avstraliya", "BR": "Braziliya", "MX": "Meksika", "SE": "Shvetsiya",
    "NO": "Norvegiya", "DK": "Daniya", "FI": "Finlyandiya", "PL": "Polsha", "UA": "Ukraina",
    "BY": "Belarus", "IR": "Eron", "EG": "Misr", "AE": "BAA", "SA": "Saudiya Arabistoni",
    "NZ": "Yangi Zelandiya", "IE": "Irlandiya", "BE": "Belgiya", "NL": "Niderlandiya",
    "CH": "Shveytsariya", "AT": "Avstriya", "CZ": "Chexiya", "HU": "Vengriya", "HK": "Gonkong",
    "TW": "Tayvan", "TH": "Tailand", "ID": "Indoneziya", "PH": "Filippin", "AR": "Argentina",
    "ZA": "JAR", "PK": "Pokiston", "KG": "Qirg'iziston", "TJ": "Tojikiston", "TM": "Turkmaniston",
    "AZ": "Ozarbayjon", "GE": "Gruziya", "AM": "Armaniston", "GR": "Gretsiya", "PT": "Portugaliya",
    "RO": "Ruminiya", "BG": "Bolgariya", "RS": "Serbiya", "HR": "Xorvatiya", "IL": "Isroil",
    "MY": "Malayziya", "SG": "Singapur", "VN": "Vyetnam", "CL": "Chili", "CO": "Kolumbiya",
    "IS": "Islandiya", "LT": "Litva", "LV": "Latviya", "EE": "Estoniya", "SK": "Slovakiya",
}

IMDB_RE = re.compile(r"(tt\d{5,10})")


def poster_url(path: str | None, size: str = "w500") -> str | None:
    return f"{IMG}{size}{path}" if path else None


def kind_of(movie_type: str) -> str:
    """Bizning tur -> TMDB turi."""
    return "tv" if movie_type == "serial" else "movie"


class TMDB:
    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[str, tuple[float, Any]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"Accept": "application/json"}
            # v4 "Read Access Token" (eyJ...) yoki v3 api_key ikkalasi ham qo'llanadi
            if self.api_key.startswith("eyJ"):
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def _get(self, path: str, **params: Any) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        params = {k: v for k, v in params.items() if v is not None}
        if not self.api_key.startswith("eyJ"):
            params["api_key"] = self.api_key
        key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "api_key")
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        for attempt in range(2):
            try:
                async with self._session_get().get(BASE + path, params=params) as resp:
                    if resp.status == 429 and attempt == 0:
                        await asyncio.sleep(float(resp.headers.get("Retry-After", "2")))
                        continue
                    if resp.status != 200:
                        log.warning("TMDB %s -> %s", path, resp.status)
                        return None
                    data = await resp.json()
                    if len(self._cache) > 2000:
                        self._cache.clear()
                    self._cache[key] = (time.monotonic() + 6 * 3600, data)
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                log.warning("TMDB so'rovi xato %s: %s", path, type(exc).__name__)
                return None
        return None

    async def search(self, kind: str, query: str, year: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"query": query, "language": "ru-RU", "include_adult": "false"}
        if year:
            params["year" if kind == "movie" else "first_air_date_year"] = year
        data = await self._get(f"/search/{kind}", **params)
        return (data or {}).get("results", [])

    async def details(self, kind: str, tmdb_id: int) -> dict[str, Any] | None:
        return await self._get(f"/{kind}/{tmdb_id}", language="en-US",
                               append_to_response="credits,external_ids")

    async def overview(self, kind: str, tmdb_id: int) -> str:
        for lang in ("uz-UZ", "ru-RU", "en-US"):
            data = await self._get(f"/{kind}/{tmdb_id}", language=lang)
            text = ((data or {}).get("overview") or "").strip()
            if text:
                return text
        return ""

    async def localized_title(self, kind: str, tmdb_id: int) -> str:
        data = await self._get(f"/{kind}/{tmdb_id}", language="ru-RU")
        return ((data or {}).get("title") or (data or {}).get("name") or "").strip()

    async def find_imdb(self, imdb_id: str) -> tuple[str, int] | None:
        data = await self._get(f"/find/{imdb_id}", external_source="imdb_id")
        if not data:
            return None
        if data.get("movie_results"):
            return "movie", data["movie_results"][0]["id"]
        if data.get("tv_results"):
            return "tv", data["tv_results"][0]["id"]
        return None

    async def multi_search(self, query: str) -> list[dict[str, Any]]:
        data = await self._get("/search/multi", query=query, language="ru-RU", include_adult="false")
        return [r for r in (data or {}).get("results", []) if r.get("media_type") in ("movie", "tv")]

    async def cast(self, kind: str, tmdb_id: int, limit: int = 10) -> list[dict[str, Any]]:
        data = await self.details(kind, tmdb_id)
        cast = ((data or {}).get("credits") or {}).get("cast", [])
        return [{"id": c["id"], "name": c.get("name") or "?"} for c in cast[:limit]]

    async def trailer(self, kind: str, tmdb_id: int) -> str | None:
        data = await self._get(f"/{kind}/{tmdb_id}/videos", include_video_language="uz,ru,en,null")
        videos = [v for v in (data or {}).get("results", []) if v.get("site") == "YouTube"]
        for wanted in ("Trailer", "Teaser"):
            for v in videos:
                if v.get("type") == wanted:
                    return f"https://www.youtube.com/watch?v={v['key']}"
        return None

    async def person_credits(self, person_id: int) -> tuple[list[int], list[int]]:
        data = await self._get(f"/person/{person_id}/combined_credits", language="en-US")
        movie_ids, tv_ids = [], []
        for c in (data or {}).get("cast", []):
            (tv_ids if c.get("media_type") == "tv" else movie_ids).append(c["id"])
        return movie_ids, tv_ids

    async def fields(self, kind: str, tmdb_id: int, with_overview: bool = True) -> dict[str, Any] | None:
        """Bazadagi `movies` ustunlari uchun to'ldirilgan qiymatlar."""
        data = await self.details(kind, tmdb_id)
        if not data:
            return None
        date = data.get("release_date") or data.get("first_air_date") or ""
        if kind == "movie":
            runtime = data.get("runtime")
            imdb = data.get("imdb_id") or (data.get("external_ids") or {}).get("imdb_id")
            original = data.get("original_title")
        else:
            runtimes = data.get("episode_run_time") or []
            runtime = runtimes[0] if runtimes else None
            imdb = (data.get("external_ids") or {}).get("imdb_id")
            original = data.get("original_name")
        genres = [GENRES_UZ.get(g["id"], g.get("name", "")) for g in data.get("genres", [])]
        countries = [COUNTRIES_UZ.get(c["iso_3166_1"], c.get("name", "")) for c in data.get("production_countries", [])]
        if not countries and data.get("origin_country"):
            countries = [COUNTRIES_UZ.get(c, c) for c in data["origin_country"]]
        result: dict[str, Any] = {
            "tmdb_id": tmdb_id,
            "imdb_id": imdb or None,
            "original_title": original or None,
            "year": int(date[:4]) if date[:4].isdigit() else None,
            "genres": ", ".join(g for g in genres if g) or None,
            "countries": ", ".join(c for c in countries if c) or None,
            "runtime_min": runtime or None,
            "poster_path": data.get("poster_path"),
        }
        if with_overview:
            result["description"] = await self.overview(kind, tmdb_id) or None
        return result


tmdb = TMDB(config.TMDB_API_KEY)


def result_title(item: dict[str, Any]) -> str:
    return item.get("title") or item.get("name") or item.get("original_title") or item.get("original_name") or "?"


def result_year(item: dict[str, Any]) -> int | None:
    date = item.get("release_date") or item.get("first_air_date") or ""
    return int(date[:4]) if date[:4].isdigit() else None
