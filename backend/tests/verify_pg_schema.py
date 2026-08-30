import asyncio
import asyncpg


async def inspect_postgres_schema():
    conn = await asyncpg.connect("postgresql://postgres:postgres@127.0.0.1:5432/bugtracker")
    print("--- CANDIDATE_ISSUES COLUMNS ---")
    columns = await conn.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'candidate_issues'
        ORDER BY ordinal_position;
    """)
    for col in columns:
        print(f"  {col['column_name']:<25} {col['data_type']:<20} nullable={col['is_nullable']}")

    print("\n--- CANDIDATE_ISSUES CONSTRAINTS ---")
    constraints = await conn.fetch("""
        SELECT conname, pg_get_constraintdef(oid) as def
        FROM pg_constraint
        WHERE conrelid = 'candidate_issues'::regclass;
    """)
    for c in constraints:
        print(f"  {c['conname']:<40} {c['def']}")

    print("\n--- CANDIDATE_ISSUES INDEXES ---")
    indexes = await conn.fetch("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = 'candidate_issues';
    """)
    for idx in indexes:
        print(f"  {idx['indexname']:<40} {idx['indexdef']}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(inspect_postgres_schema())
