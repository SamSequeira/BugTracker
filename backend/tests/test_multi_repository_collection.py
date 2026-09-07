"""
test_multi_repository_collection.py
-----------------------------------
Tests multi-repository and multi-analysis-run candidate issue collection,
foreign-key integrity preservation, review queue isolation, duplicate cluster detection,
and progress monitoring.
"""

from pathlib import Path
import tempfile
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from data.dbconnection.base import Base
from data.dbconnection.session import get_db
from app.main import app
from app.models.repository import Repository
from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_service import candidate_issue_service
from app.services.repository_analysis_service import repository_analysis_service


@pytest_asyncio.fixture
async def multi_repo_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client_multi(multi_repo_db: AsyncSession):
    async def override_get_db():
        yield multi_repo_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_multi_repository_and_multi_run_accumulation(multi_repo_db: AsyncSession, client_multi: AsyncClient):
    """
    Simulate:
    1. Repository A analyzed -> Run A1
    2. Repository B analyzed -> Run B1
    3. Repository A analyzed again -> Run A2 (generating potential duplicates across runs)
    Verify:
    - All candidate issues are persisted with distinct analysis_run_id foreign keys.
    - Review queue filtering properly handles all 3 states (unverified, partial, verified).
    - Dataset statistics accurately reflect progress.
    - Potential duplicate clusters across runs are identified without deleting records.
    - Verified training export returns only fully verified records.
    """
    # -----------------------------------------------------------------------
    # Step 1: Repository A with sample Python files
    # -----------------------------------------------------------------------
    with tempfile.TemporaryDirectory() as repo_a_dir, tempfile.TemporaryDirectory() as repo_b_dir:
        file_a = Path(repo_a_dir) / "calc.py"
        file_a.write_text("def div(n):\n    return n / 0\n", encoding="utf-8")

        file_b = Path(repo_b_dir) / "handler.py"
        file_b.write_text("def parse():\n    try:\n        pass\n    except:\n        pass\n", encoding="utf-8")

        # Create Repository A & Run A1
        repo_a = Repository(id="repo-alpha", name="Repo Alpha", s3_key="repos/alpha.zip")
        multi_repo_db.add(repo_a)
        await multi_repo_db.flush()

        run_a1 = AnalysisRun(id="run-a1", repository_id=repo_a.id, status="running")
        multi_repo_db.add(run_a1)
        await multi_repo_db.flush()

        # Run static analyzer on Repo A
        ast_a = ast_generator.generate_ast_for_repository(repo_a_dir)
        cand_a1 = candidate_issue_service.generate_from_repository(ast_a)
        await repository_analysis_service.complete_analysis_run(
            multi_repo_db, run_a1.id, {"candidate_issues": cand_a1["candidate_issues"], "total_files": 1, "supported_files": 1}
        )

        # -----------------------------------------------------------------------
        # Step 2: Repository B & Run B1
        # -----------------------------------------------------------------------
        repo_b = Repository(id="repo-beta", name="Repo Beta", s3_key="repos/beta.zip")
        multi_repo_db.add(repo_b)
        await multi_repo_db.flush()

        run_b1 = AnalysisRun(id="run-b1", repository_id=repo_b.id, status="running")
        multi_repo_db.add(run_b1)
        await multi_repo_db.flush()

        # Run static analyzer on Repo B
        ast_b = ast_generator.generate_ast_for_repository(repo_b_dir)
        cand_b1 = candidate_issue_service.generate_from_repository(ast_b)
        await repository_analysis_service.complete_analysis_run(
            multi_repo_db, run_b1.id, {"candidate_issues": cand_b1["candidate_issues"], "total_files": 1, "supported_files": 1}
        )

        # -----------------------------------------------------------------------
        # Step 3: Repository A analyzed again -> Run A2
        # -----------------------------------------------------------------------
        run_a2 = AnalysisRun(id="run-a2", repository_id=repo_a.id, status="running")
        multi_repo_db.add(run_a2)
        await multi_repo_db.flush()

        cand_a2 = candidate_issue_service.generate_from_repository(ast_a)
        await repository_analysis_service.complete_analysis_run(
            multi_repo_db, run_a2.id, {"candidate_issues": cand_a2["candidate_issues"], "total_files": 1, "supported_files": 1}
        )

    # -----------------------------------------------------------------------
    # Step 4: Verify Accumulation & Initial Review Queue
    # -----------------------------------------------------------------------
    # Total unverified issues should be at least 3 (from A1, B1, and A2)
    res_unverif = await client_multi.get("/candidate-issues?verification_status=unverified")
    assert res_unverif.status_code == 200
    unverif_data = res_unverif.json()
    assert unverif_data["total"] >= 3

    # Verify filtering by specific analysis run
    res_run_a1 = await client_multi.get(f"/candidate-issues?analysis_run_id=run-a1")
    assert res_run_a1.status_code == 200
    assert len(res_run_a1.json()["items"]) >= 1

    # -----------------------------------------------------------------------
    # Step 5: Test Partial & Full Manual Labelling
    # -----------------------------------------------------------------------
    all_issues = unverif_data["items"]
    issue_a1 = next(i for i in all_issues if i["analysis_run_id"] == "run-a1")
    issue_b1 = next(i for i in all_issues if i["analysis_run_id"] == "run-b1")
    issue_a2 = next(i for i in all_issues if i["analysis_run_id"] == "run-a2")

    # A1: Partially verify with severity only
    res_part_sev = await client_multi.patch(
        f"/candidate-issues/{issue_a1['id']}/labels",
        json={"verified_severity": "low"}
    )
    assert res_part_sev.status_code == 200
    assert res_part_sev.json()["verified_severity"] == "low"
    assert res_part_sev.json()["verified_priority"] is None
    assert res_part_sev.json()["severity"] == issue_a1["severity"]  # Detector severity preserved!

    # B1: Partially verify with priority only
    res_part_prio = await client_multi.patch(
        f"/candidate-issues/{issue_b1['id']}/labels",
        json={"verified_priority": "p3"}
    )
    assert res_part_prio.status_code == 200
    assert res_part_prio.json()["verified_severity"] is None
    assert res_part_prio.json()["verified_priority"] == "p3"

    # A2: Fully verify with both labels and reviewer notes
    res_full = await client_multi.patch(
        f"/candidate-issues/{issue_a2['id']}/labels",
        json={
            "verified_severity": "high",
            "verified_priority": "p1",
            "verification_notes": "Confirmed divide by zero in calc engine"
        }
    )
    assert res_full.status_code == 200
    assert res_full.json()["verified_severity"] == "high"
    assert res_full.json()["verified_priority"] == "p1"
    assert res_full.json()["verified_at"] is not None

    # -----------------------------------------------------------------------
    # Step 6: Verify Review Queue States
    # -----------------------------------------------------------------------
    # 1. Partial queue must contain issues A1 and B1
    res_queue_part = await client_multi.get("/candidate-issues?verification_status=partial")
    assert res_queue_part.status_code == 200
    part_ids = [i["id"] for i in res_queue_part.json()["items"]]
    assert issue_a1["id"] in part_ids
    assert issue_b1["id"] in part_ids

    # 2. Verified queue must contain issue A2
    res_queue_ver = await client_multi.get("/candidate-issues?verification_status=verified")
    assert res_queue_ver.status_code == 200
    ver_ids = [i["id"] for i in res_queue_ver.json()["items"]]
    assert issue_a2["id"] in ver_ids

    # -----------------------------------------------------------------------
    # Step 7: Verify Dataset Statistics
    # -----------------------------------------------------------------------
    res_stats = await client_multi.get("/candidate-issues/dataset/stats")
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert stats["total_candidate_issues"] >= 3
    assert stats["partially_verified"] == 2
    assert stats["fully_verified"] == 1
    # Only A2 is fully verified: verified_severity="high", verified_priority="p1"
    assert stats["severity_distribution"]["high"] == 1
    assert "critical" not in stats["severity_distribution"]
    assert stats["priority_distribution"]["p1"] == 1
    assert stats["priority_distribution"]["p3"] == 0

    # -----------------------------------------------------------------------
    # Step 8: Verify Duplicate Detection Across Runs
    # -----------------------------------------------------------------------
    res_dups = await client_multi.get("/candidate-issues/duplicates")
    assert res_dups.status_code == 200
    dups_data = res_dups.json()
    assert dups_data["total_duplicate_groups"] >= 1
    # Issue A1 and Issue A2 share the same rule, file, line, code_snippet
    dup_group = next(
        (g for g in dups_data["groups"] if g["code_snippet"] == "n / 0" or "calc.py" in g["file_path"]),
        None
    )
    assert dup_group is not None
    assert issue_a1["id"] in dup_group["issue_ids"]
    assert issue_a2["id"] in dup_group["issue_ids"]
    # Verify no records were deleted
    res_all = await client_multi.get("/candidate-issues")
    assert res_all.json()["total"] >= 3

    # -----------------------------------------------------------------------
    # Step 9: Verify Training Dataset Export
    # -----------------------------------------------------------------------
    res_export = await client_multi.get("/candidate-issues/dataset/verified")
    assert res_export.status_code == 200
    export_data = res_export.json()
    assert export_data["total"] == 1
    record = export_data["records"][0]
    assert record["id"] == issue_a2["id"]
    assert record["severity"] == "high"  # mapped from verified_severity
    assert record["priority"] == "p1"  # mapped from verified_priority
    assert record["detector_severity"] == "high"  # detector prediction
