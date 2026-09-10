import asyncio
import asyncpg


async def ensure_bugtracker_db():
    conn = await asyncpg.connect("postgresql://postgres:postgres@127.0.0.1:5432/postgres")
    exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = 'bugtracker'")
    if not exists:
        await conn.execute("CREATE DATABASE bugtracker")
        print("Database 'bugtracker' created.")
    else:
        print("Database 'bugtracker' already exists.")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(ensure_bugtracker_db())
