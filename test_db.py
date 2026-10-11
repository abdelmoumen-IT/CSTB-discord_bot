
import asyncio
from database.connection import create_db_pool


async def main():
    pool = await create_db_pool()

    try:
        result = await pool.fetchval("SELECT version()")
        print("Connected to PostgreSQL!")
        print(result)
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())