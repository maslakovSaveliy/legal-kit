import os

from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from handlers.catalog import ITEMS

router = Router()
PROVIDER_TOKEN = os.environ.get("YOOKASSA_PROVIDER_TOKEN", "")


@router.callback_query(F.data.startswith("buy:"))
async def buy(call: CallbackQuery) -> None:
    key = call.data.split(":", 1)[1]
    title, price = ITEMS[key]
    if key == "guide":
        # digital goods are paid in Telegram Stars
        await call.message.answer_invoice(
            title=title, description="Электронная книга", payload=f"order:{key}",
            currency="XTR", prices=[LabeledPrice(label=title, amount=price)],
        )
        return
    await call.message.answer_invoice(
        title=title, description="Доставка по России", payload=f"order:{key}",
        provider_token=PROVIDER_TOKEN, currency="RUB",
        prices=[LabeledPrice(label=title, amount=price * 100)],
        need_shipping_address=True,
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(message: Message) -> None:
    await message.answer("Оплата получена, заказ передан в доставку.")
