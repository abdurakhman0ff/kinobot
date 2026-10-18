"""Foydalanuvchi klaviaturalari."""
from __future__ import annotations

from typing import Any, Sequence
from urllib.parse import quote

from aiogram.types import InlineKeyboardMarkup

import texts as t
from keyboards.callbacks import Card, Nav, Op, Req, Rnd, SubCheck, Vip
from keyboards.common import NOOP, btn, chunk, kb, nav_row
from utils.text import som


def deep_link(bot_username: str, code: int) -> str:
    return f"https://t.me/{bot_username}?start=kino_{code}"


def share_url(bot_username: str, movie: dict[str, Any]) -> str:
    link = deep_link(bot_username, movie["code"])
    text = t.SHARE_TEXT.format(title=movie.get("title") or "")
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(text, safe='')}"


def start_kb() -> InlineKeyboardMarkup:
    return kb([[btn(t.BTN_SEARCH_INLINE, inline="")]])


def main_menu(vip_days: int | None, is_staff: bool) -> InlineKeyboardMarkup:
    """Asosiy menyu: IMDb qidiruv olib tashlandi, Profil eng pastga o'tkazildi."""
    vip_btn = btn(t.BTN_VIP_LEFT.format(days=vip_days) if vip_days is not None else t.BTN_VIP, Nav(to="vip"))
    rows = [
        [vip_btn, btn(t.BTN_TOP, Nav(to="top"))],
        [btn(t.BTN_FILMS, Nav(to="films")), btn(t.BTN_SERIES, Nav(to="series"))],
        [btn(t.BTN_NEW, Nav(to="new")), btn(t.BTN_RANDOM, Nav(to="random"))],
        [btn(t.BTN_FILTER, Nav(to="filter")), btn(t.BTN_SAVED, Nav(to="saved"))],
        [btn(t.BTN_REQUEST, Nav(to="req")), btn(t.BTN_PROMO, Nav(to="promo"))],
        [btn(t.BTN_HELP, Nav(to="help")), btn(t.BTN_SEARCH, inline="")],
    ]
    if is_staff:
        rows.append([btn(t.BTN_ADMIN, Nav(to="admin"))])
        
    # 👤 Profil eng pastda uzun tugma bo'lib joylashadi
    rows.append([btn(t.BTN_PROFILE, Nav(to="profile"))])
    return kb(rows)


def back_kb(back: str | None = "menu") -> InlineKeyboardMarkup:
    return kb([nav_row(Nav(to=back) if back else None)])


def subscribe_kb(items: Sequence[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = []
    for item in items:
        link = item.get("invite_link") or (f"https://t.me/{item['username']}" if item.get("username") else None)
        if link:
            rows.append([btn(f"➕ {item['title']}", url=link)])
    rows.append([btn(t.BTN_CHECK, SubCheck())])
    return kb(rows)


def not_found_kb(prefill: bool = True) -> InlineKeyboardMarkup:
    req = btn(t.BTN_REQUEST, Req(a="pf") if prefill else Nav(to="req"))
    return kb([[req], nav_row()])


def vip_offer_kb() -> InlineKeyboardMarkup:
    return kb([[btn(t.BTN_VIP_NO_WAIT, Nav(to="vip"))]])


def locked_kb() -> InlineKeyboardMarkup:
    return kb([[btn(t.BTN_GET_VIP, Nav(to="vip"))], nav_row()])


# ---------- kino kartochkasi ----------

def film_card_kb(movie: dict[str, Any], bot_username: str, saved: bool, parts: Sequence[dict[str, Any]] | None = None) -> InlineKeyboardMarkup:
    """Kino kartochkasi: Qismlar va asosiy tugmalar."""
    m = movie["id"]
    rows = []
    
    # Xatolik chiqmasligi uchun parts ro'yxat ekanligini va uzunligini xavfsiz tekshiramiz
    if parts and isinstance(parts, (list, tuple)) and len(parts) > 1:
        part_btns = [
            btn(f"{'▶️ ' if p['id'] == m else ''}{p['part_number']}-qism", Card(a="open", m=p["id"]))
            for p in parts
        ]
        rows.append(part_btns)  # [ 1-qism ] [ 2-qism ] [ 3-qism ]
        
    rows += [
        # 1-qator: Baholash va Saqlash
        [
            btn(t.BTN_RATE, Card(a="rate", m=m)), 
            btn(t.BTN_UNSAVE if saved else t.BTN_SAVE, Card(a="sv", m=m))
        ],
        # 2-qator: Do'stlarga ulashish (uzun tugma)
        [
            btn(t.BTN_SHARE, url=share_url(bot_username, movie))
        ]
    ]
    return kb(rows)


def serial_card_kb(movie: dict[str, Any], bot_username: str, seasons: Sequence[int], saved: bool,
                    cont: tuple[int, int, int] | None) -> InlineKeyboardMarkup:
    """Serial kartochkasi: Faqat Baholash | Saqlash va Ulashish tugmalari qoldi."""
    m = movie["id"]
    rows = chunk([btn(t.BTN_SEASON.format(n=s), Card(a="ss", m=m, v=s, k="s")) for s in seasons], 3)
    if cont:
        ep_id, season, number = cont
        rows.append([btn(t.BTN_CONTINUE.format(season=season, number=number), Card(a="se", m=m, v=ep_id, k="s"))])
    
    rows += [
        # 1-qator: Baholash va Saqlash
        [
            btn(t.BTN_RATE, Card(a="rate", m=m, k="s")),
            btn(t.BTN_UNSAVE if saved else t.BTN_SAVE, Card(a="sv", m=m, k="s"))
        ],
        # 2-qator: Do'stlarga ulashish (uzun tugma)
        [
            btn(t.BTN_SHARE_SHORT, url=share_url(bot_username, movie))
        ]
    ]
    return kb(rows)
                        
def movie_parts_kb(movie_id: int, parts: Sequence[dict[str, Any]]) -> InlineKeyboardMarkup:
    """2-rasmdagi kabi ko'p qismli kinoning qismlari tugmalarini yaratadi."""
    buttons = [
        btn(f"▶️ {p['part_number']}-qism", Card(a="open_part", m=movie_id, v=p["id"]))
        for p in parts
    ]
    # Qismlarni 3 tadan qilib qatorlarga bo'lamiz
    rows = chunk(buttons, 3)
    rows.append([btn(t.BTN_BACK, Nav(to="menu"))])
    return kb(rows)

EPISODES_PER_PAGE = 25


def episodes_kb(movie_id: int, season: int, eps: Sequence[dict[str, Any]], page: int, k: str,
                current_ep: int = 0) -> InlineKeyboardMarkup:
    pages = max(1, (len(eps) + EPISODES_PER_PAGE - 1) // EPISODES_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    part = eps[page * EPISODES_PER_PAGE:(page + 1) * EPISODES_PER_PAGE]
    buttons = [
        btn(("▶️ " if e["id"] == current_ep else "") + str(e["number"]),
            Card(a="se", m=movie_id, v=e["id"], k=k, e=current_ep))
        for e in part
    ]
    rows = chunk(buttons, 5)
    if pages > 1:
        rows.append([
            btn("⬅️", Card(a="ss", m=movie_id, v=season, p=page - 1, k=k, e=current_ep) if page > 0 else NOOP),
            btn(f"{page + 1}/{pages}", NOOP),
            btn("➡️", Card(a="ss", m=movie_id, v=season, p=page + 1, k=k, e=current_ep) if page < pages - 1 else NOOP),
        ])
    rows.append([btn(t.BTN_BACK, Card(a="back", m=movie_id, k=k, e=current_ep))])
    return kb(rows)


def episode_kb(movie_id: int, ep: dict[str, Any], prev_id: int | None, next_id: int | None) -> InlineKeyboardMarkup:
    row = []
    if prev_id:
        row.append(btn(t.BTN_PREV_EP, Card(a="se", m=movie_id, v=prev_id, k="e", e=ep["id"])))
    row.append(btn(t.BTN_EPISODES, Card(a="ss", m=movie_id, v=ep["season"], k="e", e=ep["id"])))
    if next_id:
        row.append(btn(t.BTN_NEXT_EP, Card(a="se", m=movie_id, v=next_id, k="e", e=ep["id"])))
    rows = [row]
    if not next_id:
        rows.append([btn(t.BTN_LAST_EP, NOOP)])
    return kb(rows)


def rating_kb(movie_id: int, k: str) -> InlineKeyboardMarkup:
    return kb([
        [btn(f"{i}⭐", Card(a="rs", m=movie_id, v=i, k=k)) for i in range(1, 6)],
        [btn(t.BTN_BACK, Card(a="back", m=movie_id, k=k))],
    ])


def comment_prompt_kb(movie_id: int) -> InlineKeyboardMarkup:
    return kb([[btn(t.BTN_SKIP, Card(a="cskip", m=movie_id))]])


def actors_kb(movie_id: int, actors: Sequence[dict[str, Any]], k: str) -> InlineKeyboardMarkup:
    rows = chunk([btn(a["name"][:30], Card(a="ac", m=movie_id, v=a["id"], k=k)) for a in actors], 2)
    rows.append([btn(t.BTN_BACK, Card(a="back", m=movie_id, k=k))])
    return kb(rows)


def movies_back_kb(movies: Sequence[dict[str, Any]], back: Card) -> InlineKeyboardMarkup:
    rows = [[btn(_short_label(m), Op(id=m["id"]))] for m in movies]
    rows.append([btn(t.BTN_BACK, back)])
    return kb(rows)


def _short_label(movie: dict[str, Any]) -> str:
    year = f" ({movie['year']})" if movie.get("year") else ""
    return f"🎬 {movie['title']}{year}{' 💎' if movie.get('is_vip') else ''}"[:60]


def report_kb(movie_id: int, episode_id: int, k: str) -> InlineKeyboardMarkup:
    rows = [[btn(reason, Card(a="rp", m=movie_id, e=episode_id, v=i, k=k))] for i, reason in enumerate(t.REPORT_REASONS)]
    rows.append([btn(t.BTN_BACK, Card(a="back", m=movie_id, k=k, e=episode_id))])
    return kb(rows)


def comments_kb(movie_id: int, page: int, pages: int, deletable: Sequence[int]) -> InlineKeyboardMarkup:
    rows = [[btn(t.BTN_DEL_COMMENT.format(n=i + 1), Card(a="cmd", m=movie_id, v=uid, p=page))]
            for i, uid in enumerate(deletable)]
    if pages > 1:
        rows.append([
            btn("⬅️", Card(a="cm", m=movie_id, p=page - 1) if page > 0 else NOOP),
            btn(f"{page + 1}/{pages}", NOOP),
            btn("➡️", Card(a="cm", m=movie_id, p=page + 1) if page < pages - 1 else NOOP),
        ])
    rows.append([btn(t.BTN_BACK, Card(a="cb", m=movie_id))])
    return kb(rows)


def random_kb(movie_id: int) -> InlineKeyboardMarkup:
    return kb([
        [btn(t.BTN_WATCH, Rnd(a="w", id=movie_id)), btn(t.BTN_RANDOM_MORE, Rnd(a="n", id=movie_id))],
        nav_row(),
    ])


def watch_url_kb(bot_username: str, code: int, text: str = t.BTN_WATCH) -> InlineKeyboardMarkup:
    return kb([[btn(text, url=deep_link(bot_username, code))]])


# ---------- VIP ----------

def tariffs_kb(tariffs: Sequence[dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[btn(t.TARIFF_BTN.format(days=x["days"], price=som(x["price_uzs"])), Vip(a="t", t=x["id"]))]
            for x in tariffs]
    rows.append(nav_row())
    return kb(rows)


def pay_methods_kb(tariff: dict[str, Any], click_enabled: bool) -> InlineKeyboardMarkup:
    rows = []
    if tariff.get("price_stars"):
        rows.append([btn(t.BTN_PAY_STARS.format(stars=tariff["price_stars"]), Vip(a="stars", t=tariff["id"]))])
    if click_enabled and tariff.get("price_uzs"):
        rows.append([btn(f"💳 Karta orqali — {som(tariff['price_uzs'])}", Vip(a="click", t=tariff["id"]))])
    rows.append(nav_row(Nav(to="vip")))
    return kb(rows)


def renew_kb() -> InlineKeyboardMarkup:
    return kb([[btn(t.BTN_RENEW, Nav(to="vip"))]])


def cancel_payment_kb() -> InlineKeyboardMarkup:
    """Rekvizitlar chiqqandagi bekor qilish tugmasi."""
    return kb([
        [btn("❌ Bekor qilish", Nav(to="vip"))]
    ])
