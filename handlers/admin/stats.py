"""📊 Statistika."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

import texts as t
from database import movies, stats
from handlers.admin.common import RoleFilter, back_panel_kb
from keyboards.callbacks import Adm
from keyboards.common import btn
from utils.text import esc, som
from utils.time import ago_db
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("admin"))
router.callback_query.filter(RoleFilter("admin"))


async def stats_text() -> str:
    s = await stats.summary()
    lines = [t.STATS_MAIN.format(**s)]
    revenue = await stats.revenue_by_month()
    if revenue:
        lines.append(t.STATS_REVENUE)
        for r in revenue:
            amount = som(r["total"]) if r["currency"] == "UZS" else f"{r['total']} ⭐"
            lines.append(f"  {r['month']}: {amount} ({r['cnt']})")
    for days, title in ((7, t.STATS_TOP7), (30, t.STATS_TOP30)):
        top = await movies.top_since(ago_db(days=days), 10)
        if top:
            lines.append(title)
            lines += [f"  {i}. {esc(m['title'])} [{m['code']}] — {m['cnt']}" for i, m in enumerate(top, 1)]
    return "\n".join(lines)


@router.callback_query(Adm.filter(F.a == "st"))
async def show_stats(callback: CallbackQuery, bot: Bot) -> None:
    await render(bot, callback.from_user.id, callback.message, await stats_text(),
                 back_panel_kb([btn(t.BTN_REFRESH, Adm(a="st"))]))
    await answer(callback)
