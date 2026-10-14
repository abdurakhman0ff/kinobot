"""Baza nusxasi, CSV eksport va import."""
from __future__ import annotations

import csv
import io
import logging
import os
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, FSInputFile

import texts as t
from database import movies
from database.db import db
from services import search
from utils.text import parse_int
from utils.time import fmt_local, utcnow

log = logging.getLogger(__name__)

MAX_DOC_BYTES = 49 * 1024 * 1024
CSV_HEADER = ["kod", "nom", "tur", "yil", "tillar", "vip", "korishlar", "tavsif"]
TYPE_ALIASES = {
    "film": "film", "kino": "film", "serial": "serial", "multfilm": "multfilm", "multik": "multfilm",
    "мультфильм": "multfilm", "сериал": "serial", "фильм": "film",
}
_TRUE = {"1", "ha", "vip", "true", "yes", "pullik"}
_FALSE = {"0", "yo'q", "yoq", "bepul", "false", "no", ""}


async def make_backup() -> str:
    directory = os.path.join(os.path.dirname(os.path.abspath(db.path)), "backups")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"kinobot_{utcnow():%Y%m%d_%H%M%S}.db")
    if os.path.exists(path):
        os.remove(path)
    async with db.exclusive():
        await db.conn.execute("VACUUM INTO ?", (path,))
    return path


async def send_backup(bot: Bot, chat_id: int) -> bool:
    path = await make_backup()
    try:
        size = os.path.getsize(path)
        if size > MAX_DOC_BYTES:
            await bot.send_message(chat_id, t.BACKUP_TOO_BIG.format(mb=size // (1024 * 1024)))
            return False
        await bot.send_document(
            chat_id,
            FSInputFile(path, filename=os.path.basename(path)),
            caption=t.BACKUP_CAPTION.format(time=fmt_local(utcnow())),
        )
        return True
    except TelegramAPIError as exc:
        log.warning("Backup yuborilmadi: %s", exc)
        return False
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


async def export_csv() -> BufferedInputFile:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(CSV_HEADER)
    for r in await movies.export_rows():
        writer.writerow([r["code"], r["title"], r["type"], r["year"] or "", r["languages"] or "",
                         r["is_vip"], r["views"], r["description"] or ""])
    data = buf.getvalue().encode("utf-8-sig")  # Excel o'zbekcha harflarni to'g'ri ochishi uchun
    return BufferedInputFile(data, filename=f"kinolar_{utcnow():%Y%m%d}.csv")


@dataclass
class ImportResult:
    updated: int = 0
    not_found: int = 0
    errors: int = 0


def _vip(value: str) -> int | None:
    v = value.strip().lower()
    if v in _TRUE:
        return 1
    if v in _FALSE:
        return 0
    return None


async def import_csv(raw: bytes) -> ImportResult:
    text = raw.decode("utf-8-sig", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    result = ImportResult()
    for row in reader:
        data = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        code = parse_int(data.get("kod") or data.get("code"))
        if code is None:
            result.errors += 1
            continue
        movie = await movies.by_code(code)
        if not movie:
            result.not_found += 1
            continue
        fields: dict[str, object] = {}
        if data.get("nom"):
            fields["title"] = data["nom"]
        if data.get("tur"):
            kind = TYPE_ALIASES.get(data["tur"].lower())
            if kind:
                fields["type"] = kind
        if data.get("yil"):
            year = parse_int(data["yil"])
            if year:
                fields["year"] = year
        if "tillar" in data:
            fields["languages"] = data["tillar"] or None
        if "vip" in data:
            vip = _vip(data["vip"])
            if vip is not None:
                fields["is_vip"] = vip
        if data.get("tavsif"):
            fields["description"] = data["tavsif"]
        if fields:
            await movies.update(movie["id"], **fields)
            result.updated += 1
    search.invalidate()
    return result
