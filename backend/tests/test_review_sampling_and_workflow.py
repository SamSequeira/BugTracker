"""
test_review_sampling_and_workflow.py
------------------------------------
Tests for deterministic review sampling, human labelling workflow,
false positive handling, and review batch API endpoints.
"""

from datetime import datetime, timezone
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
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.services.dataset_preparation import ReviewSampler, classify_provenance


def test_review_sampler_deterministic_and_diverse():
    """Verify ReviewSampler produces reproducible, diverse sample batches across repos/rules."""
    records = []
    severities = ["high", "medium", "low"]
    rules = ["PY_DIV_001", "PY_RES_001", "JAVA_EQ_001", "JAVA_RES_001", "JS_EQ_001", "JS_AWA_001"]
    languages = ["Python", "Java", "JavaScript"]
    repos = ["repo_a", "repo_b", "repo_c"]

    for i in range(300):
        r_id = rules[i % len(rules)]
        lang = languages[i % len(languages)]
        repo = repos[i % len(repos)]
        records.append({
            "id": f"real_usable_rec_{i}",
            "file_path": f"src/module_{i % 20}.py",
            "line_number": i + 1,
            "code_snippet": f"code_line_{i}()",
            "rule_id": r_id,
            "issue_type": f"type_{r_id}",
            "language": lang,
            "repository_name": repo,
            "repository_id": f"id_{repo}",
            "severity": severities[i % len(severities)],
            "urgency": "medium",
            "verified_severity": None,
            "verified_priority": None,
            "verified_at": None,
        })

    sampler1 = ReviewSampler(random_seed=42)
    batch1, report1 = sampler1.sample(records, target_size=60, max_per_rule_per_repo=10)

    sampler2 = ReviewSampler(random_seed=42)
    batch2, report2 = sampler2.sample(records, target_size=60, max_per_rule_per_repo=10)

    # 1. Deterministic repeatability
    assert len(batch1) == 60
    assert [b["id"] for b in batch1] == [b["id"] for b in batch2]

    # 2. Diversity coverage
    assert len(report1["repositories_distribution"]) == 3
    assert len(report1["languages_distribution"]) == 3
    assert len(report1["rules_distribution"]) == 6

    # 3. Cap enforcement per rule per repo
    for count in report1["rules_distribution"].values():
        assert count <= 25


def test_review_sampler_excludes_test_and_incomplete_records():
    """Verify sampler strictly excludes test fixtures and incomplete candidate issues."""
    mixed_records = [
        # Test fixture
        {
            "id": "pg-test-001",
            "file_path": "test.py",
            "code_snippet": "x / 0",
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "language": "Python",
            "repository_name": "test_repo",
        },
        # Incomplete record (missing snippet)
        {
            "id": "real_missing_snippet_002",
            "file_path": "src/core.py",
            "code_snippet": "",
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "language": "Python",
            "repository_name": "real_repo",
        },
        # Already verified record
        {
            "id": "real_already_verified_003",
            "file_path": "src/core.py",
            "code_snippet": "return a / b",
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "language": "Python",
            "repository_name": "real_repo",
            "verified_severity": "high",
            "verified_priority": "p2",
        },
        # Valid unverified real record
        {
            "id": "real_usable_004",
            "file_path": "src/core.py",
            "code_snippet": "return total / count",
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "language": "Python",
            "repository_name": "real_repo",
            "verified_severity": None,
            "verified_priority": None,
            "verified_at": None,
        },
    ]

    sampler = ReviewSampler(random_seed=42)
    batch, report = sampler.sample(mixed_records, target_size=10)

    assert len(batch) == 1
    assert batch[0]["id"] == "real_usable_004"
    assert report["total_available_unverified_real"] == 1


@pytest_asyncio.fixture
async def workflow_db():
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
async def workflow_client(workflow_db: AsyncSession):
    async def override_get_db():
        yield workflow_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_human_confirmation_and_false_positive_workflow(workflow_client: AsyncClient, workflow_db: AsyncSession):
    """Test manual issue confirmation vs false positive handling via repository and API."""
    repo = Repository(id="wf-repo-1", name="wf-repo", s3_key="s3://key")
    workflow_db.add(repo)
    await workflow_db.flush()

    run = AnalysisRun(id="wf-run-1", repository_id=repo.id, status="completed")
    workflow_db.add(run)
    await workflow_db.flush()

    iss1 = CandidateIssue(
        id="wf-iss-1",
        analysis_run_id=run.id,
        title="Title 1",
        description="Desc 1",
        file_path="src/calc.py",
        line_number=10,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero",
        code_snippet="a / 0",
        language="Python",
        severity="medium",
        urgency="medium",
    )
    iss2 = CandidateIssue(
        id="wf-iss-2",
        analysis_run_id=run.id,
        title="Title 2",
        description="Desc 2",
        file_path="src/safe.py",
        line_number=20,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by potentially zero",
        code_snippet="a / count",
        language="Python",
        severity="medium",
        urgency="medium",
    )
    workflow_db.add_all([iss1, iss2])
    await workflow_db.commit()

    # 1. Human confirms issue 1 as High severity, P2 priority
    patch_payload1 = {
        "verified_severity": "high",
        "verified_priority": "p2",
        "verification_notes": "Confirmed zero divisor on main payment execution path.",
    }
    res1 = await workflow_client.patch("/candidate-issues/wf-iss-1/labels", json=patch_payload1)
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["severity"] == "medium"  # Original detector baseline preserved
    assert data1["verified_severity"] == "high"
    assert data1["verified_priority"] == "p2"
    assert data1["verified_at"] is not None

    # 2. Human marks issue 2 as False Positive
    patch_payload2 = {
        "is_false_positive": True,
        "verification_notes": "False positive: guarded by check if count > 0 above.",
    }
    res2 = await workflow_client.patch("/candidate-issues/wf-iss-2/labels", json=patch_payload2)
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["severity"] == "medium"  # Original detector baseline preserved
    assert data2["verified_severity"] is None  # Excluded from ML labels
    assert data2["verified_priority"] is None  # Excluded from ML labels
    assert data2["verified_at"] is not None
    assert "[FALSE_POSITIVE]" in data2["verification_notes"]

    # 3. Verify ML Training Dataset query retrieves ONLY confirmed issue 1
    training_data = await candidate_issue_repository.get_verified_training_dataset(workflow_db)
    assert len(training_data) == 1
    assert training_data[0]["id"] == "wf-iss-1"
    assert training_data[0]["severity"] == "high"
    assert training_data[0]["priority"] == "p2"

    # 4. Verify review queue filters
    unverified_items, unverified_total = await candidate_issue_repository.list_issues(
        workflow_db, verification_status="unverified"
    )
    assert unverified_total == 0  # Both have been reviewed

    fp_items, fp_total = await candidate_issue_repository.list_issues(
        workflow_db, verification_status="false_positive"
    )
    assert fp_total == 1
    assert fp_items[0].id == "wf-iss-2"


@pytest.mark.asyncio
async def test_review_batch_api_endpoint(workflow_client: AsyncClient, workflow_db: AsyncSession):
    """Test POST /candidate-issues/review/batch generates balanced batch."""
    repo = Repository(id="batch-repo-1", name="sample-app", s3_key="s3://key")
    workflow_db.add(repo)
    await workflow_db.flush()

    run = AnalysisRun(id="batch-run-1", repository_id=repo.id, status="completed")
    workflow_db.add(run)
    await workflow_db.flush()

    for i in range(15):
        iss = CandidateIssue(
            id=f"real-batch-iss-{i}",
            analysis_run_id=run.id,
            title=f"Title {i}",
            description=f"Desc {i}",
            file_path=f"src/app/component_{i}.py",
            line_number=i + 1,
            rule_id=f"PY_RULE_{i % 3}",
            issue_type="division_by_zero",
            message=f"Msg {i}",
            code_snippet=f"snippet_{i}()",
            language="Python",
            severity="medium",
            urgency="medium",
        )
        workflow_db.add(iss)
    await workflow_db.commit()

    res = await workflow_client.post("/candidate-issues/review/batch", json={"target_size": 10, "random_seed": 42})
    assert res.status_code == 200
    data = res.json()
    assert data["total_available_unverified_real"] == 15
    assert data["sampled_count"] == 10
    assert len(data["items"]) == 10
    assert data["seed"] == 42
    assert "Python" in data["languages_distribution"]
