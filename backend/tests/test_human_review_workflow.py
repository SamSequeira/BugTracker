"""
test_human_review_workflow.py
==================================================================================
Comprehensive automated tests for Human Ground-Truth Review Execution, Context
Retrieval, Bias/Leakage Prevention, Resumable Sessions, and Readiness Gates.
==================================================================================
"""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.repository import Repository
from app.repositories.candidate_issue_repo import candidate_issue_repository
from app.schemas.candidate_issues import CandidateIssueLabelUpdate
from app.services.dataset_preparation import (
    DatasetDeduplicator,
    DatasetSplitter,
    DatasetValidator,
    ReviewSampler,
    build_training_text,
    evaluate_dataset_readiness,
    generate_group_id,
)
from data.dbconnection.base import Base
from scripts.collect_dataset import (
    get_batch_progress,
    get_source_context,
)


@pytest.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


# ---------------------------------------------------------------------------
# 1. Confirmed Valid Issue Workflow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirmed_valid_issue_workflow(memory_db: AsyncSession):
    repo = Repository(id="repo-1", name="test-repo", s3_key="repositories/test.zip")
    run = AnalysisRun(id="run-1", repository_id="repo-1", status="completed")
    issue = CandidateIssue(
        id="iss-1",
        analysis_run_id="run-1",
        title="Division by zero in main",
        description="Potential division by zero",
        file_path="main.py",
        line_number=10,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        severity="high",
        urgency="urgent",
        code_snippet="x / 0",
        message="Division by zero",
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    updated = await candidate_issue_repository.update_labels(
        db=memory_db,
        issue_id="iss-1",
        verified_severity="critical",
        verified_priority="p1",
        verification_notes="Confirmed critical zero divisor in core handler",
        is_false_positive=False,
    )

    assert updated is not None
    assert updated.verified_severity == "critical"
    assert updated.verified_priority == "p1"
    assert updated.verified_at is not None
    assert updated.verification_notes == "Confirmed critical zero divisor in core handler"
    # Original detector predictions remain untouched
    assert updated.severity == "high"
    assert updated.urgency == "urgent"


# ---------------------------------------------------------------------------
# 2. False Positive Workflow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_false_positive_workflow(memory_db: AsyncSession):
    repo = Repository(id="repo-fp", name="fp-repo", s3_key="repositories/fp.zip")
    run = AnalysisRun(id="run-fp", repository_id="repo-fp", status="completed")
    issue = CandidateIssue(
        id="iss-fp",
        analysis_run_id="run-fp",
        title="Div by zero in calc",
        description="Potential division by zero",
        file_path="calc.py",
        line_number=42,
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        severity="medium",
        urgency="normal",
        code_snippet="total / count",
        message="Potential division by zero",
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    updated = await candidate_issue_repository.update_labels(
        db=memory_db,
        issue_id="iss-fp",
        is_false_positive=True,
        verification_notes="Divisor count is guaranteed > 0 by prior if guard on line 40",
    )

    assert updated is not None
    assert updated.verified_severity is None
    assert updated.verified_priority is None
    assert updated.verified_at is not None
    assert updated.verification_notes.startswith("[FALSE_POSITIVE]")
    assert "guaranteed > 0" in updated.verification_notes


# ---------------------------------------------------------------------------
# 3. Skipped Issue Workflow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_skipped_issue_workflow(memory_db: AsyncSession):
    repo = Repository(id="repo-skip", name="skip-repo", s3_key="repositories/skip.zip")
    run = AnalysisRun(id="run-skip", repository_id="repo-skip", status="completed")
    issue = CandidateIssue(
        id="iss-skip",
        analysis_run_id="run-skip",
        title="Unclosed resource in util",
        description="File handle not closed",
        file_path="util.py",
        line_number=15,
        rule_id="PY_RES_001",
        severity="medium",
        urgency="normal",
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    # When skipped, no update is made; labels remain NULL and verified_at is NULL
    loaded = await candidate_issue_repository.get_by_id(memory_db, "iss-skip")
    assert loaded.verified_severity is None
    assert loaded.verified_priority is None
    assert loaded.verified_at is None


# ---------------------------------------------------------------------------
# 4. Partial-Label Recovery
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_label_recovery(memory_db: AsyncSession):
    repo = Repository(id="repo-part", name="part-repo", s3_key="repositories/part.zip")
    run = AnalysisRun(id="run-part", repository_id="repo-part", status="completed")
    issue = CandidateIssue(
        id="iss-part",
        analysis_run_id="run-part",
        title="Assert in production",
        description="Assert statement in auth",
        file_path="auth.py",
        line_number=50,
        rule_id="PY_ASS_001",
        severity="medium",
        urgency="normal",
        verified_severity="high",
        verified_priority=None,  # partially labeled
        verified_at=datetime.now(timezone.utc),
    )
    memory_db.add_all([repo, run, issue])
    await memory_db.commit()

    stats = await candidate_issue_repository.get_dataset_stats(memory_db)
    assert stats["partially_verified"] == 1
    assert stats["fully_verified"] == 0

    # Recover / complete the partial label
    await candidate_issue_repository.update_labels(
        db=memory_db,
        issue_id="iss-part",
        verified_priority="p2",
        verification_notes="Completed priority assignment",
    )

    stats_after = await candidate_issue_repository.get_dataset_stats(memory_db)
    assert stats_after["partially_verified"] == 0
    assert stats_after["fully_verified"] == 1


# ---------------------------------------------------------------------------
# 5 & 6. Invalid Severity and Priority Rejection
# ---------------------------------------------------------------------------
def test_invalid_severity_rejection():
    with pytest.raises(ValidationError):
        CandidateIssueLabelUpdate(verified_severity="urgent")  # type: ignore


def test_invalid_priority_rejection():
    with pytest.raises(ValidationError):
        CandidateIssueLabelUpdate(verified_priority="high")  # type: ignore


# ---------------------------------------------------------------------------
# 7. False Positive Cannot Contain Verified Labels
# ---------------------------------------------------------------------------
def test_false_positive_cannot_contain_verified_labels():
    with pytest.raises(ValidationError):
        CandidateIssueLabelUpdate(
            is_false_positive=True,
            verified_severity="critical",
        )

    with pytest.raises(ValidationError):
        CandidateIssueLabelUpdate(
            is_false_positive=True,
            verified_priority="p1",
        )


# ---------------------------------------------------------------------------
# 8. Confirmed Issue Requires Both Labels for ML Export
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirmed_issue_requires_both_labels_for_export(memory_db: AsyncSession):
    repo = Repository(id="repo-exp", name="exp-repo", s3_key="repositories/exp.zip")
    run = AnalysisRun(id="run-exp", repository_id="repo-exp", status="completed")
    full_issue = CandidateIssue(
        id="iss-full",
        analysis_run_id="run-exp",
        title="Div zero 1",
        description="Div zero 1",
        severity="medium",
        urgency="normal",
        file_path="calc.py",
        line_number=10,
        rule_id="PY_DIV_001",
        code_snippet="a / b",
        verified_severity="high",
        verified_priority="p2",
        verified_at=datetime.now(timezone.utc),
    )
    partial_issue = CandidateIssue(
        id="iss-partial",
        analysis_run_id="run-exp",
        title="Div zero 2",
        description="Div zero 2",
        severity="medium",
        urgency="normal",
        file_path="calc.py",
        line_number=20,
        rule_id="PY_DIV_001",
        code_snippet="c / d",
        verified_severity="high",
        verified_priority=None,
        verified_at=datetime.now(timezone.utc),
    )
    memory_db.add_all([repo, run, full_issue, partial_issue])
    await memory_db.commit()

    export_records = await candidate_issue_repository.get_verified_training_dataset(memory_db)
    export_ids = [r["id"] for r in export_records]
    assert "iss-full" in export_ids
    assert "iss-partial" not in export_ids


# ---------------------------------------------------------------------------
# 9. Batch Progress Tracking and Resumption
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_batch_progress_tracking_and_resume(memory_db: AsyncSession):
    repo = Repository(id="repo-prog", name="prog-repo", s3_key="repositories/prog.zip")
    run = AnalysisRun(id="run-prog", repository_id="repo-prog", status="completed")
    i1 = CandidateIssue(id="b1", analysis_run_id="run-prog", title="t1", description="d1", severity="medium", urgency="normal", file_path="a.py", line_number=1, verified_severity="critical", verified_priority="p1", verified_at=datetime.now(timezone.utc))
    i2 = CandidateIssue(id="b2", analysis_run_id="run-prog", title="t2", description="d2", severity="medium", urgency="normal", file_path="b.py", line_number=2, verified_at=datetime.now(timezone.utc), verification_notes="[FALSE_POSITIVE] Guarded")
    i3 = CandidateIssue(id="b3", analysis_run_id="run-prog", title="t3", description="d3", severity="medium", urgency="normal", file_path="c.py", line_number=3, verified_severity="medium", verified_at=datetime.now(timezone.utc))  # partial
    i4 = CandidateIssue(id="b4", analysis_run_id="run-prog", title="t4", description="d4", severity="medium", urgency="normal", file_path="d.py", line_number=4)  # unreviewed
    memory_db.add_all([repo, run, i1, i2, i3, i4])
    await memory_db.commit()

    progress = await get_batch_progress(memory_db, ["b1", "b2", "b3", "b4"])
    assert progress["total"] == 4
    assert progress["confirmed_valid"] == 1
    assert progress["false_positives"] == 1
    assert progress["partially_labeled"] == 1
    assert progress["unreviewed"] == 1
    assert progress["remaining"] == 2


# ---------------------------------------------------------------------------
# 10. Deterministic Review Batch Reproducibility
# ---------------------------------------------------------------------------
def test_deterministic_review_batch_reproducibility():
    records = [
        {
            "id": f"real-candidate-{i}",
            "language": "Python" if i % 3 == 0 else ("Java" if i % 3 == 1 else "JavaScript"),
            "repository_name": f"repo-{i % 4}",
            "rule_id": f"RULE_{i % 5}",
            "issue_type": f"type_{i % 3}",
            "code_snippet": f"code_snippet_{i}",
            "file_path": f"src_code/handler_{i}.py",
            "line_number": i + 1,
        }
        for i in range(100)
    ]

    sampler1 = ReviewSampler(random_seed=42)
    batch1, rep1 = sampler1.sample(records, target_size=30)

    sampler2 = ReviewSampler(random_seed=42)
    batch2, rep2 = sampler2.sample(records, target_size=30)

    ids1 = [item["id"] for item in batch1]
    ids2 = [item["id"] for item in batch2]
    assert ids1 == ids2
    assert rep1["sampled_count"] == rep2["sampled_count"] == 30


# ---------------------------------------------------------------------------
# 11 & 12. Source Context Retrieval & Missing Source Handling
# ---------------------------------------------------------------------------
def test_source_context_retrieval(tmp_path: Path):
    test_file = tmp_path / "service.py"
    lines = [f"line {i}" for i in range(1, 40)]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    ok, ctx = get_source_context(str(test_file), line_number=20, context_lines=5)
    assert ok is True
    assert ">    20 | line 20" in ctx
    assert "line 15" in ctx
    assert "line 25" in ctx


def test_missing_repository_source_handling():
    ok, ctx = get_source_context("/non/existent/path/never_created.py", line_number=10)
    assert ok is False
    assert "[Notice]" in ctx


# ---------------------------------------------------------------------------
# 13. Ground-Truth Labels Excluded from DistilBERT Feature Text
# ---------------------------------------------------------------------------
def test_ground_truth_labels_excluded_from_feature_text():
    record = {
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
        "language": "Python",
        "file_path": "calculator.py",
        "message": "Potential division by zero",
        "description": "Divisor can be 0",
        "code_snippet": "return total / divisor",
        "evidence": {"divisor": "divisor"},
        # Target labels and notes that MUST NOT leak
        "verified_severity": "critical",
        "verified_priority": "p1",
        "severity": "high",
        "urgency": "urgent",
        "is_false_positive": False,
        "verification_notes": "Very critical bug",
    }

    feature_text = build_training_text(record)

    assert "Rule ID: PY_DIV_001" in feature_text
    assert "return total / divisor" in feature_text
    # Leakage assertions
    assert "verified_severity" not in feature_text
    assert "verified_priority" not in feature_text
    assert "critical" not in feature_text
    assert "p1" not in feature_text
    assert "urgent" not in feature_text
    assert "Very critical bug" not in feature_text


# ---------------------------------------------------------------------------
# 14. Deduplication Signature Intrinsic Quality
# ---------------------------------------------------------------------------
def test_deduplicator_signature_uses_intrinsic_properties():
    deduplicator = DatasetDeduplicator()
    rec1 = {
        "id": "1",
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
        "language": "Python",
        "file_path": "a.py",
        "line_number": 10,
        "code_snippet": "x / 0",
        "verified_severity": "critical",
        "verified_priority": "p1",
    }
    rec2 = {
        "id": "2",
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
        "language": "Python",
        "file_path": "a.py",
        "line_number": 10,
        "code_snippet": "x / 0",
        "verified_severity": "critical",
        "verified_priority": "p1",
    }

    unique, stats = deduplicator.deduplicate([rec1, rec2])
    assert len(unique) == 1
    assert stats["exact_duplicates_detected"] == 1


# ---------------------------------------------------------------------------
# 15. Group Isolation and Zero Leakage Guarantee
# ---------------------------------------------------------------------------
def test_group_isolation_and_zero_leakage():
    splitter = DatasetSplitter(train_ratio=0.7, val_ratio=0.2, test_ratio=0.1, random_seed=42)
    records = []
    # 3 groups of 10 records each
    for g in range(3):
        for i in range(10):
            records.append({
                "id": f"g{g}_i{i}",
                "rule_id": f"RULE_{g}",
                "file_path": f"module_{g}.py",
                "code_snippet": f"snippet_{g}",
                "verified_severity": "high",
                "verified_priority": "p2",
                "language": "Python",
            })

    train, val, test, meta = splitter.split(records)

    assert meta["cross_split_group_overlap"] == 0
    assert meta["leakage_check_passed"] is True
    assert meta["total_groups"] == 3
    assert meta["train_groups"] + meta["validation_groups"] + meta["test_groups"] == 3

    # Ensure actual assigned records belong to non-overlapping groups
    train_gids = {generate_group_id(r) for r in train}
    val_gids = {generate_group_id(r) for r in val}
    test_gids = {generate_group_id(r) for r in test}

    assert train_gids.isdisjoint(val_gids)
    assert train_gids.isdisjoint(test_gids)
    assert val_gids.isdisjoint(test_gids)


# ---------------------------------------------------------------------------
# 16. Readiness Scorecard Evaluation & Deficits
# ---------------------------------------------------------------------------
def test_readiness_scorecard_evaluates_deficits():
    # Empty dataset -> NOT READY FOR TRAINING
    scorecard = evaluate_dataset_readiness(records=[])

    assert scorecard["dataset_status"] == "NOT READY FOR TRAINING"
    assert scorecard["status"] == "NOT READY"
    assert len(scorecard["recommendations"]) > 0
    assert "severity_deficits" in scorecard["deficits"]
    assert "priority_deficits" in scorecard["deficits"]

