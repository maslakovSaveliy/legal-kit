import aiosqlite

DB_PATH = "shop.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS customers (tg_id INTEGER PRIMARY KEY, name TEXT, phone TEXT)"
        )
        await db.execute(
            "CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, tg_id INTEGER, item TEXT, amount INTEGER, status TEXT)"
        )
        await db.commit()


async def save_customer(tg_id: int, name: str, phone: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO customers VALUES (?, ?, ?)", (tg_id, name, phone))
        await db.commit()
