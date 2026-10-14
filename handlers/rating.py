"""Baholash, izoh qoldirish va izohlarni ko'rish."""
from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import texts as t
from database import movies, users
from handlers.delivery import restore_kb
from keyboards.callbacks import Card
from keyboards.user import comment_prompt_kb, comments_kb, rating_kb
from services import delivery
from services.cards import card_caption
from utils.text import esc, truncate
from utils.time import fmt_date, from_db
from utils.ui import answer, edit_caption, edit_kb

router = Router()

Row = dict[str, Any]

COMMENT_MAX = 300
COMMENTS_PER_PAGE = 3


class CommentForm(StatesGroup):
    text = State()


@router.callback_query(Card.filter(F.a == "rate"))
async def rate_menu(callback: CallbackQuery, callback_data: Card) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    await edit_kb(callback.message, rating_kb(callback_data.m, callback_data.k))


@router.callback_query(Card.filter(F.a == "rs"))
async def rate_set(callback: CallbackQuery, callback_data: Card, state: FSMContext, bot: Bot) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback, t.RATED.format(score=callback_data.v))
    
    score = callback_data.v
    movie = await movies.get(callback_data.m)
    if not movie or not 1 <= score <= 5:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    uid = callback.from_user.id
    await movies.set_rating(uid, movie["id"], score)
    movie = await movies.get(movie["id"]) or movie
    caption = await delivery.serial_caption(movie) if callback_data.k == "s" else card_caption(movie)
    kb = await restore_kb(bot, uid, movie, callback_data.k)
    if not await edit_caption(callback.message, caption, kb):
        await edit_kb(callback.message, kb)
    await state.set_state(CommentForm.text)
    await state.update_data(movie_id=movie["id"])
    await bot.send_message(uid, t.COMMENT_PROMPT.format(max=COMMENT_MAX), reply_markup=comment_prompt_kb(movie["id"]))


@router.callback_query(Card.filter(F.a == "cskip"))
async def comment_skip(callback: CallbackQuery, state: FSMContext) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    await state.clear()
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(t.COMMENT_SKIPPED)
        except TelegramAPIError:
            pass


@router.message(CommentForm.text, F.text)
async def comment_text(message: Message, state: FSMContext) -> None:
    text = message.text.strip()
    if len(text) > COMMENT_MAX:
        await message.answer(t.COMMENT_TOO_LONG.format(max=COMMENT_MAX))
        return
    data = await state.get_data()
    await state.clear()
    movie_id = data.get("movie_id")
    if movie_id and await movies.user_rating(message.from_user.id, movie_id):  # type: ignore[union-attr]
        await movies.set_comment(message.from_user.id, movie_id, text)  # type: ignore[union-attr]
        await message.answer(t.COMMENT_SAVED)


@router.message(CommentForm.text)
async def comment_not_text(message: Message) -> None:
    await message.answer(t.COMMENT_TEXT_ONLY)


async def _comments_page(callback: CallbackQuery, movie: Row, page: int) -> None:
    total = await movies.comment_count(movie["id"])
    if not total:
        await answer(callback, t.NO_COMMENTS, alert=True)
        return
    pages = max(1, (total + COMMENTS_PER_PAGE - 1) // COMMENTS_PER_PAGE)
    page = min(max(page, 0), pages - 1)
    rows = await movies.comments(movie["id"], page * COMMENTS_PER_PAGE, COMMENTS_PER_PAGE)
    lines = [t.COMMENTS_TITLE.format(title=esc(movie["title"]), total=total)]
    for i, r in enumerate(rows, 1):
        when = from_db(r["created_at"])
        lines.append(t.COMMENT_LINE.format(
            n=i, name=esc(r["first_name"] or t.ANONYMOUS), score=r["score"],
            date=fmt_date(when) if when else "", text=esc(truncate(r["comment"], 250)),
        ))
    staff = users.has_role(callback.from_user.id, "moderator")
    deletable = [r["user_id"] for r in rows] if staff else []
    await edit_caption(callback.message, "\n\n".join(lines), comments_kb(movie["id"], page, pages, deletable))


@router.callback_query(Card.filter(F.a.in_({"cm", "cmd", "cb"})))
async def comments(callback: CallbackQuery, callback_data: Card, bot: Bot) -> None:
    # ⚡ DARHOL JAVOB BERISH
    await answer(callback)
    
    movie = await movies.get(callback_data.m)
    if not movie:
        await answer(callback, t.MOVIE_GONE, alert=True)
        return
    if callback_data.a == "cb":
        kb = await delivery.film_kb(bot, callback.from_user.id, movie)
        await edit_caption(callback.message, card_caption(movie), kb)
        return
    if callback_data.a == "cmd":
        if not users.has_role(callback.from_user.id, "moderator"):
            await answer(callback, t.NO_ACCESS, alert=True)
            return
        await movies.set_comment(callback_data.v, movie["id"], None)
        if not await movies.comment_count(movie["id"]):
            kb = await delivery.film_kb(bot, callback.from_user.id, movie)
            await edit_caption(callback.message, card_caption(movie), kb)
            return
    await _comments_page(callback, movie, callback_data.p)
