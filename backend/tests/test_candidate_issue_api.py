"""
test_candidate_issue_api.py
---------------------------
API endpoint tests for Candidate Issues, review queue filtering,
dataset progress stats, duplicate detection, and manual verification labeling.
"""

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


@pytest_asyncio.fixture
async def api_db():
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
async def client(api_db: AsyncSession):
    async def override_get_db():
        yield api_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_data(api_db: AsyncSession):
    repo = Repository(
        id=str(uuid.uuid4()),
        name="api-test-repo",
        s3_key="repositories/api-test-repo.zip",
    )
    api_db.add(repo)
    await api_db.flush()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        status="completed",
    )
    api_db.add(run)
    await api_db.flush()

    # Issue 1: UNVERIFIED
    issue1 = CandidateIssue(
        id="api-issue-1",
        analysis_run_id=run.id,
        title="Division by Zero (PY_DIV_001)",
        description="Division by zero error",
        file_path="src/math.py",
        line_number=5,
        column=2,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero divisor is 0",
        code_snippet="1 / 0",
        evidence={"operator": "/", "right_operand": "0"},
        language="Python",
        severity="high",  # detector output
        urgency="high",
        verified_severity=None,
        verified_priority=None,
    )

    # Issue 2: FULLY VERIFIED
    issue2 = CandidateIssue(
        id="api-issue-2",
        analysis_run_id=run.id,
        title="Bare Except (PY_EXC_001)",
        description="Bare except clause",
        file_path="src/server.py",
        line_number=20,
        column=0,
        rule_id="PY_EXC_001",
        issue_type="bare_except",
        message="Bare except caught",
        code_snippet="except:",
        evidence={},
        language="Python",
        severity="medium",  # detector output
        urgency="medium",
        verified_severity="high",  # ground truth
        verified_priority="p2",  # ground truth
    )

    # Issue 3: PARTIALLY VERIFIED (Severity only)
    issue3 = CandidateIssue(
        id="api-issue-3",
        analysis_run_id=run.id,
        title="Mutable Default Arg (PY_MUT_001)",
        description="Mutable default argument",
        file_path="src/utils.py",
        line_number=15,
        column=0,
        rule_id="PY_MUT_001",
        issue_type="mutable_default_argument",
        message="Mutable default argument in function def",
        code_snippet="def f(x=[]):",
        evidence={},
        language="Python",
        severity="low",
        urgency="low",
        verified_severity="low",
        verified_priority=None,
    )

    # Issue 4: DUPLICATE OF ISSUE 1 (same rule_id, file_path, line_number, code_snippet)
    issue4 = CandidateIssue(
        id="api-issue-4-dup",
        analysis_run_id=run.id,
        title="Division by Zero (PY_DIV_001) duplicate",
        description="Division by zero duplicate",
        file_path="src/math.py",
        line_number=5,
        column=2,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero divisor is 0",
        code_snippet="1 / 0",
        evidence={"operator": "/"},
        language="Python",
        severity="high",
        urgency="high",
        verified_severity=None,
        verified_priority=None,
    )

    api_db.add_all([issue1, issue2, issue3, issue4])
    await api_db.commit()

    return repo, run, issue1, issue2, issue3, issue4


@pytest.mark.asyncio
async def test_list_candidate_issues(client: AsyncClient, seed_data):
    """Test listing candidate issues with pagination."""
    response = await client.get("/candidate-issues")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert len(data["items"]) == 4


@pytest.mark.asyncio
async def test_review_queue_filtering_by_status(client: AsyncClient, seed_data):
    """Test review queue filtering by unverified, partial, and verified status."""
    # 1. Unverified (issues 1 and 4)
    res_unverif = await client.get("/candidate-issues?verification_status=unverified")
    assert res_unverif.status_code == 200
    d_unverif = res_unverif.json()
    assert d_unverif["total"] == 2
    for item in d_unverif["items"]:
        assert item["verified_severity"] is None
        assert item["verified_priority"] is None

    # 2. Partial (issue 3)
    res_part = await client.get("/candidate-issues?verification_status=partial")
    assert res_part.status_code == 200
    d_part = res_part.json()
    assert d_part["total"] == 1
    assert d_part["items"][0]["id"] == "api-issue-3"

    # 3. Verified (issue 2)
    res_verif = await client.get("/candidate-issues?verification_status=verified")
    assert res_verif.status_code == 200
    d_verif = res_verif.json()
    assert d_verif["total"] == 1
    assert d_verif["items"][0]["id"] == "api-issue-2"


@pytest.mark.asyncio
async def test_get_candidate_issue_by_id(client: AsyncClient, seed_data):
    """Test retrieving a single candidate issue by ID."""
    response = await client.get("/candidate-issues/api-issue-1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "api-issue-1"
    assert data["severity"] == "high"  # detector severity
    assert data["verified_severity"] is None
    assert data["verified_priority"] is None


@pytest.mark.asyncio
async def test_update_verified_labels_partial_and_full(client: AsyncClient, seed_data):
    """Test updating verified labels independently and together."""
    # 1. Partial update: severity only
    res1 = await client.patch(
        "/candidate-issues/api-issue-1/labels",
        json={"verified_severity": "low"},
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["severity"] == "high"  # detector severity preserved!
    assert d1["verified_severity"] == "low"
    assert d1["verified_priority"] is None

    # 2. Partial update: priority only
    res2 = await client.patch(
        "/candidate-issues/api-issue-1/labels",
        json={"verified_priority": "p1", "verification_notes": "Verified by lead reviewer"},
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["severity"] == "high"  # detector severity preserved!
    assert d2["verified_severity"] == "low"
    assert d2["verified_priority"] == "p1"
    assert d2["verified_at"] is not None
    assert "lead reviewer" in d2["verification_notes"]


@pytest.mark.asyncio
async def test_reject_invalid_verified_labels_via_api(client: AsyncClient, seed_data):
    """Test API rejects invalid verified severity ('extreme', 'critical') and priority ('p0')."""
    # Invalid severity: extreme
    res_bad_sev = await client.patch(
        "/candidate-issues/api-issue-1/labels",
        json={"verified_severity": "extreme"},
    )
    assert res_bad_sev.status_code == 422

    # Invalid severity: critical (not supported in 3-tier system)
    res_critical = await client.patch(
        "/candidate-issues/api-issue-1/labels",
        json={"verified_severity": "critical"},
    )
    assert res_critical.status_code == 422

    # Invalid priority
    res_bad_prio = await client.patch(
        "/candidate-issues/api-issue-1/labels",
        json={"verified_priority": "p0"},
    )
    assert res_bad_prio.status_code == 422


@pytest.mark.asyncio
async def test_get_dataset_statistics_endpoint(client: AsyncClient, seed_data):
    """Test GET /candidate-issues/dataset/stats returns correct progress & distributions."""
    response = await client.get("/candidate-issues/dataset/stats")
    assert response.status_code == 200
    data = response.json()

    assert data["total_candidate_issues"] == 4
    assert data["unverified"] == 2
    assert data["partially_verified"] == 1
    assert data["fully_verified"] == 1

    # In seed_data, issue 2 is fully verified: verified_severity="high", verified_priority="p2"
    assert data["severity_distribution"]["high"] == 1
    assert data["severity_distribution"]["medium"] == 0
    assert "critical" not in data["severity_distribution"]
    assert data["priority_distribution"]["p2"] == 1
    assert data["priority_distribution"]["p1"] == 0


@pytest.mark.asyncio
async def test_duplicate_candidate_issues_endpoint(client: AsyncClient, seed_data):
    """Test GET /candidate-issues/duplicates identifies potential duplicate groups."""
    response = await client.get("/candidate-issues/duplicates")
    assert response.status_code == 200
    data = response.json()

    assert data["total_duplicate_groups"] == 1
    assert data["total_duplicate_issues"] == 2

    group = data["groups"][0]
    assert group["rule_id"] == "PY_DIV_001"
    assert group["file_path"] == "src/math.py"
    assert group["line_number"] == 5
    assert group["code_snippet"] == "1 / 0"
    assert set(group["issue_ids"]) == {"api-issue-1", "api-issue-4-dup"}


@pytest.mark.asyncio
async def test_get_verified_training_dataset_endpoint(client: AsyncClient, seed_data):
    """
    Test GET /candidate-issues/dataset/verified returns only fully verified records
    with explicit mapping: severity -> verified_severity, priority -> verified_priority.
    """
    response = await client.get("/candidate-issues/dataset/verified")
    assert response.status_code == 200
    data = response.json()

    # Only api-issue-2 is fully verified in seed_data
    assert data["total"] == 1
    record = data["records"][0]
    assert record["id"] == "api-issue-2"
    assert record["severity"] == "high"  # from verified_severity
    assert record["priority"] == "p2"  # from verified_priority
    assert record["detector_severity"] == "medium"  # from original severity
    assert record["rule_id"] == "PY_EXC_001"
    assert record["language"] == "Python"


@pytest.mark.asyncio
async def test_get_candidate_issue_context_endpoint(client: AsyncClient, seed_data, tmp_path):
    """
    Test GET /candidate-issues/{issue_id}/context retrieves source context without crashing.
    """
    # 1. Non-existent issue returns 404
    resp_404 = await client.get("/candidate-issues/non-existent-id/context")
    assert resp_404.status_code == 404

    # 2. Existing issue without accessible file on disk returns found=False with clear notice
    resp_missing = await client.get("/candidate-issues/api-issue-1/context")
    assert resp_missing.status_code == 200
    data_missing = resp_missing.json()
    assert data_missing["issue_id"] == "api-issue-1"
    assert data_missing["found"] is False
    assert "[Notice]" in data_missing["formatted_text"]


@pytest.mark.asyncio
async def test_serve_review_dashboard_html(client: AsyncClient):
    """
    Test GET /review serves the standalone temporary review dashboard HTML.
    """
    response = await client.get("/review")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "BugTracker — Ground Truth Review" in response.text
    assert "TEMPORARY DATASET REVIEW TOOL" in response.text

