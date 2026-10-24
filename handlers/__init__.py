from handlers import auto_delete, buy
"""Routerlarni tartib bilan ulash. Tartib muhim: aniq holatlar umumiy matn qidiruvidan oldin."""
from aiogram import Router

from handlers import (
    delivery,
    filter,
    gifts,
    help,
    inline,
    join_requests,
    lists,
    payments,
    profile,
    promo,
    rating,
    requests,
    saved,
    search,
    start,
    vip,
)
from handlers.admin import build_router as build_admin_router


def build_router() -> Router:
    root = Router(name="root")
    root.include_routers(
        payments.router,
        start.router,
        build_admin_router(),
        join_requests.router,
        inline.router,
        delivery.router,
        rating.router,
        lists.router,
        filter.router,
        saved.router,
        profile.router,
        requests.router,
        gifts.router, buy.router, auto_delete.router,
        promo.router,
        help.router,
        vip.router,
        search.router,  # oxirida: holatsiz matn = kod yoki qidiruv
    )
    return root

