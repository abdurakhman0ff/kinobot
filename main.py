"""Abdurakhmanjaan | MovieBot — ishga tushirish nuqtasi (long polling)."""
from __future__ import annotations

import asyncio
import logging
import os
import traceback

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

import config
import texts as t
from database import settings, users
from database.db import db
from database.migrations import migrate
from database.restore import apply_pending_restore
from handlers import build_router
from middlewares.ban import BanMiddleware
from middlewares.throttle import ThrottleMiddleware
from middlewares.user_track import UserTrackMiddleware
from services import notify, scheduler
from services.tmdb import tmdb
from utils.text import esc
from utils.ui import is_silent

log = logging.getLogger("kinobot")

ALLOWED_UPDATES = [
    "message", "callback_query", "inline_query", "pre_checkout_query", "chat_join_request", "my_chat_member",
]
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


def _where(exc: BaseException) -> str:
    """Xato yuz bergan joy (loyiha fayllari ichidagi oxirgi qator)."""
    frames = [f for f in traceback.extract_tb(exc.__traceback__) if f.filename.startswith(PROJECT_DIR)]
    if not frames:
        return "?"
    frame = frames[-1]
    return f"{os.path.relpath(frame.filename, PROJECT_DIR)}:{frame.lineno} {frame.name}"


async def on_error(event: ErrorEvent, bot: Bot) -> bool:
    exc = event.exception
    if is_silent(exc):
        return True
    update = event.update
    origin = update.message or update.callback_query or update.inline_query
    user_id = origin.from_user.id if origin and origin.from_user else None
    if isinstance(exc, TelegramForbiddenError) and user_id:
        await users.set_field(user_id, "is_blocked_bot", 1)
        return True
    log.error("Xatolik (user=%s): %s", user_id, exc, exc_info=exc)
    where = _where(exc)
    await notify.owner(
        bot,
        t.ADMIN_ERROR.format(type=type(exc).__name__, where=esc(where), user_id=user_id or "—",
                             text=esc(str(exc)[:300])),
        key=f"{type(exc).__name__}:{where}",
        every=600,
    )
    try:
        if update.callback_query:
            await update.callback_query.answer(t.ERROR_USER, show_alert=True)
        elif update.message:
            await update.message.answer(t.ERROR_USER)
    except TelegramAPIError:
        pass
    return True


async def set_commands(bot: Bot) -> None:
    await bot.set_my_commands([
        BotCommand(command="start", description=t.CMD_START),
        BotCommand(command="top", description=t.CMD_TOP),
        BotCommand(command="new", description=t.CMD_NEW),
        BotCommand(command="saved", description=t.CMD_SAVED),
        BotCommand(command="vip", description=t.CMD_VIP),
    ])


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN env o'zgaruvchisi berilmagan")

    if apply_pending_restore(config.DB_PATH):
        log.info("Zaxira baza tiklandi")
    await db.connect(config.DB_PATH)
    try:
        await migrate()
        await settings.load()
        await users.load_admins()
        await run_bot()
    finally:
        await tmdb.close()
        # aiosqlite oqimi yopilmasa jarayon tugamaydi va Railway uni qayta ishga tushira olmaydi
        await db.close()


async def run_bot() -> None:
    bot = Bot(config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML,
                                                             link_preview_is_disabled=True))
    dp = Dispatcher(storage=MemoryStorage())
    track, ban = UserTrackMiddleware(), BanMiddleware()
    for observer in (dp.message, dp.callback_query, dp.inline_query):
        observer.outer_middleware(track)
        observer.outer_middleware(ban)
    dp.message.outer_middleware(ThrottleMiddleware(0.7))
    dp.callback_query.outer_middleware(ThrottleMiddleware(0.4))
    dp.include_router(build_router())
    dp.errors.register(on_error)

    jobs = scheduler.setup(bot)
    try:
        await set_commands(bot)
        jobs.start()
        # drop_pending_updates=False: ishlamay turgan paytdagi to'lovlar yo'qolmasligi uchun
        await bot.delete_webhook(drop_pending_updates=False)
        await notify.owner(bot, t.BOT_STARTED)
        log.info("Bot ishga tushdi")
        await dp.start_polling(bot, allowed_updates=ALLOWED_UPDATES)
    finally:
        if jobs.running:
            jobs.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
