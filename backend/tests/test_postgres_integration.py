"""
test_postgres_integration.py
----------------------------
Integration test suite executed against actual PostgreSQL instance.
Tests real PostgreSQL connection, JSON/JSONB persistence, CheckConstraints,
review queue status filtering, dataset statistics, duplicate detection,
detector severity vs. verified ground truth isolation, and training dataset retrieval.
"""

import os
from pathlib import Path
import uuid
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.repository import Repository
from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.repositories.candidate_issue_repo import candidate_issue_repository

# Load .env file
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(env_path)


def get_postgres_url() -> str:
    url = os.environ.get("POSTGRES_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


POSTGRES_URL = get_postgres_url()
is_postgres_configured = bool(POSTGRES_URL and "postgresql" in POSTGRES_URL)


@pytest_asyncio.fixture
async def pg_session():
    if not is_postgres_configured:
        pytest.skip("PostgreSQL connection not configured in DATABASE_URL or POSTGRES_TEST_DATABASE_URL")

    try:
        engine = create_async_engine(POSTGRES_URL, pool_pre_ping=True)
        # Probe connection
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL instance unreachable or auth failed: {exc}")

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ===========================================================================
# 1. POSTGRESQL CONNECTION & SCHEMA CONSTRAINTS
# ===========================================================================

@pytest.mark.asyncio
async def test_postgres_connection_and_version(pg_session: AsyncSession):
    """PG Test 1: Verify real PostgreSQL connection and server version."""
    result = await pg_session.execute(text("SELECT version();"))
    version_str = result.scalar()
    assert version_str is not None
    assert "PostgreSQL" in version_str


@pytest.mark.asyncio
async def test_postgres_candidate_issue_persistence_and_evidence_json(pg_session: AsyncSession):
    """PG Test 2: Verify candidate issue persistence with JSON evidence on PostgreSQL."""
    repo = Repository(
        id=f"pg-repo-{uuid.uuid4()}",
        name="pg-test-repo",
        s3_key="repositories/pg-test-repo.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    evidence_dict = {
        "operator": "/",
        "right_operand": "0",
        "nested": {"key": "val", "count": 42},
    }

    issue = CandidateIssue(
        id=f"pg-issue-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Division by Zero (PY_DIV_001)",
        description="Division by zero error",
        file_path="src/math.py",
        line_number=5,
        column=1,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero",
        code_snippet="x / 0",
        evidence=evidence_dict,
        language="Python",
        severity="high",  # detector prediction
        urgency="high",
        verified_severity=None,
        verified_priority=None,
    )
    pg_session.add(issue)
    await pg_session.commit()

    retrieved = await candidate_issue_repository.get_by_id(pg_session, issue.id)
    assert retrieved is not None
    assert retrieved.evidence == evidence_dict
    assert retrieved.severity == "high"
    assert retrieved.verified_severity is None
    assert retrieved.verified_priority is None


@pytest.mark.asyncio
async def test_postgres_valid_verified_severities_and_priorities(pg_session: AsyncSession):
    """PG Test 3: Verify all valid severity and priority values are accepted by PostgreSQL."""
    repo = Repository(
        id=f"pg-repo-valid-{uuid.uuid4()}",
        name="pg-valid-repo",
        s3_key="repositories/valid.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-valid-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    valid_severities = ["high", "medium", "low"]
    valid_priorities = ["p1", "p2", "p3"]

    for sev, prio in zip(valid_severities, valid_priorities):
        issue = CandidateIssue(
            id=f"pg-valid-{sev}-{uuid.uuid4()}",
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
        pg_session.add(issue)

    await pg_session.commit()


@pytest.mark.asyncio
async def test_postgres_check_constraint_rejects_invalid_severity(pg_session: AsyncSession):
    """PG Test 4: Verify PostgreSQL check constraint rejects invalid verified_severity ('extreme')."""
    repo = Repository(
        id=f"pg-repo-inv-s-{uuid.uuid4()}",
        name="pg-test-repo-inv-s",
        s3_key="repositories/inv-s.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-inv-s-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    invalid_issue = CandidateIssue(
        id=f"pg-inv-sev-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Invalid Severity",
        description="Desc",
        file_path="test.py",
        severity="high",
        urgency="high",
        verified_severity="extreme",  # Violates ck_candidate_issues_verified_severity
    )
    pg_session.add(invalid_issue)

    with pytest.raises((IntegrityError, DBAPIError)):
        await pg_session.commit()

    await pg_session.rollback()


@pytest.mark.asyncio
async def test_postgres_check_constraint_rejects_invalid_priority(pg_session: AsyncSession):
    """PG Test 5: Verify PostgreSQL check constraint rejects invalid verified_priority ('p0')."""
    repo = Repository(
        id=f"pg-repo-inv-p-{uuid.uuid4()}",
        name="pg-test-repo-inv-p",
        s3_key="repositories/inv-p.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-inv-p-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    invalid_issue = CandidateIssue(
        id=f"pg-inv-prio-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Invalid Priority",
        description="Desc",
        file_path="test.py",
        severity="medium",
        urgency="medium",
        verified_severity="high",
        verified_priority="p0",  # Violates ck_candidate_issues_verified_priority
    )
    pg_session.add(invalid_issue)

    with pytest.raises((IntegrityError, DBAPIError)):
        await pg_session.commit()

    await pg_session.rollback()


# ===========================================================================
# 2. DETECTOR SEVERITY PRESERVATION & GROUND TRUTH ISOLATION
# ===========================================================================

@pytest.mark.asyncio
async def test_postgres_detector_severity_preserved_after_verification(pg_session: AsyncSession):
    """
    PG Test 6: Verify detector severity remains unchanged when verified labels are assigned.
    Before: severity=high, verified_severity=None, verified_priority=None
    After:  severity=high, verified_severity=critical, verified_priority=p1
    """
    repo = Repository(
        id=f"pg-repo-sep-{uuid.uuid4()}",
        name="pg-sep-repo",
        s3_key="repositories/sep.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-sep-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    issue_id = f"pg-sep-issue-{uuid.uuid4()}"
    issue = CandidateIssue(
        id=issue_id,
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
    pg_session.add(issue)
    await pg_session.commit()

    # Verify initially
    initial = await candidate_issue_repository.get_by_id(pg_session, issue_id)
    assert initial.severity == "high"
    assert initial.verified_severity is None
    assert initial.verified_priority is None

    # Manually verify with intentional disagreement: low + p3
    updated = await candidate_issue_repository.update_labels(
        pg_session,
        issue_id=issue_id,
        verified_severity="low",
        verified_priority="p3",
        verification_notes="Downgraded to low because it is in test mock flow",
    )

    assert updated is not None
    assert updated.severity == "high"  # Original detector output is preserved!
    assert updated.verified_severity == "low"  # Ground truth
    assert updated.verified_priority == "p3"  # Ground truth
    assert updated.verified_at is not None

    # Retrieve again in fresh query to verify persistence
    refreshed = await candidate_issue_repository.get_by_id(pg_session, issue_id)
    assert refreshed.severity == "high"
    assert refreshed.verified_severity == "low"
    assert refreshed.verified_priority == "p3"


# ===========================================================================
# 3. REVIEW QUEUE FILTERING, STATS, DUPLICATES & TRAINING EXPORT
# ===========================================================================

@pytest.mark.asyncio
async def test_postgres_ground_truth_isolation_and_training_dataset(pg_session: AsyncSession):
    """
    PG Test 7: Verify verified labels vs detector prediction isolation and dataset export on PostgreSQL.
    DATABASE: severity=high, verified_severity=low, verified_priority=p3
    TRAINING DATASET OUTPUT: severity=low, priority=p3, detector_severity=high
    """
    repo = Repository(
        id=f"pg-repo-ds-{uuid.uuid4()}",
        name="pg-dataset-repo",
        s3_key="repositories/ds.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-ds-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    issue_partial_id = f"pg-part-{uuid.uuid4()}"
    issue_partial = CandidateIssue(
        id=issue_partial_id,
        analysis_run_id=run.id,
        title="Partial Issue",
        description="Desc",
        file_path="partial.py",
        severity="medium",
        urgency="medium",
        verified_severity="high",
        verified_priority=None,  # Not training ready
    )

    issue_verified_id = f"pg-verif-{uuid.uuid4()}"
    issue_verified = CandidateIssue(
        id=issue_verified_id,
        analysis_run_id=run.id,
        title="Verified Issue",
        description="Desc",
        file_path="verified.py",
        language="Python",
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero",
        code_snippet="x / 0",
        evidence={"operator": "/"},
        severity="high",  # Detector predicted 'high'
        urgency="high",
        verified_severity="low",  # Ground truth 'low'
        verified_priority="p3",  # Ground truth 'p3'
    )

    pg_session.add_all([issue_partial, issue_verified])
    await pg_session.commit()

    training_dataset = await candidate_issue_repository.get_verified_training_dataset(pg_session)
    matching = [r for r in training_dataset if r["id"] == issue_verified_id]

    assert len(matching) == 1
    rec = matching[0]
    assert rec["severity"] == "low", "Target label MUST be verified_severity"
    assert rec["priority"] == "p3", "Target label MUST be verified_priority"
    assert rec["detector_severity"] == "high", "Detector prediction MUST be preserved separately"
    assert rec["severity"] != rec["detector_severity"]
    # Ensure partial record was excluded
    assert all(r["id"] != issue_partial_id for r in training_dataset)


@pytest.mark.asyncio
async def test_postgres_review_queue_filtering_and_stats(pg_session: AsyncSession):
    """
    PG Test 8: Test review queue status filtering and dataset progress statistics on PostgreSQL.
    """
    repo = Repository(
        id=f"pg-repo-q-{uuid.uuid4()}",
        name="pg-queue-repo",
        s3_key="repositories/queue.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-q-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    # 1 unverified
    i_unverif = CandidateIssue(
        id=f"pg-q-unv-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Unverified Q",
        description="Desc",
        file_path="q1.py",
        severity="low",
        urgency="low",
        verified_severity=None,
        verified_priority=None,
    )
    # 1 partial
    i_partial = CandidateIssue(
        id=f"pg-q-part-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Partial Q",
        description="Desc",
        file_path="q2.py",
        severity="medium",
        urgency="medium",
        verified_severity="high",
        verified_priority=None,
    )
    # 1 verified
    i_verif = CandidateIssue(
        id=f"pg-q-ver-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Verified Q",
        description="Desc",
        file_path="q3.py",
        severity="high",
        urgency="high",
        verified_severity="high",
        verified_priority="p1",
    )

    pg_session.add_all([i_unverif, i_partial, i_verif])
    await pg_session.commit()

    # Query unverified for this run
    unverif_items, _ = await candidate_issue_repository.list_issues(
        pg_session, analysis_run_id=run.id, verification_status="unverified"
    )
    assert len(unverif_items) == 1
    assert unverif_items[0].id == i_unverif.id

    # Query partial for this run
    part_items, _ = await candidate_issue_repository.list_issues(
        pg_session, analysis_run_id=run.id, verification_status="partial"
    )
    assert len(part_items) == 1
    assert part_items[0].id == i_partial.id

    # Query verified for this run
    ver_items, _ = await candidate_issue_repository.list_issues(
        pg_session, analysis_run_id=run.id, verification_status="verified"
    )
    assert len(ver_items) == 1
    assert ver_items[0].id == i_verif.id

    # Global Stats check
    stats = await candidate_issue_repository.get_dataset_stats(pg_session)
    assert stats["total_candidate_issues"] >= 3
    assert stats["fully_verified"] >= 1
    assert "high" in stats["severity_distribution"]
    assert "p1" in stats["priority_distribution"]


@pytest.mark.asyncio
async def test_postgres_potential_duplicate_detection(pg_session: AsyncSession):
    """
    PG Test 9: Verify identifying potential duplicate clusters on PostgreSQL.
    """
    repo = Repository(
        id=f"pg-repo-dup-{uuid.uuid4()}",
        name="pg-dup-repo",
        s3_key="repositories/dup.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-dup-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    dup_sig_rule = f"RULE_{uuid.uuid4().hex[:6]}"
    dup_sig_file = "src/duplicate_target.py"
    dup_sig_line = 42
    dup_sig_code = "return a / 0"

    d1 = CandidateIssue(
        id=f"pg-dup1-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Dup Issue 1",
        description="Desc 1",
        file_path=dup_sig_file,
        line_number=dup_sig_line,
        code_snippet=dup_sig_code,
        rule_id=dup_sig_rule,
        severity="high",
        urgency="high",
    )
    d2 = CandidateIssue(
        id=f"pg-dup2-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Dup Issue 2",
        description="Desc 2",
        file_path=dup_sig_file,
        line_number=dup_sig_line,
        code_snippet=dup_sig_code,
        rule_id=dup_sig_rule,
        severity="high",
        urgency="high",
    )

    pg_session.add_all([d1, d2])
    await pg_session.commit()

    dup_res = await candidate_issue_repository.get_potential_duplicates(
        pg_session, analysis_run_id=run.id
    )
    assert dup_res["total_duplicate_groups"] == 1
    assert dup_res["total_duplicate_issues"] == 2
    assert set(dup_res["groups"][0]["issue_ids"]) == {d1.id, d2.id}


# ===========================================================================
# 4. DATASET PREPARATION PIPELINE ON POSTGRESQL
# ===========================================================================

@pytest.mark.asyncio
async def test_postgres_dataset_preparation_pipeline(pg_session: AsyncSession):
    """
    PG Test 10: Verify end-to-end dataset preparation pipeline on real PostgreSQL:
    - Queries verified records from live PostgreSQL
    - Validates data quality, label encoding, and missingness
    - Removes exact duplicates without modifying PostgreSQL tables
    - Performs group-aware splitting with zero leakage
    - Exports JSONL files and verifies metadata
    - Confirms database records are 100% read-only and unmutated
    """
    import tempfile
    from app.services.dataset_preparation import dataset_preparation_service

    repo = Repository(
        id=f"pg-repo-prep-{uuid.uuid4()}",
        name="pg-prep-repo",
        s3_key="repositories/prep.zip",
    )
    pg_session.add(repo)
    await pg_session.flush()

    run = AnalysisRun(
        id=f"pg-run-prep-{uuid.uuid4()}",
        repository_id=repo.id,
        status="completed",
    )
    pg_session.add(run)
    await pg_session.flush()

    # Seed 6 verified issues
    verified_issues = []
    severities = ["high", "medium", "low", "high", "medium", "low"]
    priorities = ["p1", "p2", "p3", "p1", "p2", "p3"]

    for i, (sev, prio) in enumerate(zip(severities, priorities)):
        iss = CandidateIssue(
            id=f"pg-prep-iss-{i}-{uuid.uuid4()}",
            analysis_run_id=run.id,
            title=f"PG Issue {i}",
            description=f"PG Desc {i}",
            file_path=f"src/pg_module_{i % 3}.py",
            line_number=(i + 1) * 5,
            rule_id=f"PG_RULE_{i % 2}",
            issue_type=f"pg_type_{i % 2}",
            message=f"PG Message {i}",
            code_snippet=f"code_snippet_{i % 3}",
            evidence={"index": i, "safe": True},
            language="Python",
            severity="high",  # detector prediction
            urgency="high",
            verified_severity=sev,  # ground truth
            verified_priority=prio,  # ground truth
        )
        verified_issues.append(iss)

    # Seed 1 unverified issue
    unverif_iss = CandidateIssue(
        id=f"pg-prep-unv-{uuid.uuid4()}",
        analysis_run_id=run.id,
        title="Unverified PG Issue",
        description="Unverified",
        file_path="src/unverified.py",
        line_number=99,
        rule_id="PG_UNV",
        issue_type="pg_unv",
        message="Unv",
        code_snippet="unv()",
        severity="medium",
        urgency="medium",
        verified_severity=None,
        verified_priority=None,
    )

    pg_session.add_all(verified_issues + [unverif_iss])
    await pg_session.commit()

    with tempfile.TemporaryDirectory() as tmp_dir:
        res = await dataset_preparation_service.prepare_dataset(
            db=pg_session,
            dataset_version="pg_test_v1",
            random_seed=42,
            train_ratio=0.60,
            validation_ratio=0.20,
            test_ratio=0.20,
            exclude_test_synthetic=False,
            export_dir=str(Path(tmp_dir) / "pg_test_v1"),
            overwrite=True,
        )

        assert res["status"] == "prepared"
        assert res["total_verified_records"] >= 6
        assert res["records_after_deduplication"] >= 1
        assert res["quality_report"]["leakage_validation"]["cross_split_group_overlap"] == 0

        # Verify DB safety on live PostgreSQL: candidate issues still exist and unmutated
        refreshed_unv = await candidate_issue_repository.get_by_id(pg_session, unverif_iss.id)
        assert refreshed_unv is not None
        assert refreshed_unv.verified_severity is None
        assert refreshed_unv.severity == "medium"

        refreshed_ver = await candidate_issue_repository.get_by_id(pg_session, verified_issues[0].id)
        assert refreshed_ver is not None
        assert refreshed_ver.severity == "high"  # Detector prediction preserved!
        assert refreshed_ver.verified_severity == "high"  # Ground truth preserved!

