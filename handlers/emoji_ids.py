"""/emojiid: yuborilgan premium emoji'larning ID sini qaytaradi (faqat admin)."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database import users

router = Router()


@router.message(Command("emojiid"))
async def emoji_ids(message: Message) -> None:
    if not users.has_role(message.from_user.id, "admin"):  # type: ignore[union-attr]
        return
    ids = [e.custom_emoji_id for e in (message.entities or []) if e.type == "custom_emoji"]
    if not ids:
        await message.answer("Buyruq yoniga premium emoji yozing, masalan: /emojiid (emoji)")
        return
    await message.answer("\n".join(f"<code>{i}</code>" for i in ids))


@router.message(Command("rmkb"))
async def remove_reply_keyboard(message: Message) -> None:
    """Eski versiyadan qolgan pastki (reply) klaviaturani chatdan olib tashlaydi."""
    if not users.has_role(message.from_user.id, "admin"):  # type: ignore[union-attr]
        return
    from aiogram.types import ReplyKeyboardRemove

    sent = await message.answer("✅ Pastki tugmalar olib tashlandi.", reply_markup=ReplyKeyboardRemove())
    try:
        await sent.delete()
    except Exception:  # noqa: BLE001
        pass


# ---------- treyler yuklash va kartochkani ko'rish (admin) ----------
from aiogram import Bot, F  # noqa: E402
from aiogram.filters import CommandObject  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.state import State, StatesGroup  # noqa: E402

import texts as t  # noqa: E402
from database import movies, users  # noqa: E402
from utils.text import esc  # noqa: E402


class TrailerForm(StatesGroup):
    video = State()


@router.message(Command("treyler"))
async def trailer_cmd(message: Message, command: CommandObject, state: FSMContext) -> None:
    if not users.has_role(message.from_user.id, "moderator"):  # type: ignore[union-attr]
        return
    args = (command.args or "").split()
    if not args or not args[0].isdigit():
        await message.answer(t.BM_TRAILER_USAGE)
        return
    movie = await movies.by_code(int(args[0]))
    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi.")
        return
    if len(args) > 1:
        await movies.update(movie["id"], trailer_file_id=None)
        await message.answer(t.BM_TRAILER_DELETED)
        return
    await state.set_state(TrailerForm.video)
    await state.update_data(trailer_movie_id=movie["id"])
    await message.answer(t.BM_TRAILER_ASK.format(title=esc(movie["title"])))


@router.message(TrailerForm.video, F.video)
async def trailer_got_video(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    movie_id = int(data.get("trailer_movie_id") or 0)
    await state.clear()
    if not movie_id:
        return
    await movies.update(movie_id, trailer_file_id=message.video.file_id)  # type: ignore[union-attr]
    await message.answer(t.BM_TRAILER_SAVED)


@router.message(TrailerForm.video, Command("cancel"))
async def trailer_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Bekor qilindi.")


@router.message(TrailerForm.video)
async def trailer_bad(message: Message) -> None:
    await message.answer(t.BM_TRAILER_BAD)


@router.message(Command("korish"))
async def preview_buy_card(message: Message, command: CommandObject, bot: Bot) -> None:
    if not users.has_role(message.from_user.id, "moderator"):  # type: ignore[union-attr]
        return
    arg = (command.args or "").strip()
    if not arg.isdigit():
        await message.answer(t.BM_TRAILER_USAGE)
        return
    movie = await movies.by_code(int(arg))
    if not movie:
        await message.answer("❌ Bunday kodli kino topilmadi.")
        return
    if not int(movie.get("price") or 0):
        await message.answer("Bu kino bepul, sotib olish kartochkasi yo'q.")
        return
    from services import delivery
    await delivery.send_buy_card(bot, message.chat.id, movie)
