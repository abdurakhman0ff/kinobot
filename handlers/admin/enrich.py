"""🪄 TMDB bilan ommaviy to'ldirish va shubhali natijalarni qo'lda tanlash."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile, CallbackQuery

import texts as t
from database import movies
from handlers.admin.common import RoleFilter, back_panel_kb
from keyboards.callbacks import Adm
from keyboards.common import btn
from services import enrich
from services.tmdb import tmdb
from utils.text import esc
from utils.time import utcnow
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("admin"))
router.callback_query.filter(RoleFilter("admin"))
log = logging.getLogger(__name__)

# admin -> ko'rib chiqilishi kerak bo'lgan shubhali kinolar
_review: dict[int, list[tuple[int, list[enrich.Candidate]]]] = {}
_running: set[int] = set()


@router.callback_query(Adm.filter(F.a == "enr"))
async def enrich_menu(callback: CallbackQuery, bot: Bot) -> None:
    if not tmdb.enabled:
        await render(bot, callback.from_user.id, callback.message, t.TMDB_KEY_MISSING, back_panel_kb())
        await answer(callback)
        return
    missing = len(await movies.missing_tmdb())
    rows = [[btn(t.BTN_ENRICH_RUN, Adm(a="enrgo", v="run")), btn(t.BTN_ENRICH_DRY, Adm(a="enrgo", v="dry"))]]
    if _review.get(callback.from_user.id):
        rows.append([btn(t.BTN_ENRICH_REVIEW.format(n=len(_review[callback.from_user.id])), Adm(a="enrv"))])
    await render(bot, callback.from_user.id, callback.message, t.ENRICH_MENU.format(n=missing), back_panel_kb(*rows))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "enrgo"))
async def enrich_run(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    uid = callback.from_user.id
    if uid in _running:
        await answer(callback, t.ENRICH_ALREADY, alert=True)
        return
    dry = callback_data.v == "dry"
    _running.add(uid)
    await render(bot, uid, callback.message, t.ENRICH_STARTED.format(mode=t.DRY_RUN if dry else t.REAL_RUN))
    await answer(callback)
    asyncio.create_task(_run(bot, uid, dry))


async def _run(bot: Bot, uid: int, dry: bool) -> None:
    async def progress(done: int, total: int) -> None:
        try:
            await bot.send_message(uid, t.ENRICH_PROGRESS.format(done=done, total=total))
        except TelegramAPIError:
            pass

    try:
        report = await enrich.run(dry_run=dry, progress=progress)
    except Exception:  # noqa: BLE001 - fon vazifasi
        log.exception("TMDB to'ldirish xatosi")
        await bot.send_message(uid, t.ENRICH_FAILED)
        return
    finally:
        _running.discard(uid)
    if not dry:
        _review[uid] = [(m["id"], cands) for m, cands in report.uncertain]
    text = t.ENRICH_DONE.format(
        mode=t.DRY_RUN if dry else t.REAL_RUN, total=report.total, filled=len(report.filled),
        uncertain=len(report.uncertain), not_found=len(report.not_found),
    )
    rows = [[btn(t.BTN_ENRICH_REVIEW.format(n=len(report.uncertain)), Adm(a="enrv"))]] if report.uncertain and not dry else []
    await bot.send_message(uid, text, reply_markup=back_panel_kb(*rows))
    await bot.send_document(uid, BufferedInputFile(enrich.csv_report(report),
                                                   filename=f"tmdb_hisobot_{utcnow():%Y%m%d_%H%M}.csv"))


async def _show_review(bot: Bot, uid: int, message: object = None) -> None:
    queue = _review.get(uid) or []
    while queue:
        movie = await movies.get(queue[0][0])
        if movie and not movie.get("tmdb_id"):
            break
        queue.pop(0)
    if not queue:
        _review.pop(uid, None)
        await render(bot, uid, message, t.ENRICH_REVIEW_DONE, back_panel_kb())
        return
    movie_id, cands = queue[0]
    movie = await movies.get(movie_id)
    rows = [[btn(f"{c.title} ({c.year or '—'}) · {round(c.score)}%", Adm(a="enrc", id=movie_id, v=f"{c.kind}.{c.tmdb_id}"))]
            for c in cands]
    rows.append([btn(t.BTN_SKIP, Adm(a="enrs", id=movie_id))])
    text = t.ENRICH_REVIEW_ITEM.format(left=len(queue), title=esc(movie["title"]), code=movie["code"],  # type: ignore[index]
                                       year=movie.get("year") or "—")  # type: ignore[union-attr]
    await render(bot, uid, message, text, back_panel_kb(*rows))


@router.callback_query(Adm.filter(F.a == "enrv"))
async def review(callback: CallbackQuery, bot: Bot) -> None:
    await _show_review(bot, callback.from_user.id, callback.message)
    await answer(callback)


def _drop(uid: int, movie_id: int) -> None:
    queue = _review.get(uid) or []
    _review[uid] = [x for x in queue if x[0] != movie_id]


@router.callback_query(Adm.filter(F.a == "enrc"))
async def review_choose(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    kind, _, tmdb_id = callback_data.v.partition(".")
    movie = await movies.get(callback_data.id)
    ok = bool(movie) and await enrich.apply(movie, kind, int(tmdb_id))  # type: ignore[arg-type]
    _drop(callback.from_user.id, callback_data.id)
    await answer(callback, t.SAVED_OK if ok else t.ADD_TMDB_FAILED)
    await _show_review(bot, callback.from_user.id, callback.message)


@router.callback_query(Adm.filter(F.a == "enrs"))
async def review_skip(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    _drop(callback.from_user.id, callback_data.id)
    await answer(callback)
    await _show_review(bot, callback.from_user.id, callback.message)
