"""
test_dataset_readiness.py
-------------------------
Tests for dataset readiness gate, provenance classification,
and enhanced progress statistics API endpoints.
"""

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
from app.services.dataset_preparation import (
    classify_provenance,
    evaluate_dataset_readiness,
    DatasetValidator,
)


def test_classify_provenance():
    """Verify classification of test/synthetic vs real-usable vs real-incomplete."""
    # Test fixture marker in ID or path
    test_rec = {
        "id": "pg-test-123",
        "file_path": "test.py",
        "code_snippet": "x / 0",
        "rule_id": "RULE_1",
        "issue_type": "div",
    }
    assert classify_provenance(test_rec) == "TEST_OR_SYNTHETIC"

    # Real but missing snippet
    incomplete_rec = {
        "id": "real_issue_456",
        "file_path": "src/core/math.py",
        "code_snippet": "",
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
    }
    assert classify_provenance(incomplete_rec) == "REAL_INCOMPLETE"

    # Real usable record
    usable_rec = {
        "id": "real_issue_789",
        "file_path": "src/core/math.py",
        "code_snippet": "return total / denominator",
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
    }
    assert classify_provenance(usable_rec) == "REAL_USABLE"


def test_readiness_scorecard_insufficient_data():
    """Verify readiness gate fails on insufficient sample count and missing diversity."""
    sparse_records = [
        {
            "id": f"rec_{i}",
            "file_path": f"src/mod_{i}.py",
            "code_snippet": f"snippet_{i}",
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "language": "Python",
            "verified_severity": "critical",
            "verified_priority": "p1",
            "repository_id": "repo_1",
        }
        for i in range(10)
    ]

    report = evaluate_dataset_readiness(sparse_records)

    assert report["dataset_status"] == "NOT READY FOR TRAINING"
    assert report["status"] == "NOT READY"
    assert report["readiness_score"] < 50.0

    # Verify specific criteria failures
    vol_crit = next(c for c in report["criteria"] if c["criterion"] == "Usable Unique Records")
    assert vol_crit["status"] == "FAIL"

    repo_crit = next(c for c in report["criteria"] if c["criterion"] == "Repository Diversity")
    assert repo_crit["status"] == "FAIL"

    # Verify actionable recommendations exist
    assert len(report["recommendations"]) > 0


def test_readiness_scorecard_sufficient_diverse_data():
    """Verify readiness gate passes when dataset has >=150 records, >=5 repos, >=3 langs, >=10 rules, and balanced classes."""
    severities = ["critical", "high", "medium", "low"]
    priorities = ["p1", "p2", "p3", "p4"]
    languages = ["Python", "Java", "JavaScript"]

    diverse_records = []
    for i in range(160):
        sev = severities[i % 4]
        prio = priorities[i % 4]
        lang = languages[i % 3]
        rule = f"RULE_{lang[:2].upper()}_{i % 12:02d}"
        repo = f"repo_project_{i % 6}"

        diverse_records.append({
            "id": f"diverse_rec_{i}",
            "file_path": f"src/pkg_{i % 8}/module_{i}.py",
            "code_snippet": f"result = calculate_val_{i}()",
            "rule_id": rule,
            "issue_type": f"issue_type_{i % 8}",
            "language": lang,
            "verified_severity": sev,
            "verified_priority": prio,
            "repository_id": repo,
            "group_id": f"grp_{i % 40}",
        })

    report = evaluate_dataset_readiness(
        records=diverse_records,
        deduplication_stats={"final_unique_records": 160},
        validation_report={"provenance_breakdown": {"real_usable": 160, "test_or_synthetic": 0, "real_incomplete": 0}},
        split_metadata={"cross_split_group_overlap": 0},
    )

    assert "READY FOR MODEL TRAINING REVIEW" in report["dataset_status"]
    assert report["readiness_score"] >= 80.0


@pytest_asyncio.fixture
async def readiness_db():
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
async def readiness_client(readiness_db: AsyncSession):
    async def override_get_db():
        yield readiness_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_readiness_and_enhanced_stats_api(readiness_client: AsyncClient, readiness_db: AsyncSession):
    """Test GET /candidate-issues/dataset/readiness and enhanced /dataset/stats."""
    # Seed 1 repo, 1 run, 4 verified candidate issues
    repo = Repository(id="api-repo", name="api-repo", s3_key="s3://key")
    readiness_db.add(repo)
    await readiness_db.flush()

    run = AnalysisRun(id="api-run", repository_id=repo.id, status="completed")
    readiness_db.add(run)
    await readiness_db.flush()

    for i in range(4):
        iss = CandidateIssue(
            id=f"readiness-iss-{i}",
            analysis_run_id=run.id,
            title=f"Title {i}",
            description=f"Desc {i}",
            file_path=f"src/file_{i}.py",
            line_number=i * 5,
            rule_id=f"PY_RULE_{i}",
            issue_type=f"type_{i}",
            message=f"Msg {i}",
            code_snippet=f"snippet_{i}",
            language="Python",
            severity="high",
            urgency="high",
            verified_severity=["critical", "high", "medium", "low"][i],
            verified_priority=["p1", "p2", "p3", "p4"][i],
        )
        readiness_db.add(iss)

    await readiness_db.commit()

    # Test /dataset/stats
    res_stats = await readiness_client.get("/candidate-issues/dataset/stats")
    assert res_stats.status_code == 200
    d_stats = res_stats.json()
    assert d_stats["total_candidate_issues"] == 4
    assert d_stats["fully_verified"] == 4
    assert "provenance_breakdown" in d_stats
    assert "diversity_counts" in d_stats
    assert d_stats["diversity_counts"]["unique_rules"] == 4

    # Test /dataset/readiness
    res_readiness = await readiness_client.get("/candidate-issues/dataset/readiness")
    assert res_readiness.status_code == 200
    d_readiness = res_readiness.json()
    assert d_readiness["total_candidate_issues_in_db"] == 4
    assert "NOT READY FOR TRAINING" in d_readiness["readiness"]["dataset_status"]
    assert len(d_readiness["readiness"]["criteria"]) >= 10
