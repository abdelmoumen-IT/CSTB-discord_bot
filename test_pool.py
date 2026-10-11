import asyncio
from dotenv import load_dotenv
load_dotenv()

from database.connection import init_pool, get_pool, close_pool

async def main():
    await init_pool()
    async with get_pool().acquire() as conn:
        print(await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
    await close_pool()

asyncio.run(main())