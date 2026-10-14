"""Admin routerlari (har biri o'z rol filtri bilan)."""
from aiogram import Router

from handlers.admin import (
    add_movie,
    backup,
    broadcast,
    edit_movie,
    enrich,
    episodes,
    forced,
    moderation,
    owner,
    panel,
    stats,
    unfilled,
)


def build_router() -> Router:
    router = Router(name="admin")
    router.include_routers(
        panel.router,
        add_movie.router,
        episodes.router,
        edit_movie.router,
        stats.router,
        broadcast.router,
        moderation.router,
        unfilled.router,
        enrich.router,
        owner.router,
        forced.router,
        backup.router,
    )
    return router
