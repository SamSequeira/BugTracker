import sys
import asyncio
sys.path.insert(0, "backend")

async def clean_test_data():
    from data.dbconnection.session import engine
    from sqlalchemy import text
    
    print("[Cleaning test data...]")
    print("Preserving: users table")
    print("Removing: old repositories, analysis_runs, candidate_issues")
    
    async with engine.begin() as conn:
        # Delete in order respecting foreign keys
        result = await conn.execute(text("DELETE FROM issue_recommendations"))
        print(f"  Deleted {result.rowcount} issue_recommendations")
        
        result = await conn.execute(text("DELETE FROM issue_similarities"))
        print(f"  Deleted {result.rowcount} issue_similarities")
        
        result = await conn.execute(text("DELETE FROM issue_statuses"))
        print(f"  Deleted {result.rowcount} issue_statuses")
        
        result = await conn.execute(text("DELETE FROM candidate_issues"))
        print(f"  Deleted {result.rowcount} candidate_issues")
        
        result = await conn.execute(text("DELETE FROM architecture_components"))
        print(f"  Deleted {result.rowcount} architecture_components")
        
        result = await conn.execute(text("DELETE FROM architecture_summaries"))
        print(f"  Deleted {result.rowcount} architecture_summaries")
        
        result = await conn.execute(text("DELETE FROM analysis_technologies"))
        print(f"  Deleted {result.rowcount} analysis_technologies")
        
        result = await conn.execute(text("DELETE FROM source_files"))
        print(f"  Deleted {result.rowcount} source_files")
        
        result = await conn.execute(text("DELETE FROM analysis_runs"))
        print(f"  Deleted {result.rowcount} analysis_runs")
        
        result = await conn.execute(text("DELETE FROM repositories"))
        print(f"  Deleted {result.rowcount} repositories")
    
    print("[Verifying cleanup...]")
    async with engine.connect() as conn:
        for table in ["repositories", "analysis_runs", "candidate_issues"]:
            result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            print(f"  {table}: {count} rows (should be 0)")

asyncio.run(clean_test_data())
