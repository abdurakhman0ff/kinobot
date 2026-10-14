"""💾 Backup, /export, /import (faqat asosiy admin)."""
from __future__ import annotations

import io

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from handlers.admin.common import RoleFilter, back_panel_kb, cancel_kb
from keyboards.callbacks import Adm
from keyboards.common import btn
from services import backup
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("owner"))
router.callback_query.filter(RoleFilter("owner"))

MAX_IMPORT_BYTES = 10 * 1024 * 1024


class ImportForm(StatesGroup):
    file = State()


@router.callback_query(Adm.filter(F.a == "bak"), StateFilter("*"))
async def backup_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    await render(bot, callback.from_user.id, callback.message, t.BACKUP_MENU, back_panel_kb(
        [btn(t.BTN_BACKUP_NOW, Adm(a="bk"))],
        [btn(t.BTN_EXPORT, Adm(a="exp")), btn(t.BTN_IMPORT, Adm(a="imp"))],
    ))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "bk"))
async def backup_now(callback: CallbackQuery, bot: Bot) -> None:
    await answer(callback, t.BACKUP_WAIT)
    if not await backup.send_backup(bot, callback.from_user.id):
        await bot.send_message(callback.from_user.id, t.BACKUP_FAILED)


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    await message.answer_document(await backup.export_csv(), caption=t.EXPORT_CAPTION)


@router.callback_query(Adm.filter(F.a == "exp"))
async def export_cb(callback: CallbackQuery, bot: Bot) -> None:
    await answer(callback)
    await bot.send_document(callback.from_user.id, await backup.export_csv(), caption=t.EXPORT_CAPTION)


@router.message(Command("import"), StateFilter("*"))
async def cmd_import(message: Message, state: FSMContext) -> None:
    await state.set_state(ImportForm.file)
    await message.answer(t.IMPORT_SEND, reply_markup=cancel_kb())


@router.callback_query(Adm.filter(F.a == "imp"))
async def import_cb(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.set_state(ImportForm.file)
    await render(bot, callback.from_user.id, callback.message, t.IMPORT_SEND, cancel_kb())
    await answer(callback)


@router.message(ImportForm.file, F.document)
async def import_file(message: Message, state: FSMContext, bot: Bot) -> None:
    doc = message.document
    if not doc or not (doc.file_name or "").lower().endswith(".csv") or (doc.file_size or 0) > MAX_IMPORT_BYTES:
        await message.answer(t.IMPORT_BAD_FILE)
        return
    buf = io.BytesIO()
    await bot.download(doc, destination=buf)
    await state.clear()
    result = await backup.import_csv(buf.getvalue())
    await message.answer(t.IMPORT_DONE.format(updated=result.updated, not_found=result.not_found,
                                              errors=result.errors), reply_markup=back_panel_kb())
