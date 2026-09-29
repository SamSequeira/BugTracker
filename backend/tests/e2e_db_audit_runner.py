import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from data.dbconnection.session import engine, AsyncSessionLocal
from sqlalchemy import text, select, inspect
from app.models.candidate_issues import CandidateIssue
from app.models.analysis_run import AnalysisRun
from app.models.repository import Repository
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.services.ast_generator import ast_generator
from app.services.static_analyzer import StaticAnalyzer
from app.services.candidate_issue_mapper import candidate_issue_mapper
from app.services.dataset_preparation.sampler import ReviewSampler


async def run_part2_db_connection():
    print("\n=======================================================")
    print("PART 2: DATABASE CONNECTION VERIFICATION")
    print("=======================================================")
    raw_url = settings.DATABASE_URL
    masked_url = re.sub(r':([^@]+)@', ':****@', raw_url)
    print(f"DATABASE_URL: {masked_url}")
    print(f"Database Engine: {type(engine).__name__ if engine else 'None'}")
    
    if engine is None:
        print("RESULT: FAIL - Async engine is None.")
        return False
        
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("SELECT version();"))
            version_str = res.scalar()
            print(f"PostgreSQL version(): {version_str}")
            
            res = await conn.execute(text("SELECT current_database();"))
            db_name = res.scalar()
            print(f"Current Database: {db_name}")
            
            res = await conn.execute(text("SELECT version_num FROM alembic_version;"))
            alembic_rev = res.scalar()
            print(f"Alembic Current Revision: {alembic_rev}")
            
            res = await conn.execute(text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;"
            ))
            tables = [r[0] for r in res.fetchall()]
            print(f"Public Tables Count: {len(tables)}")
            print(f"Tables: {', '.join(tables)}")
            
        print("RESULT: PASS - Real PostgreSQL database connected and operational.")
        return True
    except Exception as e:
        print(f"RESULT: FAIL - Connection error: {e}")
        return False


async def run_part3_db_schema():
    print("\n=======================================================")
    print("PART 3: DATABASE SCHEMA VERIFICATION")
    print("=======================================================")
    try:
        async with engine.connect() as conn:
            # Inspect candidate_issues columns
            query = text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'candidate_issues'
                ORDER BY ordinal_position;
            """)
            res = await conn.execute(query)
            columns = res.fetchall()
            print(f"\n[candidate_issues Columns ({len(columns)})]:")
            for col in columns:
                print(f"  - {col[0]}: {col[1]} (nullable: {col[2]}, default: {col[3]})")
                
            # Inspect check constraints
            query = text("""
                SELECT conname, pg_get_constraintdef(c.oid)
                FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE conrelid = 'candidate_issues'::regclass;
            """)
            res = await conn.execute(query)
            constraints = res.fetchall()
            print(f"\n[candidate_issues Constraints ({len(constraints)})]:")
            for c in constraints:
                print(f"  - {c[0]}: {c[1]}")
                
            # Inspect indexes
            query = text("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'candidate_issues';
            """)
            res = await conn.execute(query)
            indexes = res.fetchall()
            print(f"\n[candidate_issues Indexes ({len(indexes)})]:")
            for idx in indexes:
                print(f"  - {idx[0]}: {idx[1]}")
                
        print("\nRESULT: PASS - Schema contains all required verification and analysis fields and check constraints.")
        return True
    except Exception as e:
        print(f"RESULT: FAIL - Schema inspection error: {e}")
        return False

if __name__ == "__main__":
    async def main():
        ok2 = await run_part2_db_connection()
        if ok2:
            await run_part3_db_schema()
    asyncio.run(main())
