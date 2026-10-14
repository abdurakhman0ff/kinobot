"""Callback ma'lumotlari (qisqa prefikslar: 64 baytdan kam)."""
from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class Nav(CallbackData, prefix="nv"):
    """Menyu bo'limlari: menu, vip, top, new, films, series, random, filter, saved, imdb,
    profile, history, notify, req, promo, help, howto, paysup, admin."""
    to: str


class Pg(CallbackData, prefix="pg"):
    """Sahifalash: k = ro'yxat turi, p = sahifa, x = qo'shimcha (davr, filter holati)."""
    k: str
    p: int = 0
    x: str | None = None  # bo'sh satr callback'da None bo'lib qaytadi


class Op(CallbackData, prefix="op"):
    """Ro'yxatdan kino/serialni ochish."""
    id: int


class Card(CallbackData, prefix="cd"):
    """Kartochka amallari. k: f = film xabari, s = serial kartochkasi, e = qism xabari."""
    a: str
    m: int
    e: int = 0
    v: int = 0
    p: int = 0
    k: str = "f"


class Flt(CallbackData, prefix="ft"):
    """Filter: a = amal, t = tur (a/f/s/m), l = til indeksi, y = yil indeksi, v = tanlangan qiymat."""
    a: str
    t: str = "a"
    l: int = -1
    y: int = -1
    v: int = -1


class Rnd(CallbackData, prefix="rn"):
    a: str
    id: int = 0


class Vip(CallbackData, prefix="vp"):
    """a: t (tarif tanlash), stars, click."""
    a: str
    t: int = 0


class Req(CallbackData, prefix="rq"):
    """a: pf (oldindan to'ldirilgan so'rov), ok, no, skip (admin)."""
    a: str
    id: int = 0


class SubCheck(CallbackData, prefix="sb"):
    a: str = "check"


class Adm(CallbackData, prefix="ad"):
    """Admin panel amallari."""
    a: str
    id: int = 0
    v: str | None = None
