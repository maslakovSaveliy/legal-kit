from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

router = Router()

ITEMS = {
    "plaid": ("Плед шерстяной", 4900),
    "pillow": ("Подушка льняная", 1900),
    "guide": ("Электронная книга «Уютный дом» (PDF)", 50),
}


@router.message(Command("catalog"))
async def catalog(message: Message) -> None:
    rows = [
        [InlineKeyboardButton(text=f"{title} — {price}", callback_data=f"buy:{key}")]
        for key, (title, price) in ITEMS.items()
    ]
    await message.answer("Каталог:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
