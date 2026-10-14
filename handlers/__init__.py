"""Routerlarni tartib bilan ulash. Tartib muhim: aniq holatlar umumiy matn qidiruvidan oldin."""
from aiogram import Router

from handlers import (
    delivery,
    filter,
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
        promo.router,
        help.router,
        vip.router,
        search.router,  # oxirida: holatsiz matn = kod yoki qidiruv
    )
    return root

