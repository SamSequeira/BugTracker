"""
test_analysis_status_high_issues.py
-----------------------------------
Tests for the repository analysis-status endpoint and high_open_issues calculation:
- Repository with 7 total findings and 5 high + 2 medium -> high_open_issues = 5
- If 2 of those 5 high issues are resolved -> high_open_issues = 3
- If there are no high open issues -> high_open_issues = 0
"""

import uuid
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
from app.models.issue_status import IssueStatus
from app.schemas.repository import AnalysisStatusResponse


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


@pytest.mark.asyncio
async def test_analysis_status_none(client: AsyncClient, api_db: AsyncSession):
    """When no analysis run exists for a repo, high_open_issues is 0 and status is 'none'."""
    repo = Repository(
        id=str(uuid.uuid4()),
        name="test-repo-none",
        s3_key="repositories/test-repo-none.zip",
    )
    api_db.add(repo)
    await api_db.commit()

    resp = await client.get(f"/api/v1/repositories/{repo.id}/analysis-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "none"
    assert data["high_open_issues"] == 0
    assert data["candidate_issues_count"] == 0


@pytest.mark.asyncio
async def test_analysis_status_high_open_issues_count(client: AsyncClient, api_db: AsyncSession):
    """
    Verify:
    1. 7 total findings (5 high + 2 medium) -> high_open_issues = 5
    2. If 2 of those 5 high issues are resolved -> high_open_issues = 3
    3. If remaining 3 high issues are resolved -> high_open_issues = 0
    """
    repo = Repository(
        id=str(uuid.uuid4()),
        name="test-repo-kpi",
        s3_key="repositories/test-repo-kpi.zip",
    )
    api_db.add(repo)
    await api_db.flush()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        status="completed",
        total_files=10,
        supported_files=10,
        candidate_issues_count=7,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    api_db.add(run)
    await api_db.flush()

    # 5 High issues
    high_issues = []
    high_statuses = []
    for i in range(5):
        issue_id = str(uuid.uuid4())
        issue = CandidateIssue(
            id=issue_id,
            analysis_run_id=run.id,
            title=f"High Issue {i+1}",
            description=f"High finding {i+1}",
            file_path="src/main.py",
            line_number=i * 10 + 1,
            severity="high",
            urgency="high",
        )
        status = IssueStatus(
            id=str(uuid.uuid4()),
            candidate_issue_id=issue_id,
            status="open",
        )
        high_issues.append(issue)
        high_statuses.append(status)
        api_db.add(issue)
        api_db.add(status)

    # 2 Medium issues
    for i in range(2):
        issue_id = str(uuid.uuid4())
        issue = CandidateIssue(
            id=issue_id,
            analysis_run_id=run.id,
            title=f"Medium Issue {i+1}",
            description=f"Medium finding {i+1}",
            file_path="src/utils.py",
            line_number=i * 5 + 1,
            severity="medium",
            urgency="medium",
        )
        status = IssueStatus(
            id=str(uuid.uuid4()),
            candidate_issue_id=issue_id,
            status="open",
        )
        api_db.add(issue)
        api_db.add(status)

    await api_db.commit()

    # Step 1: All 5 high issues open -> high_open_issues should be 5
    resp = await client.get(f"/api/v1/repositories/{repo.id}/analysis-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["candidate_issues_count"] == 7
    assert data["high_open_issues"] == 5

    # Step 2: Resolve 2 of the 5 high issues -> high_open_issues should be 3
    high_statuses[0].status = "resolved"
    high_statuses[1].status = "resolved"
    await api_db.commit()

    resp = await client.get(f"/api/v1/repositories/{repo.id}/analysis-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["high_open_issues"] == 3

    # Step 3: Resolve the remaining 3 high issues -> high_open_issues should be 0
    high_statuses[2].status = "resolved"
    high_statuses[3].status = "resolved"
    high_statuses[4].status = "resolved"
    await api_db.commit()

    resp = await client.get(f"/api/v1/repositories/{repo.id}/analysis-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["high_open_issues"] == 0


@pytest.mark.asyncio
async def test_analysis_status_3_high_open_issues(client: AsyncClient, api_db: AsyncSession):
    """
    Verify:
    When DB contains 3 CandidateIssue records for a repository and all 3 are High/open:
    - candidate_issues_count (Total Vulnerabilities) = 3
    - high_open_issues (Open High Issues) = 3
    """
    repo = Repository(
        id=str(uuid.uuid4()),
        name="test-repo-3-high",
        s3_key="repositories/test-repo-3-high.zip",
    )
    api_db.add(repo)
    await api_db.flush()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        status="completed",
        total_files=5,
        supported_files=5,
        candidate_issues_count=0,  # e.g. stale snapshot before issues added
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    api_db.add(run)
    await api_db.flush()

    for i in range(3):
        issue_id = str(uuid.uuid4())
        issue = CandidateIssue(
            id=issue_id,
            analysis_run_id=run.id,
            title=f"Semantic High Issue {i+1}",
            description=f"Semantic defect {i+1}",
            file_path="app/main.py",
            line_number=20 + i,
            severity="high",
            urgency="needs_review",
        )
        status = IssueStatus(
            id=str(uuid.uuid4()),
            candidate_issue_id=issue_id,
            status="open",
        )
        api_db.add(issue)
        api_db.add(status)

    await api_db.commit()

    resp = await client.get(f"/api/v1/repositories/{repo.id}/analysis-status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["candidate_issues_count"] == 3
    assert data["high_open_issues"] == 3

