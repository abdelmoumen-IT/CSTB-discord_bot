import asyncio
from dotenv import load_dotenv
load_dotenv()

from database.connection import init_pool, close_pool
from database.repositories import get_modules, get_categories, get_resources

async def main():
    await init_pool()
    modules = await get_modules()
    print(modules)
    print(await get_categories(modules[0]["id"]))
    cats = await get_categories(modules[0]["id"])
    print(await get_resources(cats[0]["id"])) 
    await close_pool()

asyncio.run(main())