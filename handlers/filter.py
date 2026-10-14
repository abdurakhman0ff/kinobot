"""Filter: Tur, Til, Yil (janr va sifat bo'yicha filter yo'q)."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup

import texts as t
from database import movies
from keyboards.callbacks import Flt, Nav, Pg
from keyboards.common import btn, chunk, kb, list_kb, nav_row, pages_of
from utils.ui import answer, render

router = Router()

PER_PAGE = 8
TYPES = ["a", "f", "s", "m"]
TYPE_NAMES = {"a": t.ALL, "f": t.TYPE_LABELS["film"], "s": t.TYPE_LABELS["serial"], "m": t.TYPE_LABELS["multfilm"]}


def _year_name(index: int) -> str:
    return movies.YEAR_RANGES[index][0] if 0 <= index < len(movies.YEAR_RANGES) else t.ALL


async def _state(f: Flt) -> tuple[str, str | None, int, list[str]]:
    langs = await movies.languages()
    lang = langs[f.l] if 0 <= f.l < len(langs) else None
    type_code = f.t if f.t in TYPES else "a"
    return type_code, lang, f.y, langs


async def main_view(f: Flt) -> tuple[str, InlineKeyboardMarkup]:
    type_code, lang, year, _ = await _state(f)
    count = await movies.filter_count(type_code, lang, year)
    text = t.FILTER_TEXT.format(type=TYPE_NAMES[type_code], lang=lang or t.ALL, year=_year_name(year))
    s = {"t": type_code, "l": f.l, "y": f.y}
    markup = kb([
        [btn(t.BTN_F_TYPE, Flt(a="t", **s)), btn(t.BTN_F_LANG, Flt(a="l", **s)), btn(t.BTN_F_YEAR, Flt(a="y", **s))],
        [btn(t.BTN_F_CLEAR, Flt(a="c")), btn(t.BTN_F_SHOW.format(n=count), Flt(a="go", **s))],
        nav_row(),
    ])
    return text, markup


async def options_view(f: Flt) -> tuple[str, InlineKeyboardMarkup]:
    _, _, _, langs = await _state(f)
    s = {"t": f.t, "l": f.l, "y": f.y}
    if f.a == "t":
        title = t.FILTER_CHOOSE_TYPE
        buttons = [btn(("✅ " if f.t == code else "") + TYPE_NAMES[code], Flt(a="st", v=i, **s))
                   for i, code in enumerate(TYPES)]
    elif f.a == "l":
        title = t.FILTER_CHOOSE_LANG
        buttons = [btn(("✅ " if f.l == -1 else "") + t.ALL, Flt(a="sl", v=-1, **s))]
        buttons += [btn(("✅ " if f.l == i else "") + name, Flt(a="sl", v=i, **s)) for i, name in enumerate(langs)]
    else:
        title = t.FILTER_CHOOSE_YEAR
        buttons = [btn(("✅ " if f.y == -1 else "") + t.ALL, Flt(a="sy", v=-1, **s))]
        buttons += [btn(("✅ " if f.y == i else "") + name, Flt(a="sy", v=i, **s))
                    for i, (name, _, _) in enumerate(movies.YEAR_RANGES)]
    rows = chunk(buttons, 2)
    rows.append([btn(t.BTN_BACK, Flt(a="show", **s))])
    return title, kb(rows)


def _encode(f: Flt) -> str:
    return f"{f.t}.{f.l}.{f.y}"


def _decode(raw: str | None) -> Flt:
    try:
        type_code, lang, year = (raw or "").split(".")
        return Flt(a="go", t=type_code, l=int(lang), y=int(year))
    except ValueError:
        return Flt(a="go")


async def results_view(f: Flt, page: int) -> tuple[str, InlineKeyboardMarkup]:
    type_code, lang, year, _ = await _state(f)
    total = await movies.filter_count(type_code, lang, year)
    pages = pages_of(total, PER_PAGE)
    page = min(max(page, 0), pages - 1)
    rows = await movies.filter_page(type_code, lang, year, page * PER_PAGE, PER_PAGE)
    text = t.FILTER_RESULTS.format(n=total) + ("" if rows else "\n\n" + t.EMPTY_LIST)
    back = Flt(a="show", t=f.t, l=f.l, y=f.y)
    return text, list_kb(rows, "flt", page, pages, _encode(f), back=back)


@router.callback_query(Nav.filter(F.to == "filter"))
async def nav_filter(callback: CallbackQuery, bot: Bot) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    text, markup = await main_view(Flt(a="show"))
    await render(bot, callback.from_user.id, callback.message, text, markup)


@router.callback_query(Flt.filter())
async def filter_action(callback: CallbackQuery, callback_data: Flt, bot: Bot) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    f = callback_data
    if f.a in ("t", "l", "y"):
        text, markup = await options_view(f)
    elif f.a == "go":
        text, markup = await results_view(f, 0)
    else:
        if f.a == "st":
            f = Flt(a="show", t=TYPES[f.v] if 0 <= f.v < len(TYPES) else "a", l=f.l, y=f.y)
        elif f.a == "sl":
            f = Flt(a="show", t=f.t, l=f.v, y=f.y)
        elif f.a == "sy":
            f = Flt(a="show", t=f.t, l=f.l, y=f.v)
        elif f.a == "c":
            f = Flt(a="show")
        text, markup = await main_view(f)
    await render(bot, callback.from_user.id, callback.message, text, markup)


@router.callback_query(Pg.filter(F.k == "flt"))
async def filter_page(callback: CallbackQuery, callback_data: Pg, bot: Bot) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    text, markup = await results_view(_decode(callback_data.x), callback_data.p)
    await render(bot, callback.from_user.id, callback.message, text, markup)
