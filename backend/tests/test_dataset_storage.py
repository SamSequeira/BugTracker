"""
test_dataset_storage.py
-----------------------
Unit & Component test suite for Candidate Issue storage, verified labels,
database CheckConstraints, and training dataset retrieval.
"""

from datetime import datetime, timezone
import uuid
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from data.dbconnection.base import Base
from app.models.repository import Repository
from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.issue_status import IssueStatus
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.services.candidate_issue_mapper import candidate_issue_mapper
from app.services.static_analyzer.models import CandidateIssue as CandidateIssueDataclass


# Setup an isolated in-memory test database for unit testing
@pytest_asyncio.fixture
async def test_db():
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
async def sample_analysis_run(test_db: AsyncSession) -> tuple[Repository, AnalysisRun]:
    """Helper fixture to create a valid repository and analysis run hierarchy."""
    repo = Repository(
        id=str(uuid.uuid4()),
        name="test-repo",
        s3_key="repositories/test-repo.zip",
    )
    test_db.add(repo)
    await test_db.flush()

    run = AnalysisRun(
        id=str(uuid.uuid4()),
        repository_id=repo.id,
        status="completed",
    )
    test_db.add(run)
    await test_db.flush()
    await test_db.commit()

    return repo, run


# ===========================================================================
# 1. DATABASE CONNECTIVITY & SCHEMA INTEGRITY TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_database_connection(test_db: AsyncSession):
    """Test 1: Verify basic database connectivity and scalar execution."""
    result = await test_db.execute(text("SELECT 1"))
    assert result.scalar() == 1


@pytest.mark.asyncio
async def test_schema_compatibility_and_tables(test_db: AsyncSession):
    """Test 2: Verify all required models and tables exist and are recognized."""
    tables = Base.metadata.tables.keys()
    assert "repositories" in tables
    assert "analysis_runs" in tables
    assert "candidate_issues" in tables
    assert "issue_statuses" in tables
    assert "users" in tables


# ===========================================================================
# 2. CANDIDATE ISSUE INSERTION & RETRIEVAL TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_candidate_issue_insertion_and_retrieval(test_db: AsyncSession, sample_analysis_run):
    """Test 3 & 4: Insert and retrieve candidate issue preserving all fields."""
    _, run = sample_analysis_run

    issue = CandidateIssue(
        id=str(uuid.uuid4()),
        analysis_run_id=run.id,
        title="Division By Zero (PY_DIV_001)",
        description="Division by zero: the divisor `0` is always zero.",
        file_path="src/math_utils.py",
        line_number=2,
        column=0,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero: the divisor `0` is always zero.",
        code_snippet="x / 0",
        evidence={
            "operator": "/",
            "right_operand": "0",
            "right_node_type": "integer",
            "classification": "definitely_zero",
        },
        language="Python",
        severity="high",
        urgency="high",
        verified_severity=None,
        verified_priority=None,
    )

    created = await candidate_issue_repository.create(test_db, issue)
    await test_db.commit()

    retrieved = await candidate_issue_repository.get_by_id(test_db, created.id)
    assert retrieved is not None
    assert retrieved.id == issue.id
    assert retrieved.rule_id == "PY_DIV_001"
    assert retrieved.issue_type == "division_by_zero"
    assert retrieved.language == "Python"
    assert retrieved.line_number == 2
    assert retrieved.column == 0
    assert retrieved.code_snippet == "x / 0"
    assert retrieved.severity == "high"  # Detector prediction
    assert retrieved.verified_severity is None
    assert retrieved.verified_priority is None


@pytest.mark.asyncio
async def test_evidence_preservation(test_db: AsyncSession, sample_analysis_run):
    """Test 5: Verify complex structured JSON evidence is preserved without mutation."""
    _, run = sample_analysis_run

    evidence_payload = {
        "operator": "/",
        "right_operand": "0",
        "right_node_type": "integer",
        "nested_details": {
            "ast_node_type": "binary_op",
            "is_constant": True,
        },
        "score": 0.99,
    }

    issue = CandidateIssue(
        id=str(uuid.uuid4()),
        analysis_run_id=run.id,
        title="Division by zero",
        description="Division by zero desc",
        file_path="test.py",
        line_number=10,
        evidence=evidence_payload,
        severity="high",
        urgency="high",
    )

    await candidate_issue_repository.create(test_db, issue)
    await test_db.commit()

    retrieved = await candidate_issue_repository.get_by_id(test_db, issue.id)
    assert retrieved is not None
    assert retrieved.evidence == evidence_payload
    assert retrieved.evidence["nested_details"]["ast_node_type"] == "binary_op"


# ===========================================================================
# 3. DETECTOR SEVERITY VS GROUND-TRUTH INDEPENDENCE TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_detector_severity_preserved_after_verification(test_db: AsyncSession, sample_analysis_run):
    """
    Test 6: Verify detector severity remains unchanged when verified labels disagree.
    Before: severity=high, verified_severity=None, verified_priority=None
    After:  severity=high, verified_severity=critical, verified_priority=p1
    """
    _, run = sample_analysis_run

    issue = CandidateIssue(
        id=str(uuid.uuid4()),
        analysis_run_id=run.id,
        title="Division by zero",
        description="Division by zero desc",
        file_path="math.py",
        line_number=5,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero",
        code_snippet="1 / 0",
        language="Python",
        severity="high",  # Detector predicted 'high'
        urgency="high",
        verified_severity=None,
        verified_priority=None,
    )
    await candidate_issue_repository.create(test_db, issue)
    await test_db.commit()

    # Manually verify with intentional disagreement: critical + p1
    updated = await candidate_issue_repository.update_labels(
        test_db,
        issue_id=issue.id,
        verified_severity="critical",
        verified_priority="p1",
        verification_notes="Upgraded to critical because it is in the core payment path",
    )

    assert updated is not None
    assert updated.severity == "high"  # Original detector output is preserved!
    assert updated.verified_severity == "critical"  # Ground truth
    assert updated.verified_priority == "p1"  # Ground truth
    assert updated.verified_at is not None
    assert "payment path" in updated.verification_notes


# ===========================================================================
# 4. LABEL VALIDATION & CONSTRAINT REJECTION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_valid_verified_labels(test_db: AsyncSession, sample_analysis_run):
    """Test 7 & 9: Verify all valid severity and priority values are accepted."""
    _, run = sample_analysis_run

    valid_severities = ["critical", "high", "medium", "low"]
    valid_priorities = ["p1", "p2", "p3", "p4"]

    for sev, prio in zip(valid_severities, valid_priorities):
        issue = CandidateIssue(
            id=str(uuid.uuid4()),
            analysis_run_id=run.id,
            title=f"Issue {sev}",
            description=f"Desc {sev}",
            file_path="test.py",
            line_number=1,
            severity="medium",
            urgency="medium",
            verified_severity=sev,
            verified_priority=prio,
        )
        await candidate_issue_repository.create(test_db, issue)

    await test_db.commit()


@pytest.mark.asyncio
async def test_invalid_verified_severity_rejected(test_db: AsyncSession, sample_analysis_run):
    """Test 8: Verify invalid verified_severity values are rejected by DB constraint."""
    _, run = sample_analysis_run

    issue = CandidateIssue(
        id=str(uuid.uuid4()),
        analysis_run_id=run.id,
        title="Invalid Severity Issue",
        description="Desc",
        file_path="test.py",
        severity="medium",
        urgency="medium",
        verified_severity="extreme",  # INVALID
        verified_priority="p1",
    )
    test_db.add(issue)

    with pytest.raises((IntegrityError, DBAPIError)):
        await test_db.commit()

    await test_db.rollback()


@pytest.mark.asyncio
async def test_invalid_verified_priority_rejected(test_db: AsyncSession, sample_analysis_run):
    """Test 10: Verify invalid verified_priority values are rejected by DB constraint."""
    _, run = sample_analysis_run

    issue = CandidateIssue(
        id=str(uuid.uuid4()),
        analysis_run_id=run.id,
        title="Invalid Priority Issue",
        description="Desc",
        file_path="test.py",
        severity="medium",
        urgency="medium",
        verified_severity="high",
        verified_priority="p0",  # INVALID
    )
    test_db.add(issue)

    with pytest.raises((IntegrityError, DBAPIError)):
        await test_db.commit()

    await test_db.rollback()


# ===========================================================================
# 5. PARTIAL LABELS & TRAINING DATASET RETRIEVAL TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_partial_label_handling_and_training_dataset_filter(test_db: AsyncSession, sample_analysis_run):
    """
    Test 11, 12, 13, 14, 15: Verify states:
      1. No labels (verified_severity=None, verified_priority=None)
      2. Severity only (verified_severity=high, verified_priority=None)
      3. Priority only (verified_severity=None, verified_priority=p2)
      4. Fully verified (verified_severity=critical, verified_priority=p1)
    Confirm get_verified_training_dataset() returns ONLY state 4.
    """
    _, run = sample_analysis_run

    # State 1: No labels
    i1 = CandidateIssue(
        id="issue-no-labels",
        analysis_run_id=run.id,
        title="Issue 1",
        description="Desc 1",
        file_path="f1.py",
        severity="medium",
        urgency="medium",
        verified_severity=None,
        verified_priority=None,
    )

    # State 2: Severity only
    i2 = CandidateIssue(
        id="issue-sev-only",
        analysis_run_id=run.id,
        title="Issue 2",
        description="Desc 2",
        file_path="f2.py",
        severity="low",
        urgency="low",
        verified_severity="high",
        verified_priority=None,
    )

    # State 3: Priority only
    i3 = CandidateIssue(
        id="issue-prio-only",
        analysis_run_id=run.id,
        title="Issue 3",
        description="Desc 3",
        file_path="f3.py",
        severity="high",
        urgency="high",
        verified_severity=None,
        verified_priority="p2",
    )

    # State 4: Fully verified
    i4 = CandidateIssue(
        id="issue-fully-verified",
        analysis_run_id=run.id,
        title="Issue 4",
        description="Desc 4",
        file_path="f4.py",
        language="Python",
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero",
        code_snippet="x / 0",
        evidence={"operator": "/"},
        severity="high",  # detector prediction
        urgency="high",
        verified_severity="critical",  # ground truth
        verified_priority="p1",  # ground truth
    )

    await candidate_issue_repository.create_bulk(test_db, [i1, i2, i3, i4])
    await test_db.commit()

    # Retrieve verified dataset
    training_records = await candidate_issue_repository.get_verified_training_dataset(test_db)

    # Exactly 1 record should be returned
    assert len(training_records) == 1
    record = training_records[0]

    assert record["id"] == "issue-fully-verified"
    # Ground-truth targets
    assert record["severity"] == "critical"
    assert record["priority"] == "p1"
    # Original detector prediction preserved under detector_severity
    assert record["detector_severity"] == "high"


@pytest.mark.asyncio
async def test_explicit_ground_truth_target_mapping(test_db: AsyncSession, sample_analysis_run):
    """
    Test 16: Explicit ground-truth mapping test.
    DATABASE:
      severity = high
      verified_severity = low
      verified_priority = p4
    TRAINING DATASET OUTPUT:
      severity = low   (NOT high!)
      priority = p4
      detector_severity = high
    """
    _, run = sample_analysis_run

    issue = CandidateIssue(
        id="disagree-test-id",
        analysis_run_id=run.id,
        title="Disagree Issue",
        description="Desc",
        file_path="test.py",
        language="Python",
        rule_id="PY_RES_001",
        issue_type="resource_leak",
        message="Unclosed file descriptor",
        code_snippet="open('file.txt')",
        evidence={"function": "open"},
        severity="high",  # Static analyzer thought it was high
        urgency="high",
        verified_severity="low",  # Human expert verified it as low
        verified_priority="p4",  # Human expert assigned p4
    )
    await candidate_issue_repository.create(test_db, issue)
    await test_db.commit()

    records = await candidate_issue_repository.get_verified_training_dataset(test_db)
    target = next((r for r in records if r["id"] == "disagree-test-id"), None)

    assert target is not None
    assert target["severity"] == "low", "Training dataset target MUST use verified_severity"
    assert target["priority"] == "p4", "Training dataset target MUST use verified_priority"
    assert target["detector_severity"] == "high", "Detector severity must remain preserved separately"
    assert target["severity"] != target["detector_severity"]


# ===========================================================================
# 6. MULTIPLE ISSUES & MAPPER INTEGRATION TESTS
# ===========================================================================

@pytest.mark.asyncio
async def test_multiple_candidate_issues_from_single_analysis(test_db: AsyncSession, sample_analysis_run):
    """Test 17 & 18: Multiple candidate issues mapped and stored from a single analysis run."""
    _, run = sample_analysis_run

    raw_findings = [
        CandidateIssueDataclass(
            rule_id="PY_DIV_001",
            issue_type="division_by_zero",
            message="Division by zero detected",
            file_path="src/calc.py",
            line_number=10,
            column=4,
            code_snippet="a / 0",
            evidence={"divisor": "0"},
            severity="high",
        ),
        CandidateIssueDataclass(
            rule_id="PY_MUT_001",
            issue_type="mutable_default_argument",
            message="Mutable default argument in function def",
            file_path="src/calc.py",
            line_number=25,
            column=0,
            code_snippet="def foo(items=[]):",
            evidence={"arg": "items"},
            severity="medium",
        ),
    ]

    issues, statuses = candidate_issue_mapper.to_orm_bulk(raw_findings, run.id)

    assert len(issues) == 2
    assert len(statuses) == 2

    # Verify initial ORM mapping does NOT set verified labels
    for issue in issues:
        assert issue.verified_severity is None
        assert issue.verified_priority is None
        assert issue.analysis_run_id == run.id

    await candidate_issue_repository.create_bulk(test_db, issues)
    await test_db.commit()

    stored_issues = await candidate_issue_repository.list_by_analysis_run_id(test_db, run.id)
    assert len(stored_issues) == 2

    # Verify fields were preserved
    issue1 = next(i for i in stored_issues if i.rule_id == "PY_DIV_001")
    assert issue1.code_snippet == "a / 0"
    assert issue1.evidence == {"divisor": "0"}
    assert issue1.severity == "high"

    issue2 = next(i for i in stored_issues if i.rule_id == "PY_MUT_001")
    assert issue2.code_snippet == "def foo(items=[]):"
    assert issue2.severity == "medium"
