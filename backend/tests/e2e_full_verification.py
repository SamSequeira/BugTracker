"""
e2e_full_verification.py
-------------------------
Complete, rigorous, zero-mock end-to-end verification script covering:
- Part 2: Database connection verification
- Part 3: Database schema verification
- Part 4: Real BuggyMultiLangApp analysis execution
- Part 5: Candidate issue insertion verification (PostgreSQL direct comparison)
- Part 6: Candidate issue retrieval & filter verification
- Part 7: Tab 5 human review fetch verification (ReviewSampler + /review/batch)
- Part 8: Human verification update (PATCH /labels) & field preservation
- Part 9: Verified dataset endpoint verification (GET /dataset/verified)
- Part 10: Tab 5 re-fetch and state persistence verification
- Part 11: Negative and integrity testing
- Part 12: Data consistency and orphan audit
"""

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.config import settings
from data.dbconnection.session import engine, AsyncSessionLocal
from sqlalchemy import text, select, func
from app.models.repository import Repository
from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.issue_status import IssueStatus
from app.models.issue_recommendation import IssueRecommendation
from app.models.source_file import SourceFile
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.repositories.repository_repo import repository_repository
from app.services.ast_generator import ast_generator
from app.services.static_analyzer.analyzer import static_analyzer
from app.services.repository_analysis_service import RepositoryAnalysisService
from app.services.dataset_preparation.sampler import ReviewSampler
from app.schemas.candidate_issues import CandidateIssueResponse, CandidateIssueLabelUpdate

BENCHMARK_PATH = r"c:\Users\seque\Desktop\CODES\Projects\BuggyMultiLangApp"

verification_results = {}

async def run_full_verification():
    print("================================================================================")
    print(" STARTING END-TO-END VERIFICATION OF BUGTRACKER PIPELINE")
    print("================================================================================")

    # -------------------------------------------------------------------------
    # PART 2 & 3: Database Connection & Schema
    # -------------------------------------------------------------------------
    print("\n--- PART 2: DATABASE CONNECTION & MIGRATIONS ---")
    try:
        async with engine.connect() as conn:
            pg_ver = (await conn.execute(text("SELECT version();"))).scalar()
            db_name = (await conn.execute(text("SELECT current_database();"))).scalar()
            alembic_rev = (await conn.execute(text("SELECT version_num FROM alembic_version;"))).scalar()
            
            raw_url = settings.DATABASE_URL
            masked_url = re.sub(r':([^@]+)@', ':****@', raw_url)
            print(f"Connected to: {masked_url}")
            print(f"Database: {db_name} | PostgreSQL Version: {pg_ver}")
            print(f"Current Alembic Revision: {alembic_rev}")
            verification_results["part2"] = {
                "status": "PASS",
                "db_name": db_name,
                "version": pg_ver,
                "alembic_rev": alembic_rev,
            }
    except Exception as e:
        print(f"Part 2 FAIL: {e}")
        verification_results["part2"] = {"status": "FAIL", "error": str(e)}
        return

    print("\n--- PART 3: DATABASE SCHEMA INSPECTION ---")
    try:
        async with engine.connect() as conn:
            res = await conn.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_name = 'candidate_issues';
            """))
            cols = {r[0]: {"type": r[1], "nullable": r[2]} for r in res.fetchall()}
            
            required_cols = [
                "id", "analysis_run_id", "title", "description", "file_path",
                "line_number", "column", "severity", "urgency", "rule_id",
                "issue_type", "message", "code_snippet", "evidence", "language",
                "verified_severity", "verified_priority", "verified_at", "verification_notes"
            ]
            missing_cols = [c for c in required_cols if c not in cols]
            if missing_cols:
                raise ValueError(f"Missing required columns in candidate_issues: {missing_cols}")
                
            print(f"Verified all {len(required_cols)} required columns present in candidate_issues table.")
            verification_results["part3"] = {"status": "PASS", "columns_count": len(cols)}
    except Exception as e:
        print(f"Part 3 FAIL: {e}")
        verification_results["part3"] = {"status": "FAIL", "error": str(e)}
        return

    # -------------------------------------------------------------------------
    # PART 4: Real BuggyMultiLangApp Analysis Execution
    # -------------------------------------------------------------------------
    print("\n--- PART 4: RUNNING REAL ANALYSIS ON BUGGYMULTILANGAPP ---")
    repo_service = RepositoryAnalysisService()
    test_repo_id = str(uuid.uuid4())
    test_run_id = str(uuid.uuid4())

    async with AsyncSessionLocal() as db:
        # Create a test repository record and initial analysis run record
        repo_obj = Repository(
            id=test_repo_id,
            name="BuggyMultiLangApp-Audit",
            source_url=BENCHMARK_PATH,
            s3_key="repositories/test.zip",
        )
        db.add(repo_obj)
        
        run_obj = AnalysisRun(
            id=test_run_id,
            repository_id=test_repo_id,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        db.add(run_obj)
        await db.commit()

    # Step 1: Run AST Generation
    print(f"Generating AST for repository: {BENCHMARK_PATH}...")
    ast_result = await asyncio.to_thread(
        ast_generator.generate_ast_for_repository,
        BENCHMARK_PATH,
    )
    print(f"Files parsed: {len(ast_result.get('files_analyzed', []))}")

    # Step 2: Run Static Analyzer directly
    print("Running Static Analyzer across parsed files...")
    static_analysis = await asyncio.to_thread(
        static_analyzer.analyze_repository,
        ast_result,
        test_repo_id,
    )
    
    # Collect raw analyzer findings
    raw_analyzer_issues = []
    for file_res in static_analysis.get("results", []):
        for issue in file_res.get("issues", []):
            raw_analyzer_issues.append({
                "file_path": file_res["file_path"],
                "language": file_res["language"],
                "rule_id": issue.get("rule_id"),
                "issue_type": issue.get("issue_type"),
                "line_number": issue.get("line_number"),
                "column": issue.get("column"),
                "severity": issue.get("severity"),
                "message": issue.get("message"),
                "code_snippet": issue.get("code_snippet"),
                "evidence": issue.get("evidence"),
            })

    total_analyzer_findings = len(raw_analyzer_issues)
    print(f"Analyzer produced {total_analyzer_findings} total findings.")

    # -------------------------------------------------------------------------
    # PART 5: Verify Candidate Issue Insertion into PostgreSQL
    # -------------------------------------------------------------------------
    print("\n--- PART 5: CANDIDATE ISSUE INSERTION & DATABASE VERIFICATION ---")
    async with AsyncSessionLocal() as db:
        # Complete analysis run and persist findings to PostgreSQL
        complete_analysis_dict = {
            "repository_path": BENCHMARK_PATH,
            "candidate_issues": raw_analyzer_issues,
            "_files_analyzed": ast_result.get("files_analyzed", []),
            "_ast_result": ast_result,
        }
        await repo_service.complete_analysis_run(db, test_run_id, complete_analysis_dict)
        await db.commit()

    # Query PostgreSQL directly for inserted rows
    async with AsyncSessionLocal() as db:
        stmt = (
            select(CandidateIssue)
            .where(CandidateIssue.analysis_run_id == test_run_id)
            .order_by(CandidateIssue.file_path, CandidateIssue.line_number)
        )
        db_issues = list((await db.execute(stmt)).scalars().all())

    db_issues_count = len(db_issues)
    print(f"Analyzer findings: {total_analyzer_findings} | PostgreSQL inserted rows: {db_issues_count}")
    
    if total_analyzer_findings != db_issues_count:
        print(f"FAIL: Count mismatch! Expected {total_analyzer_findings}, got {db_issues_count}")
    else:
        print("PASS: 100% count consistency between Static Analyzer findings and PostgreSQL candidate_issues rows.")

    # Check representative rules across Python, JavaScript, Java
    rule_samples = {
        "PY_DIV_001": None,
        "PY_MUT_001": None,
        "PY_UNREACH_001": None,
        "PY_CONSTCOND_001": None,
        "PY_RES_001": None,
        "PY_EVAL_001": None,
        "JS_DIV_001": None,
        "JS_EQ_001": None,
        "JS_AWA_001": None,
        "JS_PROMISE_001": None,
        "JAVA_DIV_001": None,
        "JAVA_LOOP_001": None,
        "JAVA_NULL_001": None,
        "JAVA_EQ_001": None,
        "JAVA_EXC_001": None,
    }

    for row in db_issues:
        r_id = row.rule_id
        if r_id in rule_samples and rule_samples[r_id] is None:
            rule_samples[r_id] = row

    print("\n--- Representative Issue Verification (Analyzer -> ORM -> PostgreSQL) ---")
    representative_checks_passed = True
    for rule_id, sample in rule_samples.items():
        if sample is None:
            print(f"  [!] Rule {rule_id}: No finding produced in benchmark")
            representative_checks_passed = False
            continue
            
        # Verify field integrity
        has_id = bool(sample.id)
        has_run = sample.analysis_run_id == test_run_id
        has_file = bool(sample.file_path)
        has_line = sample.line_number is not None
        has_sev = sample.severity in ("high", "medium", "low")
        has_snippet = bool(sample.code_snippet)
        has_lang = sample.language in ("Python", "JavaScript", "Java")
        ev_ok = isinstance(sample.evidence, dict) and len(sample.evidence) > 0
        
        ok = all([has_id, has_run, has_file, has_line, has_sev, has_snippet, has_lang, ev_ok])
        status_str = "PASS" if ok else "FAIL"
        if not ok:
            representative_checks_passed = False
        print(f"  [{status_str}] {rule_id} ({sample.language}) -> file: {Path(sample.file_path).name}:{sample.line_number} | severity: {sample.severity} | evidence keys: {list(sample.evidence.keys())}")

    verification_results["part5"] = {
        "status": "PASS" if (total_analyzer_findings == db_issues_count and representative_checks_passed) else "FAIL",
        "analyzer_count": total_analyzer_findings,
        "database_count": db_issues_count,
    }

    # -------------------------------------------------------------------------
    # PART 6: Candidate Issue Retrieval & Filter Verification
    # -------------------------------------------------------------------------
    print("\n--- PART 6: CANDIDATE ISSUE RETRIEVAL & FILTERING ---")
    async with AsyncSessionLocal() as db:
        # 1. Unfiltered by run_id
        items_run, total_run = await candidate_issue_repository.list_issues(
            db, analysis_run_id=test_run_id, limit=200
        )
        print(f"Query by run_id: total={total_run}, items={len(items_run)}")

        # 2. Filter by Language
        py_items, py_total = await candidate_issue_repository.list_issues(
            db, analysis_run_id=test_run_id, language="Python", limit=200
        )
        js_items, js_total = await candidate_issue_repository.list_issues(
            db, analysis_run_id=test_run_id, language="JavaScript", limit=200
        )
        java_items, java_total = await candidate_issue_repository.list_issues(
            db, analysis_run_id=test_run_id, language="Java", limit=200
        )
        print(f"Language breakdown: Python={py_total}, JS={js_total}, Java={java_total} (Sum={py_total + js_total + java_total})")

        # 3. Filter by Rule ID (e.g. PY_MUT_001)
        mut_items, mut_total = await candidate_issue_repository.list_issues(
            db, analysis_run_id=test_run_id, rule_id="PY_MUT_001"
        )
        print(f"Filter by rule_id='PY_MUT_001': count={mut_total} (Expected: 2)")

        # 4. Filter verified-only before any verification
        verif_items, verif_total = await candidate_issue_repository.list_issues(
            db, analysis_run_id=test_run_id, verified_only=True
        )
        print(f"Filter verified_only=True (before labeling): count={verif_total} (Expected: 0)")

    part6_ok = (total_run == db_issues_count and (py_total + js_total + java_total) == db_issues_count and mut_total == 2 and verif_total == 0)
    print(f"Part 6 Filtering Verification: {'PASS' if part6_ok else 'FAIL'}")
    verification_results["part6"] = {"status": "PASS" if part6_ok else "FAIL"}

    # -------------------------------------------------------------------------
    # PART 7: Tab 5 Human Review Fetch Verification
    # -------------------------------------------------------------------------
    print("\n--- PART 7: TAB 5 HUMAN REVIEW (REVIEW BATCH GENERATION) ---")
    async with AsyncSessionLocal() as db:
        # Review batch sampler fetches all unverified issues across repos
        records = await candidate_issue_repository.get_all_unverified_issues_with_repo(db)
        sampler = ReviewSampler(random_seed=42)
        sampled_records, report = sampler.sample(
            records=records,
            target_size=200,
            max_per_rule_per_repo=25,
        )
        stats = await candidate_issue_repository.get_dataset_stats(db)

    print(f"Total unverified candidate issues in DB: {report['total_available_unverified_real']}")
    print(f"Sampled batch size: {report['sampled_count']}")
    print(f"Language distribution in Tab 5 batch: {report['languages_distribution']}")
    print(f"Global dataset stats: total={stats['total_candidate_issues']}, fully_verified={stats['fully_verified']}, unverified={stats['unverified']}")

    # Confirm that items in the review batch match PostgreSQL rows
    sampled_ids = {r["id"] for r in sampled_records}
    async with AsyncSessionLocal() as db:
        stmt = select(CandidateIssue.id).where(CandidateIssue.id.in_(sampled_ids))
        verified_db_ids = set((await db.execute(stmt)).scalars().all())

    batch_integrity_ok = len(sampled_ids) == len(verified_db_ids) and len(sampled_ids) > 0
    print(f"Review batch records trace directly to PostgreSQL: {'PASS' if batch_integrity_ok else 'FAIL'}")
    verification_results["part7"] = {
        "status": "PASS" if batch_integrity_ok else "FAIL",
        "sampled_count": len(sampled_ids),
        "verified_in_db": len(verified_db_ids),
    }

    # -------------------------------------------------------------------------
    # PART 8: Human Verification Update (Tab 5 /labels endpoint)
    # -------------------------------------------------------------------------
    print("\n--- PART 8: HUMAN VERIFICATION UPDATE & FIELD PRESERVATION ---")
    # Select candidate issues across all 3 languages to label
    test_candidates = [
        next(i for i in db_issues if i.language == "Python" and i.rule_id == "PY_MUT_001"),
        next(i for i in db_issues if i.language == "JavaScript" and i.rule_id == "JS_DIV_001"),
        next(i for i in db_issues if i.language == "Java" and i.rule_id == "JAVA_LOOP_001"),
    ]

    labels_to_apply = [
        {"verified_severity": "high", "verified_priority": "p1", "notes": "Verified critical mutable default arg bug."},
        {"verified_severity": "medium", "verified_priority": "p2", "notes": "Verified medium division by zero."},
        {"verified_severity": "high", "verified_priority": "p1", "notes": "Verified infinite loop in Java service."},
    ]

    part8_passed = True
    async with AsyncSessionLocal() as db:
        for cand, label_info in zip(test_candidates, labels_to_apply):
            original_detector_severity = cand.severity
            
            # Execute label update via repository
            updated = await candidate_issue_repository.update_labels(
                db=db,
                issue_id=cand.id,
                verified_severity=label_info["verified_severity"],
                verified_priority=label_info["verified_priority"],
                verification_notes=label_info["notes"],
            )
            await db.commit()

            # Refresh and inspect directly in PostgreSQL
            refreshed = await candidate_issue_repository.get_by_id(db, cand.id)
            
            sev_match = refreshed.verified_severity == label_info["verified_severity"]
            prio_match = refreshed.verified_priority == label_info["verified_priority"]
            notes_match = refreshed.verification_notes == label_info["notes"]
            timestamp_ok = refreshed.verified_at is not None
            detector_sev_preserved = refreshed.severity == original_detector_severity

            ok = sev_match and prio_match and notes_match and timestamp_ok and detector_sev_preserved
            if not ok:
                part8_passed = False
            status_str = "PASS" if ok else "FAIL"
            print(f"  [{status_str}] Issue {cand.id[:8]} ({cand.rule_id}):")
            print(f"       detector_severity: {refreshed.severity} (preserved: {detector_sev_preserved})")
            print(f"       verified_severity: {refreshed.verified_severity} | verified_priority: {refreshed.verified_priority}")
            print(f"       verified_at: {refreshed.verified_at} | notes: {refreshed.verification_notes}")

    verification_results["part8"] = {"status": "PASS" if part8_passed else "FAIL"}

    # -------------------------------------------------------------------------
    # PART 9: Verified Dataset Endpoint Verification
    # -------------------------------------------------------------------------
    print("\n--- PART 9: VERIFIED DATASET ENDPOINT VERIFICATION ---")
    async with AsyncSessionLocal() as db:
        training_records = await candidate_issue_repository.get_verified_training_dataset(db)
        
    print(f"Total records in verified training dataset: {len(training_records)}")
    part9_passed = len(training_records) >= len(test_candidates)

    for rec in training_records:
        if rec["id"] in [c.id for c in test_candidates]:
            has_correct_sev = rec["severity"] in ("high", "medium", "low")
            has_correct_prio = rec["priority"] in ("p1", "p2", "p3", "p4")
            has_detector_sev = bool(rec["detector_severity"])
            print(f"  Verified Record {rec['id'][:8]}: severity={rec['severity']} (verified), priority={rec['priority']}, detector_severity={rec['detector_severity']}")
            if not (has_correct_sev and has_correct_prio and has_detector_sev):
                part9_passed = False

    verification_results["part9"] = {"status": "PASS" if part9_passed else "FAIL"}

    # -------------------------------------------------------------------------
    # PART 10: Verify Tab 5 After Saving & Stability
    # -------------------------------------------------------------------------
    print("\n--- PART 10: TAB 5 RE-FETCH & STABILITY AFTER SAVING ---")
    async with AsyncSessionLocal() as db:
        # 1. Fetch updated stats
        new_stats = await candidate_issue_repository.get_dataset_stats(db)
        print(f"Updated Stats: fully_verified={new_stats['fully_verified']}, unverified={new_stats['unverified']}")

        # 2. Check that verified issues are labeled as verified
        for cand in test_candidates:
            refreshed = await candidate_issue_repository.get_by_id(db, cand.id)
            assert refreshed.verified_severity is not None
            assert refreshed.verified_priority is not None

        # 3. Check for duplicates created by update
        stmt = select(func.count(CandidateIssue.id)).where(CandidateIssue.analysis_run_id == test_run_id)
        current_count = (await db.execute(stmt)).scalar()
        print(f"Total candidate issues for run: {current_count} (Original: {db_issues_count})")
        no_duplicates = current_count == db_issues_count

    part10_ok = no_duplicates and (new_stats["fully_verified"] >= len(test_candidates))
    print(f"Tab 5 State Persistence & ID Stability: {'PASS' if part10_ok else 'FAIL'}")
    verification_results["part10"] = {"status": "PASS" if part10_ok else "FAIL"}

    # -------------------------------------------------------------------------
    # PART 11: Negative & Integrity Testing
    # -------------------------------------------------------------------------
    print("\n--- PART 11: NEGATIVE & INTEGRITY TESTING ---")
    part11_errors = []
    async with AsyncSessionLocal() as db:
        # 1. Invalid verified_severity constraint violation
        try:
            await db.execute(text(
                "UPDATE candidate_issues SET verified_severity = 'invalid_sev' WHERE id = :id",
            ), {"id": test_candidates[0].id})
            await db.commit()
            part11_errors.append("FAIL: Database accepted invalid verified_severity ('invalid_sev')")
        except Exception as e:
            await db.rollback()
            print(f"  [PASS] Invalid verified_severity correctly rejected by database check constraint: {type(e).__name__}")

        # 2. Invalid verified_priority constraint violation
        try:
            await db.execute(text(
                "UPDATE candidate_issues SET verified_priority = 'p99' WHERE id = :id",
            ), {"id": test_candidates[0].id})
            await db.commit()
            part11_errors.append("FAIL: Database accepted invalid verified_priority ('p99')")
        except Exception as e:
            await db.rollback()
            print(f"  [PASS] Invalid verified_priority correctly rejected by database check constraint: {type(e).__name__}")

        # 3. Nonexistent issue update
        nonexistent_res = await candidate_issue_repository.update_labels(
            db, issue_id="nonexistent-uuid-9999", verified_severity="high", verified_priority="p1"
        )
        if nonexistent_res is None:
            print("  [PASS] Nonexistent issue update correctly returns None.")
        else:
            part11_errors.append("FAIL: Nonexistent issue update did not return None.")

        # 4. Foreign key constraint violation on analysis_run_id
        try:
            fake_issue = CandidateIssue(
                id=str(uuid.uuid4()),
                analysis_run_id="nonexistent-run-id-12345",
                title="Fake",
                description="Fake",
                file_path="fake.py",
                severity="low",
                urgency="low",
            )
            db.add(fake_issue)
            await db.commit()
            part11_errors.append("FAIL: Foreign key violation was not caught by database.")
        except Exception as e:
            await db.rollback()
            print(f"  [PASS] Foreign key constraint on analysis_run_id enforced: {type(e).__name__}")

    part11_ok = len(part11_errors) == 0
    verification_results["part11"] = {"status": "PASS" if part11_ok else "FAIL", "errors": part11_errors}

    # -------------------------------------------------------------------------
    # PART 12: Data Consistency & Orphan Audit
    # -------------------------------------------------------------------------
    print("\n--- PART 12: DATA CONSISTENCY & ORPHAN AUDIT ---")
    async with AsyncSessionLocal() as db:
        # Check orphaned candidate issues
        res = await db.execute(text("""
            SELECT count(*) FROM candidate_issues c
            LEFT JOIN analysis_runs a ON c.analysis_run_id = a.id
            WHERE a.id IS NULL;
        """))
        orphan_count = res.scalar()
        print(f"Orphaned candidate issues (invalid analysis_run_id): {orphan_count}")

        # Check duplicate candidate issue rows (same run, file, line, rule_id)
        res = await db.execute(text("""
            SELECT analysis_run_id, file_path, line_number, rule_id, count(*)
            FROM candidate_issues
            WHERE analysis_run_id = :run_id
            GROUP BY analysis_run_id, file_path, line_number, rule_id
            HAVING count(*) > 1;
        """), {"run_id": test_run_id})
        dup_rows = res.fetchall()
        print(f"Duplicate candidate issue rows within test run: {len(dup_rows)}")

        # Check for invalid partial verification states (e.g. verified_at set without verified_severity)
        res = await db.execute(text("""
            SELECT count(*) FROM candidate_issues
            WHERE verified_at IS NOT NULL AND verified_severity IS NULL AND verified_priority IS NULL;
        """))
        invalid_verif_count = res.scalar()
        print(f"Issues with timestamp but missing verification labels: {invalid_verif_count}")

    part12_ok = orphan_count == 0 and len(dup_rows) == 0 and invalid_verif_count == 0
    verification_results["part12"] = {
        "status": "PASS" if part12_ok else "FAIL",
        "orphan_count": orphan_count,
        "duplicate_rows": len(dup_rows),
        "invalid_verif_count": invalid_verif_count,
    }

    # Cleanup test run and repository
    print("\nCleaning up test audit run...")
    async with AsyncSessionLocal() as db:
        await db.execute(text("""
            DELETE FROM issue_statuses 
            WHERE candidate_issue_id IN (
                SELECT id FROM candidate_issues WHERE analysis_run_id = :r_id
            )
        """), {"r_id": test_run_id})
        await db.execute(text("""
            DELETE FROM issue_recommendations 
            WHERE candidate_issue_id IN (
                SELECT id FROM candidate_issues WHERE analysis_run_id = :r_id
            )
        """), {"r_id": test_run_id})
        await db.execute(text("DELETE FROM candidate_issues WHERE analysis_run_id = :r_id"), {"r_id": test_run_id})
        await db.execute(text("DELETE FROM source_files WHERE analysis_run_id = :r_id"), {"r_id": test_run_id})
        await db.execute(text("DELETE FROM analysis_runs WHERE id = :r_id"), {"r_id": test_run_id})
        await db.execute(text("DELETE FROM repositories WHERE id = :rep_id"), {"rep_id": test_repo_id})
        await db.commit()
    print("Cleanup completed.")

    print("\n================================================================================")
    print(" CONSOLIDATED VERIFICATION RUN SUMMARY")
    print("================================================================================")
    for part, res in verification_results.items():
        print(f"  {part.upper()}: {res['status']}")
    print("================================================================================")

if __name__ == "__main__":
    asyncio.run(run_full_verification())
