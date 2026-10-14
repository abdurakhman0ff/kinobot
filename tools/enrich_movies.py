"""Kinolarni TMDB ma'lumotlari bilan to'ldirish (kod, nom va VIP belgisiga tegmaydi).

    python tools/enrich_movies.py --dry-run          # faqat hisobot, bazaga yozmaydi
    python tools/enrich_movies.py --csv hisobot.csv  # to'ldiradi va hisobotni saqlaydi

Ishonchi past yoki topilmagan kinolar hisobotda; ularni admin panel
"🪄 TMDB bilan to'ldirish" bo'limida qo'lda tanlash mumkin.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from database.db import db  # noqa: E402
from database.migrations import migrate  # noqa: E402
from services import enrich  # noqa: E402
from services.tmdb import tmdb  # noqa: E402


async def progress(done: int, total: int) -> None:
    print(f"  {done}/{total}...")


async def main() -> None:
    parser = argparse.ArgumentParser(description="TMDB bilan ommaviy to'ldirish")
    parser.add_argument("--dry-run", action="store_true", help="bazaga yozmasdan faqat hisobot")
    parser.add_argument("--csv", default="tmdb_report.csv", help="hisobot fayli (default: tmdb_report.csv)")
    args = parser.parse_args()
    if not tmdb.enabled:
        raise SystemExit("TMDB_API_KEY berilmagan")

    await db.connect(config.DB_PATH)
    try:
        await migrate()
        report = await enrich.run(dry_run=args.dry_run, progress=progress)
    finally:
        await tmdb.close()
        await db.close()

    with open(args.csv, "wb") as fh:
        fh.write(enrich.csv_report(report))
    mode = "dry-run" if args.dry_run else "to'ldirildi"
    print(f"Jami: {report.total} | {mode}: {len(report.filled)} | shubhali: {len(report.uncertain)} "
          f"| topilmadi: {len(report.not_found)}")
    print(f"Hisobot: {args.csv}")


if __name__ == "__main__":
    asyncio.run(main())
