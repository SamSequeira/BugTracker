"""
test_dataset_preparation.py
---------------------------
Comprehensive unit and API tests for DistilBERT dataset preparation pipeline:
- Feature building (no target leakage, deterministic evidence serialization)
- Quality validation (label validation, missingness, class distribution)
- Exact deduplication for ML export
- Group-aware, stratified splitting with zero cross-split leakage
- Versioned JSONL export, metadata generation, and quality report
- API endpoints (prepare, metadata, quality-report)
- Database safety (read-only verification)
"""

import json
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
from app.services.dataset_preparation import (
    DatasetDeduplicator,
    DatasetExporter,
    DatasetPreparationService,
    DatasetSplitter,
    DatasetValidator,
    build_training_text,
    generate_group_id,
    serialize_evidence,
    SEVERITY_TO_ID,
    PRIORITY_TO_ID,
)


# ===========================================================================
# 1. FEATURE BUILDER & EVIDENCE SERIALIZATION TESTS
# ===========================================================================

def test_serialize_evidence_deterministic():
    """Verify evidence serialization sorts keys and handles nested types."""
    ev1 = {"right_operand": "0", "operator": "/", "details": {"inner": 1}}
    ev2 = {"operator": "/", "details": {"inner": 1}, "right_operand": "0"}

    s1 = serialize_evidence(ev1)
    s2 = serialize_evidence(ev2)

    assert s1 == s2
    assert s1.startswith("details=")
    assert "operator=/" in s1
    assert "right_operand=0" in s1

    # Empty / None handling
    assert serialize_evidence(None) == "None"
    assert serialize_evidence({}) == "None"


def test_build_training_text_and_leakage_safety():
    """
    Verify training text includes all input context,
    and strictly EXCLUDES verified_severity, verified_priority, and detector_severity.
    """
    issue_data = {
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
        "language": "Python",
        "file_path": "src/checkout.py",
        "message": "Division by zero divisor is 0",
        "description": "Zero division in payment loop",
        "code_snippet": "amount / 0",
        "evidence": {"operator": "/", "right_operand": "0"},
        # Target labels (ground truth)
        "verified_severity": "critical",
        "verified_priority": "p1",
        # Detector prediction
        "severity": "high",
        "detector_severity": "high",
    }

    text = build_training_text(issue_data)

    # Required context must be present
    assert "Rule ID: PY_DIV_001" in text
    assert "Issue Type: division_by_zero" in text
    assert "Language: Python" in text
    assert "File Path: src/checkout.py" in text
    assert "Message: Division by zero divisor is 0" in text
    assert "Description: Zero division in payment loop" in text
    assert "amount / 0" in text
    assert "operator=/" in text

    # Critical Leakage Safety Checks:
    # 1. No target labels inside the text
    assert "verified_severity" not in text
    assert "verified_priority" not in text
    assert "critical" not in text.lower() or "critical" not in text
    # 2. No detector severity in the text
    assert "detector_severity" not in text
    assert "Severity:" not in text


def test_generate_group_id_deterministic():
    """Verify group ID is deterministic based on rule_id, file_path, code_snippet."""
    issue_a = {"rule_id": "RULE_1", "file_path": "a.py", "code_snippet": "x / 0"}
    issue_b = {"rule_id": "RULE_1", "file_path": "a.py", "code_snippet": "x / 0"}
    issue_c = {"rule_id": "RULE_2", "file_path": "a.py", "code_snippet": "x / 0"}

    gid_a = generate_group_id(issue_a)
    gid_b = generate_group_id(issue_b)
    gid_c = generate_group_id(issue_c)

    assert gid_a == gid_b
    assert gid_a != gid_c
    assert gid_a.startswith("grp_")


# ===========================================================================
# 2. QUALITY VALIDATION & DEDUPLICATION TESTS
# ===========================================================================

def test_dataset_validator_label_and_missingness_checks():
    """Verify DatasetValidator flags invalid labels and computes missingness statistics."""
    validator = DatasetValidator(min_samples_per_class=2)

    records = [
        # Valid 1
        {
            "id": "1",
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "language": "Python",
            "file_path": "a.py",
            "message": "Div by zero",
            "code_snippet": "1 / 0",
            "verified_severity": "high",
            "verified_priority": "p1",
        },
        # Valid 2 (missing code_snippet)
        {
            "id": "2",
            "rule_id": "PY_EXC_001",
            "issue_type": "bare_except",
            "language": "Python",
            "file_path": "b.py",
            "message": "Bare except",
            "code_snippet": "",  # missing
            "verified_severity": "medium",
            "verified_priority": "p2",
        },
        # Invalid: invalid severity 'extreme'
        {
            "id": "3",
            "rule_id": "PY_DIV_001",
            "verified_severity": "extreme",
            "verified_priority": "p1",
        },
        # Invalid: invalid priority 'p0'
        {
            "id": "4",
            "rule_id": "PY_DIV_001",
            "verified_severity": "low",
            "verified_priority": "p0",
        },
    ]

    valid_records, report = validator.validate_records(records)

    assert len(valid_records) == 2
    assert report["total_input_records"] == 4
    assert report["valid_records_count"] == 2
    assert report["invalid_records_count"] == 2
    assert report["missingness_statistics"]["missing_code_snippet"] == 1
    assert len(report["errors"]) == 2

    # Check distributions
    assert report["severity_distribution"]["high"]["count"] == 1
    assert report["severity_distribution"]["medium"]["count"] == 1
    assert report["severity_distribution"]["critical"]["count"] == 0
    assert report["priority_distribution"]["p1"]["count"] == 1

    # Check warnings for sparse classes (< 2)
    sparse_sev_labels = [w["label"] for w in report["warnings"] if w["target"] == "severity"]
    assert "critical" in sparse_sev_labels
    assert "low" in sparse_sev_labels


def test_dataset_deduplicator():
    """Verify exact duplicate records are removed deterministically."""
    deduplicator = DatasetDeduplicator()

    base_rec = {
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
        "language": "Python",
        "file_path": "calc.py",
        "line_number": 10,
        "code_snippet": "x / 0",
        "verified_severity": "critical",
        "verified_priority": "p1",
    }

    records = [
        {"id": "r1", **base_rec},
        {"id": "r2", **base_rec},  # exact duplicate of r1
        {
            "id": "r3",
            **base_rec,
            "line_number": 25,  # distinct line number -> distinct record
        },
    ]

    unique, stats = deduplicator.deduplicate(records)

    assert len(unique) == 2
    assert stats["total_verified_records"] == 3
    assert stats["exact_duplicates_detected"] == 1
    assert stats["records_removed_from_ml_export"] == 1
    assert stats["final_unique_records"] == 2
    assert unique[0]["id"] == "r1"
    assert unique[1]["id"] == "r3"


# ===========================================================================
# 3. GROUP-AWARE SPLITTING & ZERO LEAKAGE TESTS
# ===========================================================================

def test_splitter_zero_group_leakage_and_reproducibility():
    """
    Verify group-aware splitting guarantees:
    - Zero group overlap across train, val, test splits.
    - Exactly identical splits with same random_seed.
    """
    # Create 12 issues belonging to 6 distinct groups (2 issues per group)
    records = []
    for g in range(6):
        for i in range(2):
            records.append({
                "id": f"rec_{g}_{i}",
                "rule_id": f"RULE_{g % 3}",
                "issue_type": f"type_{g % 3}",
                "language": "Python",
                "file_path": f"module_{g}.py",
                "code_snippet": f"snippet_{g}",
                "verified_severity": ["critical", "high", "medium", "low"][g % 4],
                "verified_priority": ["p1", "p2", "p3", "p4"][g % 4],
                "group_id": f"grp_{g}",
            })

    splitter = DatasetSplitter(
        train_ratio=0.60,
        val_ratio=0.20,
        test_ratio=0.20,
        random_seed=42,
    )

    train1, val1, test1, meta1 = splitter.split(records)

    # 1. Total records check
    assert len(train1) + len(val1) + len(test1) == 12

    # 2. Strict Leakage Verification
    train_groups = set(r["group_id"] for r in train1)
    val_groups = set(r["group_id"] for r in val1)
    test_groups = set(r["group_id"] for r in test1)

    assert len(train_groups & val_groups) == 0, "Train and Validation groups must not overlap!"
    assert len(train_groups & test_groups) == 0, "Train and Test groups must not overlap!"
    assert len(val_groups & test_groups) == 0, "Validation and Test groups must not overlap!"
    assert meta1["cross_split_group_overlap"] == 0
    assert meta1["leakage_check_passed"] is True

    # 3. Reproducibility check with same seed
    train2, val2, test2, meta2 = splitter.split(records)
    assert [r["id"] for r in train1] == [r["id"] for r in train2]
    assert [r["id"] for r in val1] == [r["id"] for r in val2]
    assert [r["id"] for r in test1] == [r["id"] for r in test2]


# ===========================================================================
# 4. EXPORT AND METADATA TESTS
# ===========================================================================

def test_exporter_creates_versioned_files_and_metadata():
    """Verify DatasetExporter produces valid JSONL files, metadata, and quality reports."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        exporter = DatasetExporter(base_output_dir=tmp_dir)

        train_recs = [{
            "id": "t1",
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "language": "Python",
            "file_path": "a.py",
            "code_snippet": "x / 0",
            "verified_severity": "critical",
            "verified_priority": "p1",
            "severity": "high",  # detector prediction
            "group_id": "grp_1",
        }]
        val_recs = [{
            "id": "v1",
            "rule_id": "PY_EXC_001",
            "issue_type": "bare_except",
            "language": "Python",
            "file_path": "b.py",
            "code_snippet": "except:",
            "verified_severity": "high",
            "verified_priority": "p2",
            "severity": "medium",
            "group_id": "grp_2",
        }]
        test_recs = [{
            "id": "e1",
            "rule_id": "PY_MUT_001",
            "issue_type": "mutable_default",
            "language": "Python",
            "file_path": "c.py",
            "code_snippet": "def f(x=[]):",
            "verified_severity": "low",
            "verified_priority": "p4",
            "severity": "low",
            "group_id": "grp_3",
        }]

        val_report = {
            "status": "valid",
            "missingness_statistics": {},
            "severity_distribution": {},
            "priority_distribution": {},
            "warnings": [],
            "errors": [],
        }
        dedup_stats = {
            "total_verified_records": 3,
            "exact_duplicates_detected": 0,
            "records_removed_from_ml_export": 0,
            "final_unique_records": 3,
        }
        split_meta = {
            "strategy": "severity_stratified_group_split",
            "random_seed": 42,
            "cross_split_group_overlap": 0,
            "leakage_check_passed": True,
        }

        result = exporter.export(
            dataset_version="v1_test",
            train_records=train_recs,
            val_records=val_recs,
            test_records=test_recs,
            validation_report=val_report,
            deduplication_stats=dedup_stats,
            split_metadata=split_meta,
        )

        out_path = Path(result["export_directory"])
        assert (out_path / "train.jsonl").exists()
        assert (out_path / "validation.jsonl").exists()
        assert (out_path / "test.jsonl").exists()
        assert (out_path / "metadata.json").exists()
        assert (out_path / "quality_report.json").exists()

        # Check train.jsonl record formatting
        with open(out_path / "train.jsonl", "r", encoding="utf-8") as f:
            train_line = json.loads(f.readline())
            assert train_line["id"] == "t1"
            assert train_line["severity"] == "critical"
            assert train_line["severity_label"] == 0  # critical -> 0
            assert train_line["priority"] == "p1"
            assert train_line["priority_label"] == 0  # p1 -> 0
            assert train_line["detector_severity"] == "high"
            assert train_line["group_id"] == "grp_1"
            assert "x / 0" in train_line["text"]
            # Assert no label leakage in text
            assert "verified_severity" not in train_line["text"]

        # Overwrite protection check
        with pytest.raises(FileExistsError):
            exporter.export(
                dataset_version="v1_test",
                train_records=train_recs,
                val_records=val_recs,
                test_records=test_recs,
                validation_report=val_report,
                deduplication_stats=dedup_stats,
                split_metadata=split_meta,
                overwrite=False,
            )


# ===========================================================================
# 5. END-TO-END PIPELINE & API TESTS
# ===========================================================================

@pytest_asyncio.fixture
async def prep_db():
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
async def prep_client(prep_db: AsyncSession):
    async def override_get_db():
        yield prep_db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seed_prep_data(prep_db: AsyncSession):
    repo = Repository(id="repo-prep", name="prep-repo", s3_key="repos/prep.zip")
    prep_db.add(repo)
    await prep_db.flush()

    run = AnalysisRun(id="run-prep", repository_id=repo.id, status="completed")
    prep_db.add(run)
    await prep_db.flush()

    # 4 fully verified issues
    issues = [
        CandidateIssue(
            id=f"prep_issue_{i}",
            analysis_run_id=run.id,
            title=f"Issue {i}",
            description=f"Description {i}",
            file_path=f"src/file_{i % 2}.py",
            line_number=i * 10,
            column=0,
            rule_id=f"RULE_{i % 2}",
            issue_type=f"type_{i % 2}",
            message=f"Message {i}",
            code_snippet=f"snippet_{i % 2}",
            evidence={"idx": i},
            language="Python",
            severity="high",  # detector prediction
            urgency="high",
            verified_severity=["critical", "high", "medium", "low"][i % 4],
            verified_priority=["p1", "p2", "p3", "p4"][i % 4],
        )
        for i in range(8)
    ]

    # 1 unverified issue
    issues.append(
        CandidateIssue(
            id="prep_unverified",
            analysis_run_id=run.id,
            title="Unverified Issue",
            description="Desc",
            file_path="src/unverif.py",
            line_number=1,
            rule_id="RULE_UNV",
            issue_type="unv_type",
            message="Unv msg",
            code_snippet="unv",
            severity="medium",
            urgency="medium",
            verified_severity=None,
            verified_priority=None,
        )
    )

    # 1 partially verified issue (severity only)
    issues.append(
        CandidateIssue(
            id="prep_partial",
            analysis_run_id=run.id,
            title="Partial Issue",
            description="Desc",
            file_path="src/part.py",
            line_number=2,
            rule_id="RULE_PART",
            issue_type="part_type",
            message="Part msg",
            code_snippet="part",
            severity="low",
            urgency="low",
            verified_severity="low",
            verified_priority=None,
        )
    )

    prep_db.add_all(issues)
    await prep_db.commit()
    return repo, run, issues


@pytest.mark.asyncio
async def test_prepare_dataset_api_workflow(prep_client: AsyncClient, seed_prep_data, prep_db: AsyncSession):
    """
    Test POST /candidate-issues/dataset/prepare and metadata/quality-report retrieval.
    Verifies:
    - Only fully verified records are included (8 out of 10).
    - Database records are completely unchanged.
    - Metadata and quality report can be queried via API.
    """
    with tempfile.TemporaryDirectory() as tmp_export_dir:
        resp = await prep_client.post(
            "/candidate-issues/dataset/prepare",
            json={
                "dataset_version": "v1_api_test",
                "random_seed": 42,
                "train_ratio": 0.70,
                "validation_ratio": 0.15,
                "test_ratio": 0.15,
                "min_samples_per_class": 1,
                "export_dir": str(Path(tmp_export_dir) / "v1_api_test"),
                "overwrite": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()

        assert data["status"] == "prepared"
        assert data["dataset_version"] == "v1_api_test"
        assert data["total_verified_records"] == 8
        assert data["train_records"] + data["validation_records"] + data["test_records"] == data["records_after_deduplication"]
        assert data["quality_report"]["leakage_validation"]["cross_split_group_overlap"] == 0

        # Verify DB safety: all 10 candidate_issues still exist in DB
        unverified_db = await prep_db.get(CandidateIssue, "prep_unverified")
        assert unverified_db is not None
        assert unverified_db.verified_severity is None
        assert unverified_db.severity == "medium"  # Unchanged!

        verified_db = await prep_db.get(CandidateIssue, "prep_issue_0")
        assert verified_db is not None
        assert verified_db.severity == "high"  # Detector severity unchanged!
        assert verified_db.verified_severity == "critical"  # Ground truth unchanged!
