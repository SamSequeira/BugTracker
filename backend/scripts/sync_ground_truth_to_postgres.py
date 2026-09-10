"""
sync_ground_truth_to_postgres.py — Sync bootstrap ground-truth dataset into PostgreSQL.
=====================================================================================
Seeds canonical ground-truth candidate issues into PostgreSQL database to establish
the baseline for the continuous learning and human review loop.
"""
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(backend_dir / ".env")

async def sync():
    gt_path = backend_dir / "data" / "ground_truth.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    splits = gt_data.get("splits") or gt_data.get("partitions", {})
    all_recs = splits.get("train", []) + splits.get("val", []) + splits.get("test", [])

    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    print(f"Connecting to PostgreSQL: {url}")
    engine = create_async_engine(url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # 1. Create or get bootstrap repository
        repo_stmt = text("SELECT id, name FROM repositories WHERE name = :name")
        res = (await session.execute(repo_stmt, {"name": "bootstrap-ground-truth-corpus"})).fetchone()
        if res:
            repo_id = res[0]
        else:
            repo_id = f"repo-{uuid.uuid4()}"
            await session.execute(
                text("INSERT INTO repositories (id, name, s3_key, created_at, updated_at) VALUES (:id, :name, :s3_key, :created_at, :updated_at)"),
                {
                    "id": repo_id,
                    "name": "bootstrap-ground-truth-corpus",
                    "s3_key": f"bootstrap/{repo_id}.zip",
                    "created_at": datetime.now(timezone.utc),
                    "updated_at": datetime.now(timezone.utc),
                }
            )

        # 2. Create or get bootstrap analysis run
        run_stmt = text("SELECT id FROM analysis_runs WHERE repository_id = :repo_id")
        run_res = (await session.execute(run_stmt, {"repo_id": repo_id})).fetchone()
        if run_res:
            analysis_run_id = run_res[0]
        else:
            analysis_run_id = f"run-{uuid.uuid4()}"
            await session.execute(
                text("INSERT INTO analysis_runs (id, repository_id, status, started_at) VALUES (:id, :repo_id, :status, :started_at)"),
                {"id": analysis_run_id, "repo_id": repo_id, "status": "completed", "started_at": datetime.now(timezone.utc)}
            )

        # 3. Check existing candidate issue IDs
        existing_ids = set((r[0] for r in (await session.execute(text("SELECT id FROM candidate_issues"))).fetchall()))

        inserted = 0
        for r in all_recs:
            cid = r.get("candidate_id") or r.get("id")
            if not cid or cid in existing_ids:
                continue

            gt_label = r.get("ground_truth") or r.get("label")
            raw_sev = str(r.get("severity") or "medium").lower()
            if raw_sev == "critical":
                raw_sev = "high"
            elif raw_sev not in ("high", "medium", "low"):
                raw_sev = "medium"

            raw_prio = str(r.get("priority") or "p2").lower()
            if raw_prio not in ("p1", "p2", "p3"):
                raw_prio = "p2"

            v_sev = raw_sev if gt_label == "TRUE_POSITIVE" else None
            v_prio = raw_prio if gt_label == "TRUE_POSITIVE" else None
            v_notes = f"Bootstrap Ground Truth: {gt_label}" if gt_label == "TRUE_POSITIVE" else "[FALSE_POSITIVE] Bootstrap False Alarm"
            v_at = datetime.now(timezone.utc)

            ins_stmt = text("""
                INSERT INTO candidate_issues (
                    id, analysis_run_id, file_path, line_number, "column",
                    rule_id, issue_type, title, description, message,
                    code_snippet, language, severity, urgency, evidence,
                    verified_severity, verified_priority, verification_notes,
                    verified_at, created_at
                ) VALUES (
                    :id, :analysis_run_id, :file_path, :line_number, :column,
                    :rule_id, :issue_type, :title, :description, :message,
                    :code_snippet, :language, :severity, :urgency, :evidence,
                    :verified_severity, :verified_priority, :verification_notes,
                    :verified_at, :created_at
                )
            """)

            await session.execute(ins_stmt, {
                "id": str(cid),
                "analysis_run_id": analysis_run_id,
                "file_path": r.get("file_path") or "unknown.py",
                "line_number": int(r.get("line_number") or 1),
                "column": int(r.get("column") or 1),
                "rule_id": r.get("rule_id") or "UNKNOWN",
                "issue_type": r.get("issue_type") or "Static Analysis Finding",
                "title": f"Candidate Defect: {r.get('rule_id')}",
                "description": r.get("message") or r.get("rule_id"),
                "message": r.get("message") or r.get("rule_id"),
                "code_snippet": r.get("code_snippet") or "",
                "language": (r.get("language") or "Python").lower(),
                "severity": raw_sev,
                "urgency": raw_prio,
                "evidence": json.dumps(r.get("evidence") or {}),
                "verified_severity": v_sev,
                "verified_priority": v_prio,
                "verification_notes": v_notes,
                "verified_at": v_at,
                "created_at": datetime.now(timezone.utc),
            })
            inserted += 1

        await session.commit()
        print(f"Successfully synced {inserted} ground truth candidate issues to PostgreSQL database.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(sync())
