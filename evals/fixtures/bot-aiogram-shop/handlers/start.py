from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from storage import save_customer

router = Router()


@router.message(CommandStart())
async def start(message: Message) -> None:
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Поделиться номером", request_contact=True)],
        ],
        resize_keyboard=True,
    )
    await message.answer("Добро пожаловать в «Тёплый дом»! Отправьте номер телефона, чтобы начать.", reply_markup=keyboard)


@router.message(F.contact)
async def got_contact(message: Message) -> None:
    await save_customer(message.from_user.id, message.from_user.full_name, message.contact.phone_number)
    await message.answer("Спасибо! Каталог: /catalog")
