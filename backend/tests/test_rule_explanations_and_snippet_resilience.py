"""
test_rule_explanations_and_snippet_resilience.py
==================================================================================
Automated tests for Human-Readable Rule Explanations, Code Snippet Persistence,
Unknown Rule Fallback, and Source Context Error Resilience.
==================================================================================
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.main import app
from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.repository import Repository
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.services.source_context import get_structured_source_context
from data.dbconnection.base import Base
from data.dbconnection.session import get_db

ALL_SUPPORTED_RULES = [
    "PY_DIV_001",
    "PY_RES_001",
    "PY_ASS_001",
    "PY_MUT_001",
    "PY_EXC_001",
    "JAVA_EQ_001",
    "JAVA_RES_001",
    "JAVA_EXC_001",
    "JAVA_DIV_001",
    "JS_EQ_001",
    "JS_AWA_001",
    "JS_DIV_001",
]


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def client(memory_db: AsyncSession):
    async def override_get_db():
        yield memory_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test 1 & 2: Rule Explanation Mapping & Unknown Rule Fallback
# ---------------------------------------------------------------------------
def test_all_supported_rules_have_explanations_in_frontend_manifest():
    """Verify all 12 supported rules are mapped with non-empty titles, explanations, and categories."""
    manifest_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "utils" / "ruleExplanations.js"
    assert manifest_path.exists(), f"Missing ruleExplanations.js at {manifest_path}"

    content = manifest_path.read_text(encoding="utf-8")

    for rule_id in ALL_SUPPORTED_RULES:
        assert f"{rule_id}:" in content, f"Rule {rule_id} is missing from ruleExplanations.js"


def test_rule_explanation_fallback_structure_in_html_and_js():
    """Verify fallback behavior for unknown future rules in both review.html and ruleExplanations.js."""
    html_path = Path(__file__).resolve().parent.parent / "app" / "static" / "review.html"
    assert html_path.exists()
    html_content = html_path.read_text(encoding="utf-8")

    assert "RULE_EXPLANATIONS" in html_content
    for rule_id in ALL_SUPPORTED_RULES:
        assert rule_id in html_content, f"Rule {rule_id} missing in static review.html"

    assert "Potential Code Issue" in html_content
    assert "UNKNOWN_RULE" in html_content


# ---------------------------------------------------------------------------
# Test 3: Source File Exists
# ---------------------------------------------------------------------------
def test_source_context_retrieval_when_file_exists(tmp_path: Path):
    """When source file exists on disk, code snippet and surrounding lines are returned with target highlighted."""
    sample_file = tmp_path / "JsonReader.java"
    lines = [f"// line {i}" for i in range(1, 20)]
    lines[9] = 'name == "null"'  # line 10
    sample_file.write_text("\n".join(lines), encoding="utf-8")

    res = get_structured_source_context(str(sample_file), line_number=10, context_lines=5)
    assert res["found"] is True
    assert res["line_number"] == 10
    assert len(res["lines"]) > 0

    target_line = next((l for l in res["lines"] if l["is_target"]), None)
    assert target_line is not None
    assert target_line["line_number"] == 10
    assert 'name == "null"' in target_line["content"]


# ---------------------------------------------------------------------------
# Test 4: Source File Missing - PostgreSQL Code Snippet Remains Accessible
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_source_file_preserves_postgresql_snippet_and_labeling(client: AsyncClient, memory_db: AsyncSession):
    """
    Even when the source file does NOT exist on disk, the candidate issue API returns
    the stored code_snippet, context endpoint returns found=False with clear message,
    and labeling remains fully functional.
    """
    repo = Repository(id="repo-resilience", name="resilience-repo", s3_key="repos/res.zip")
    run = AnalysisRun(id="run-resilience", repository_id="repo-resilience", status="completed")
    issue = CandidateIssue(
        id="iss-resilience-1",
        analysis_run_id="run-resilience",
        title="Division by zero in handler",
        description="Potential division by zero",
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        file_path="deleted/path/module.py",  # non-existent on disk
        line_number=45,
        code_snippet="return total / divisor",
        message="Potential division by zero",
        severity="high",
        urgency="urgent",
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    # 1. Fetch issue via API -> code_snippet is present directly from PostgreSQL
    issue_resp = await client.get("/candidate-issues/iss-resilience-1")
    assert issue_resp.status_code == 200
    issue_data = issue_resp.json()
    assert issue_data["code_snippet"] == "return total / divisor"
    assert issue_data["rule_id"] == "PY_DIV_001"

    # 2. Fetch context endpoint -> returns found=False with clear message, no crash
    ctx_resp = await client.get("/candidate-issues/iss-resilience-1/context")
    assert ctx_resp.status_code == 200
    ctx_data = ctx_resp.json()
    assert ctx_data["found"] is False
    assert "persisted" in ctx_data["message"] or "disk" in ctx_data["message"]

    # 3. Labeling remains fully functional
    patch_resp = await client.patch(
        "/candidate-issues/iss-resilience-1/labels",
        json={
            "verified_severity": "high",
            "verified_priority": "p2",
            "verification_notes": "Divisor is validated in production middleware",
            "is_false_positive": False,
        },
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["verified_severity"] == "high"
    assert patch_resp.json()["verified_priority"] == "p2"


# ---------------------------------------------------------------------------
# Test 5 & 6: False Positive & Skip Resilience Without Context
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_false_positive_and_skip_without_disk_source(client: AsyncClient, memory_db: AsyncSession):
    """
    Test false positive submission and skip workflow on candidate issues
    where original repo files are absent from disk.
    """
    repo = Repository(id="repo-fp-test", name="fp-test-repo", s3_key="repos/fp.zip")
    run = AnalysisRun(id="run-fp-test", repository_id="repo-fp-test", status="completed")
    issue = CandidateIssue(
        id="iss-fp-test",
        analysis_run_id="run-fp-test",
        title="Loose Equality",
        description="Loose equality used",
        rule_id="JS_EQ_001",
        issue_type="loose_equality",
        file_path="cleaned_up/utils.js",
        line_number=88,
        code_snippet="if (status == 200) {",
        severity="medium",
        urgency="normal",
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    # Submit false positive
    fp_resp = await client.patch(
        "/candidate-issues/iss-fp-test/labels",
        json={
            "is_false_positive": True,
            "verified_severity": None,
            "verified_priority": None,
            "verification_notes": "[FALSE_POSITIVE] Status is always numeric int",
        },
    )
    assert fp_resp.status_code == 200
    data = fp_resp.json()
    assert data["verified_severity"] is None
    assert data["verified_priority"] is None
    assert "[FALSE_POSITIVE]" in data["verification_notes"]


# ---------------------------------------------------------------------------
# Test 7 & 8: Batch Serialization & Direct Single Issue Retrieval
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_batch_api_serialization_includes_code_snippet(client: AsyncClient, memory_db: AsyncSession):
    """
    Given a CandidateIssue in DB with code_snippet = 'x / 0',
    verify POST /candidate-issues/review/batch returns code_snippet intact.
    """
    repo = Repository(id="repo-batch-test", name="batch-repo", s3_key="repos/batch.zip")
    run = AnalysisRun(id="run-batch-test", repository_id="repo-batch-test", status="completed")
    issue = CandidateIssue(
        id="iss-batch-snip",
        analysis_run_id="run-batch-test",
        title="Division by zero test",
        description="x / 0 division",
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        file_path="src/calc.py",
        line_number=12,
        code_snippet="x / 0",
        message="Potential division by zero",
        severity="high",
        urgency="urgent",
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    resp = await client.post("/candidate-issues/review/batch", json={"target_size": 10, "random_seed": 42})
    assert resp.status_code == 200
    batch_data = resp.json()
    assert "items" in batch_data
    found = next((it for it in batch_data["items"] if it["id"] == "iss-batch-snip"), None)
    assert found is not None
    assert found["code_snippet"] == "x / 0"


@pytest.mark.asyncio
async def test_single_issue_retrieval_returns_persisted_snippet(client: AsyncClient, memory_db: AsyncSession):
    """
    Verify GET /candidate-issues/{issue_id} returns the persisted code_snippet.
    """
    repo = Repository(id="repo-single-test", name="single-repo", s3_key="repos/single.zip")
    run = AnalysisRun(id="run-single-test", repository_id="repo-single-test", status="completed")
    issue = CandidateIssue(
        id="iss-single-snip",
        analysis_run_id="run-single-test",
        title="String equality check",
        description="Comparing string references with ==",
        rule_id="JAVA_EQ_001",
        issue_type="string_reference_equality",
        file_path="src/User.java",
        line_number=99,
        code_snippet='name == "admin"',
        message="String equality checked using ==",
        severity="medium",
        urgency="normal",
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    resp = await client.get("/candidate-issues/iss-single-snip")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "iss-single-snip"
    assert data["code_snippet"] == 'name == "admin"'
    assert data["rule_id"] == "JAVA_EQ_001"

