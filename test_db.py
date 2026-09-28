import sys
import asyncio
sys.path.insert(0, "backend")

async def test_db():
    from data.dbconnection.session import engine
    from sqlalchemy import text
    
    print("[Testing PostgreSQL connection...]")
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        print("✓ PostgreSQL connection successful")
    
    print("[Checking tables...]")
    async with engine.connect() as conn:
        result = await conn.execute(text("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name
        """))
        tables = [row[0] for row in result]
        print(f"Tables found: {len(tables)}")
        for table in tables:
            print(f"  - {table}")
    
    print("[Checking key models...]")
    for table in ["users", "repositories", "analysis_runs", "candidate_issues"]:
        if table in tables:
            async with engine.connect() as conn:
                result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  {table}: {count} rows")

asyncio.run(test_db())
