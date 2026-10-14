"""Ommaviy xabar tarqatish: fon vazifasi, navbat, to'xtatish, hisobot."""
from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

import texts as t
from database import users
from keyboards.callbacks import Adm
from keyboards.common import btn, kb

log = logging.getLogger(__name__)

RATE_DELAY = 0.05  # ~20 xabar/soniya
PROGRESS_EVERY = 200

Sender = Callable[[int], Awaitable[Any]]


@dataclass
class Job:
    title: str
    user_ids: list[int]
    send: Sender
    report_chat: int | None = None
    id: int = 0
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    stopped: bool = False
    progress_message_id: int | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


_ids = itertools.count(1)
_queue: asyncio.Queue[Job] = asyncio.Queue()
_jobs: dict[int, Job] = {}
_worker: asyncio.Task | None = None
_running: Job | None = None


def _progress_text(job: Job) -> str:
    return t.BROADCAST_PROGRESS.format(
        title=job.title, done=job.sent + job.blocked + job.failed, total=len(job.user_ids),
        sent=job.sent, blocked=job.blocked, failed=job.failed,
    )


async def enqueue(bot: Bot, job: Job) -> int:
    """Navbatga qo'shadi; oldinda turgan vazifalar sonini qaytaradi."""
    global _worker
    job.id = next(_ids)
    _jobs[job.id] = job
    ahead = _queue.qsize() + (1 if _running is not None else 0)
    await _queue.put(job)
    if _worker is None or _worker.done():
        _worker = asyncio.create_task(_loop(bot))
    return ahead


def stop(job_id: int) -> bool:
    job = _jobs.get(job_id)
    if not job or job.done.is_set():
        return False
    job.stopped = True
    return True


async def _loop(bot: Bot) -> None:
    global _running
    while True:
        job = await _queue.get()
        _running = job
        try:
            await _run(bot, job)
        except Exception:  # noqa: BLE001 - navbat to'xtab qolmasligi kerak
            log.exception("Tarqatishda kutilmagan xato")
        finally:
            _running = None
            job.done.set()
            _queue.task_done()
            if len(_jobs) > 50:
                for jid in [j for j, x in _jobs.items() if x.done.is_set()][:25]:
                    _jobs.pop(jid, None)


async def _send_one(job: Job, user_id: int) -> None:
    for _ in range(3):
        try:
            await job.send(user_id)
            job.sent += 1
            return
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
        except TelegramForbiddenError:
            job.blocked += 1
            await users.set_field(user_id, "is_blocked_bot", 1)
            return
        except TelegramBadRequest as exc:
            if "chat not found" in str(exc).lower():
                job.blocked += 1
                await users.set_field(user_id, "is_blocked_bot", 1)
            else:
                job.failed += 1
            return
        except TelegramAPIError:
            job.failed += 1
            return
    job.failed += 1


async def _update_progress(bot: Bot, job: Job, final: bool = False) -> None:
    if not job.report_chat:
        return
    text = _progress_text(job)
    if final:
        text = (t.BROADCAST_STOPPED if job.stopped else t.BROADCAST_DONE).format(
            title=job.title, sent=job.sent, blocked=job.blocked, failed=job.failed, total=len(job.user_ids)
        )
    markup = None if final else kb([[btn(t.BTN_STOP, Adm(a="bstop", id=job.id))]])
    try:
        if job.progress_message_id:
            await bot.edit_message_text(text, chat_id=job.report_chat, message_id=job.progress_message_id,
                                        reply_markup=markup)
        else:
            msg = await bot.send_message(job.report_chat, text, reply_markup=markup)
            job.progress_message_id = msg.message_id
    except TelegramAPIError:
        if final:
            try:
                await bot.send_message(job.report_chat, text)
            except TelegramAPIError:
                pass


async def _run(bot: Bot, job: Job) -> None:
    await _update_progress(bot, job)
    for index, user_id in enumerate(job.user_ids, 1):
        if job.stopped:
            break
        await _send_one(job, user_id)
        await asyncio.sleep(RATE_DELAY)
        if index % PROGRESS_EVERY == 0:
            await _update_progress(bot, job)
    await _update_progress(bot, job, final=True)
