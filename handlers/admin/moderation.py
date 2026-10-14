"""🚫 Bloklash, 📝 So'rovlar, ⚠️ Shikoyatlar, 🗓 Rejalashtirilgan postlar, 🎁 Promo-kodlar."""
from __future__ import annotations

import secrets
import string

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import misc, payments, users
from handlers.admin.common import RoleFilter, back_panel_kb, cancel_kb
from handlers.requests import admin_request_kb, request_admin_text
from keyboards.callbacks import Adm, Op
from keyboards.common import btn
from utils.text import esc, parse_int
from utils.time import fmt_date, fmt_local, from_db, parse_local, to_db
from utils.ui import answer, render

router = Router()
router.message.filter(RoleFilter("moderator"))
router.callback_query.filter(RoleFilter("moderator"))


class BanForm(StatesGroup):
    user_id = State()


class PromoCreate(StatesGroup):
    code = State()
    days = State()
    uses = State()
    expires = State()


def _admin_only(user_id: int) -> bool:
    return users.has_role(user_id, "admin")


# ---------- so'rovlar va shikoyatlar (moderator) ----------

@router.callback_query(Adm.filter(F.a == "rq"))
async def requests_list(callback: CallbackQuery, bot: Bot) -> None:
    rows = await misc.open_requests()
    await render(bot, callback.from_user.id, callback.message,
                 t.REQUESTS_TITLE.format(n=len(rows)) if rows else t.REQUESTS_EMPTY, back_panel_kb())
    for r in rows:
        user = await users.get(r["user_id"])
        await bot.send_message(callback.from_user.id, request_admin_text(r, user), reply_markup=admin_request_kb(r["id"]))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "rp"))
async def reports_list(callback: CallbackQuery, bot: Bot) -> None:
    rows = await misc.open_reports()
    await render(bot, callback.from_user.id, callback.message,
                 t.REPORTS_TITLE.format(n=len(rows)) if rows else t.REPORTS_EMPTY, back_panel_kb())
    for r in rows:
        where = t.ADMIN_EP_SUFFIX.format(season=r["season"], number=r["number"]) if r.get("season") else ""
        text = t.REPORT_ITEM.format(id=r["id"], code=r["code"], title=esc(r["title"]), where=where,
                                    reason=esc(r["reason"] or ""), user_id=r["user_id"])
        markup = back_panel_kb([btn(t.BTN_RESOLVED, Adm(a="rpx", id=r["id"])),
                                btn(t.BTN_OPEN_MOVIE, Op(id=r["movie_id"]))])
        await bot.send_message(callback.from_user.id, text, reply_markup=markup)
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "rpx"))
async def report_close(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    await misc.close_report(callback_data.id)
    await render(bot, callback.from_user.id, callback.message, t.REPORT_CLOSED.format(id=callback_data.id))
    await answer(callback)


# ---------- bloklash (admin) ----------

@router.callback_query(Adm.filter(F.a == "ban"), StateFilter("*"))
async def ban_menu(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not _admin_only(callback.from_user.id):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    await state.clear()
    await render(bot, callback.from_user.id, callback.message, t.BAN_MENU, back_panel_kb(
        [btn(t.BTN_BAN, Adm(a="bn", v="1")), btn(t.BTN_UNBAN, Adm(a="bn", v="0"))]
    ))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "bn"))
async def ban_ask(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if not _admin_only(callback.from_user.id):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    await state.set_state(BanForm.user_id)
    await state.update_data(ban=callback_data.v == "1")
    await render(bot, callback.from_user.id, callback.message, t.BAN_ASK_ID, cancel_kb())
    await answer(callback)


@router.message(BanForm.user_id, F.text)
async def ban_apply(message: Message, state: FSMContext) -> None:
    user_id = parse_int(message.text)
    if not user_id:
        await message.answer(t.BAD_NUMBER)
        return
    data = await state.get_data()
    ban = bool(data.get("ban"))
    if ban and users.role_of(user_id):
        await message.answer(t.BAN_STAFF)
        return
    await state.clear()
    await users.set_banned(user_id, ban)
    await message.answer((t.BAN_DONE if ban else t.UNBAN_DONE).format(user_id=user_id), reply_markup=back_panel_kb())


# ---------- rejalashtirilgan postlar (admin) ----------

@router.callback_query(Adm.filter(F.a == "sch"))
async def scheduled_list(callback: CallbackQuery, bot: Bot) -> None:
    if not _admin_only(callback.from_user.id):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    rows = await misc.pending_scheduled()
    lines = [t.SCHEDULED_TITLE] if rows else [t.SCHEDULED_EMPTY]
    buttons = []
    for r in rows:
        when = from_db(r["run_at"])
        lines.append(f"#{r['id']} · {fmt_local(when) if when else '?'} · {esc(r['title'])} [{r['code']}]")
        buttons.append([btn(t.BTN_CANCEL_POST.format(id=r["id"]), Adm(a="schx", id=r["id"]))])
    await render(bot, callback.from_user.id, callback.message, "\n".join(lines), back_panel_kb(*buttons))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "schx"))
async def scheduled_cancel(callback: CallbackQuery, callback_data: Adm, bot: Bot) -> None:
    if not _admin_only(callback.from_user.id):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    await misc.set_scheduled_status(callback_data.id, "cancelled")
    await answer(callback, t.CANCELLED)
    await scheduled_list(callback, bot)


# ---------- promo-kodlar (admin) ----------

@router.callback_query(Adm.filter(F.a == "pr"), StateFilter("*"))
async def promo_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not _admin_only(callback.from_user.id):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    await state.clear()
    rows = await payments.promos()
    lines = [t.PROMO_LIST_TITLE] if rows else [t.PROMO_LIST_EMPTY]
    buttons = []
    for p in rows:
        expires = from_db(p["expires_at"])
        status = "✅" if p["is_active"] else "⛔"
        lines.append(t.PROMO_LINE.format(status=status, code=esc(p["code"]), days=p["days"], used=p["used_count"],
                                         max=p["max_uses"], expires=fmt_date(expires) if expires else "∞"))
        buttons.append([btn(f"🗑 {p['code']}", Adm(a="prd", v=p["code"][:40]))])
    buttons.insert(0, [btn(t.BTN_PROMO_CREATE, Adm(a="prc"))])
    await render(bot, callback.from_user.id, callback.message, "\n".join(lines), back_panel_kb(*buttons))
    await answer(callback)


@router.callback_query(Adm.filter(F.a == "prd"))
async def promo_delete(callback: CallbackQuery, callback_data: Adm, state: FSMContext, bot: Bot) -> None:
    if not _admin_only(callback.from_user.id):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    await payments.delete_promo(callback_data.v)
    await answer(callback, t.DELETED)
    await promo_list(callback, state, bot)


@router.callback_query(Adm.filter(F.a == "prc"))
async def promo_create(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    if not _admin_only(callback.from_user.id):
        await answer(callback, t.NO_ACCESS, alert=True)
        return
    await state.set_state(PromoCreate.code)
    await render(bot, callback.from_user.id, callback.message, t.PROMO_ASK_CODE,
                 cancel_kb([btn(t.BTN_RANDOM_CODE, Adm(a="pra"))]))
    await answer(callback)


async def _promo_set_code(message_or_cb: Message | CallbackQuery, state: FSMContext, code: str, bot: Bot) -> None:
    chat_id = message_or_cb.from_user.id  # type: ignore[union-attr]
    if await payments.promo(code):
        await bot.send_message(chat_id, t.PROMO_EXISTS)
        return
    await state.update_data(code=code)
    await state.set_state(PromoCreate.days)
    await bot.send_message(chat_id, t.PROMO_ASK_DAYS.format(code=esc(code)), reply_markup=cancel_kb())


@router.callback_query(PromoCreate.code, Adm.filter(F.a == "pra"))
async def promo_random(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    alphabet = string.ascii_uppercase + string.digits
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    await answer(callback)
    await _promo_set_code(callback, state, code, bot)


@router.message(PromoCreate.code, F.text)
async def promo_code(message: Message, state: FSMContext, bot: Bot) -> None:
    code = message.text.strip().upper()
    if not code.replace("_", "").replace("-", "").isalnum() or len(code) > 32:
        await message.answer(t.PROMO_BAD_CODE)
        return
    await _promo_set_code(message, state, code, bot)


@router.message(PromoCreate.days, F.text)
async def promo_days(message: Message, state: FSMContext) -> None:
    days = parse_int(message.text)
    if not days or not 1 <= days <= 3650:
        await message.answer(t.BAD_NUMBER)
        return
    await state.update_data(days=days)
    await state.set_state(PromoCreate.uses)
    await message.answer(t.PROMO_ASK_USES, reply_markup=cancel_kb())


@router.message(PromoCreate.uses, F.text)
async def promo_uses(message: Message, state: FSMContext) -> None:
    uses = parse_int(message.text)
    if not uses or uses < 1:
        await message.answer(t.BAD_NUMBER)
        return
    await state.update_data(uses=uses)
    await state.set_state(PromoCreate.expires)
    await message.answer(t.PROMO_ASK_EXPIRES, reply_markup=cancel_kb([btn(t.BTN_NO_EXPIRY, Adm(a="prn"))]))


async def _promo_finish(bot: Bot, chat_id: int, state: FSMContext, expires_at: str | None) -> None:
    data = await state.get_data()
    await state.clear()
    ok = await payments.create_promo(data["code"], int(data["days"]), int(data["uses"]), expires_at, chat_id)
    text = t.PROMO_CREATED.format(code=esc(data["code"]), days=data["days"], uses=data["uses"]) if ok else t.PROMO_EXISTS
    await bot.send_message(chat_id, text, reply_markup=back_panel_kb([btn(t.BTN_BACK, Adm(a="pr"))]))


@router.callback_query(PromoCreate.expires, Adm.filter(F.a == "prn"))
async def promo_no_expiry(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await answer(callback)
    await _promo_finish(bot, callback.from_user.id, state, None)


@router.message(PromoCreate.expires, F.text)
async def promo_expires(message: Message, state: FSMContext, bot: Bot) -> None:
    when = parse_local(message.text.strip() + (" 23:59" if len(message.text.strip()) <= 10 else ""))
    if not when:
        await message.answer(t.BAD_DATE)
        return
    await _promo_finish(bot, message.chat.id, state, to_db(when))
