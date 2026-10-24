"""Bot ishga tushganda avto-o'chirish tsiklini yoqadi."""
from __future__ import annotations

from aiogram import Bot, Router

from services import autodelete

router = Router()


@router.startup()
async def on_startup(bot: Bot) -> None:
    autodelete.start(bot)
