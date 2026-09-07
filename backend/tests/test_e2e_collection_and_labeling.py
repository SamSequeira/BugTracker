"""
test_e2e_collection_and_labeling.py
-----------------------------------
End-to-end verification of the full workflow:
Source Code -> Static Analyzer -> PostgreSQL Persistence ->
Review Queue -> Manual Labelling -> Progress Stats -> Verified Dataset Export.
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
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_service import candidate_issue_service
from app.services.repository_analysis_service import repository_analysis_service


@pytest_asyncio.fixture
async def test_db_e2e():
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
async def client_e2e(test_db_e2e: AsyncSession):
    async def override_get_db():
        yield test_db_e2e

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_full_pipeline_collection_to_export(test_db_e2e: AsyncSession, client_e2e: AsyncClient):
    """
    E2E Test:
    1. Static Analyzer scans sample source code.
    2. Candidate issues are generated.
    3. Issues are persisted into DB with analysis run.
    4. Reviewer lists unverified issues from review queue.
    5. Reviewer inspects single issue.
    6. Reviewer assigns verified_severity and verified_priority.
    7. Reviewer verifies progress stats.
    8. Reviewer exports verified dataset.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = Path(temp_dir) / "math_demo.py"
        test_file.write_text(
            "def calculate(total):\n"
            "    count = 0\n"
            "    return total / 0\n",
            encoding="utf-8",
        )

        # 1. AST generation
        ast_result = ast_generator.generate_ast_for_repository(temp_dir)

        # 2. Candidate issue detection
        candidate_result = candidate_issue_service.generate_from_repository(ast_result)
        raw_issues = candidate_result["candidate_issues"]
        assert len(raw_issues) >= 1

        # 3. Create repository and analysis run in DB
        repo = Repository(
            id=str(uuid.uuid4()),
            name="e2e-repo",
            s3_key="repositories/e2e.zip",
        )
        test_db_e2e.add(repo)
        await test_db_e2e.flush()

        run = AnalysisRun(
            id=str(uuid.uuid4()),
            repository_id=repo.id,
            status="running",
        )
        test_db_e2e.add(run)
        await test_db_e2e.flush()

        # Persist findings via repository_analysis_service
        analysis_payload = {
            "total_files": ast_result["total_files"],
            "supported_files": ast_result["supported_files"],
            "candidate_issues": raw_issues,
        }
        completed_run = await repository_analysis_service.complete_analysis_run(
            test_db_e2e, run.id, analysis_payload
        )
        assert completed_run.status == "completed"

        # 4. Review queue: Query unverified issues
        res_queue = await client_e2e.get(f"/candidate-issues?analysis_run_id={run.id}&verification_status=unverified")
        assert res_queue.status_code == 200
        queue_data = res_queue.json()
        assert queue_data["total"] >= 1
        target_issue = queue_data["items"][0]
        issue_id = target_issue["id"]

        assert target_issue["severity"] == "high"  # detector severity
        assert target_issue["verified_severity"] is None
        assert target_issue["verified_priority"] is None

        # 5. Retrieve individual issue
        res_single = await client_e2e.get(f"/candidate-issues/{issue_id}")
        assert res_single.status_code == 200
        assert res_single.json()["id"] == issue_id

        # 6. Manual review / label assignment
        res_label = await client_e2e.patch(
            f"/candidate-issues/{issue_id}/labels",
            json={
                "verified_severity": "high",
                "verified_priority": "p1",
                "verification_notes": "Confirmed division by zero in core mathematical routine",
            },
        )
        assert res_label.status_code == 200
        labeled = res_label.json()
        assert labeled["severity"] == "high"  # Detector baseline remains unchanged!
        assert labeled["verified_severity"] == "high"  # Ground truth
        assert labeled["verified_priority"] == "p1"  # Ground truth
        assert labeled["verified_at"] is not None

        # 7. Check dataset progress stats
        res_stats = await client_e2e.get("/candidate-issues/dataset/stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert stats["fully_verified"] >= 1
        assert stats["severity_distribution"]["high"] >= 1
        assert stats["priority_distribution"]["p1"] >= 1

        # 8. Export verified training dataset
        res_dataset = await client_e2e.get("/candidate-issues/dataset/verified")
        assert res_dataset.status_code == 200
        dataset = res_dataset.json()
        assert dataset["total"] >= 1

        exported_rec = next(r for r in dataset["records"] if r["id"] == issue_id)
        assert exported_rec["severity"] == "high"  # Ground truth target
        assert exported_rec["priority"] == "p1"  # Ground truth target
        assert exported_rec["detector_severity"] == "high"  # Preserved detector prediction
        assert exported_rec["rule_id"] == "PY_DIV_001"
