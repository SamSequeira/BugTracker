import sys
import asyncio
sys.path.insert(0, "backend")

async def check_schema():
    from data.dbconnection.session import engine
    from sqlalchemy import text
    
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'repositories'
            ORDER BY ordinal_position
        """))
        columns = result.fetchall()
        print("Repositories table schema:")
        for col in columns:
            print(f"  {col[0]}: {col[1]}")

asyncio.run(check_schema())
