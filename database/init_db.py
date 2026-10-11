import os, asyncio, asyncpg
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

async def main():
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    await conn.execute(sql)
    tables = await conn.fetch(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY 1;"
    )
    print([t["table_name"] for t in tables])
    await conn.close()

asyncio.run(main())