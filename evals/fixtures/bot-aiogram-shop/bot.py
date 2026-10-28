import asyncio
import os

from aiogram import Bot, Dispatcher

from handlers import catalog, checkout, start
from storage import init_db


async def main() -> None:
    await init_db()
    bot = Bot(token=os.environ["BOT_TOKEN"])
    dp = Dispatcher()
    dp.include_routers(start.router, catalog.router, checkout.router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
