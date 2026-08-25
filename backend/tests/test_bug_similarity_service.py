"""Focused tests for the isolated Chroma-backed bug similarity service."""

from __future__ import annotations

import hashlib
import json

import pytest

from app.services.bug_similarity_service import BugSimilarityService
from app.services.static_analyzer.models import CandidateIssue


class DeterministicModel:
    """Small local embedding model: equivalent concepts share a vector."""

    def encode(self, text: str, normalize_embeddings: bool = True) -> list[float]:
        lowered = text.lower()
        if "division" in lowered or "divide" in lowered or " / " in lowered:
            return [1.0, 0.0, 0.0]
        if "resource" in lowered or "open(" in lowered or "file" in lowered:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


def make_issue(**overrides: object) -> CandidateIssue:
    values: dict[str, object] = {
        "rule_id": "PY_DIV_001",
        "issue_type": "division_by_zero",
        "message": "Divisor may be zero.",
        "file_path": "src/calculator.py",
        "line_number": 12,
        "column": 4,
        "code_snippet": "return total / divisor",
        "evidence": {"operator": "/"},
        "severity": "high",
    }
    values.update(overrides)
    return CandidateIssue(**values)  # type: ignore[arg-type]


@pytest.fixture
def service(tmp_path):
    return BugSimilarityService(
        persist_dir=tmp_path / "chroma",
        model=DeterministicModel(),
        threshold=0.85,
    )


def test_issue_id_is_deterministic_and_repository_scoped():
    issue = make_issue()
    assert BugSimilarityService.issue_id(issue, "repo-a") == BugSimilarityService.issue_id(issue, "repo-a")
    assert BugSimilarityService.issue_id(issue, "repo-a") != BugSimilarityService.issue_id(issue, "repo-b")
    assert len(BugSimilarityService.issue_id(issue, "repo-a")) == len(hashlib.sha256().hexdigest())


def test_issue_text_is_normalized_and_uses_meaningful_fields():
    text = BugSimilarityService.build_issue_text(make_issue(message="  Divisor\n may be zero.  "))
    assert "message: Divisor may be zero." in text
    assert "code: return total / divisor" in text
    assert "evidence" not in text


def test_store_issue_upserts_with_stable_id(service):
    issue = make_issue()
    issue_id = service.store_issue(issue, "repo-a")
    assert service._collection.count() == 1
    assert service.store_issue(issue, "repo-a") == issue_id
    assert service._collection.count() == 1


def test_first_issue_has_no_matches_and_is_stored(service):
    result = service.add_and_find(make_issue(), "repo-a")
    assert result == {"duplicate": False, "similarity": 0.0, "similar_bugs": []}
    json.dumps(result)
    assert service._collection.count() == 1


def test_clearly_similar_issue_is_duplicate(service):
    service.store_issue(make_issue(), "repo-a")
    result = service.find_similar_issues(
        make_issue(file_path="src/other.py", line_number=20, message="Division by zero is possible."),
        "repo-b",
    )
    assert result["duplicate"] is True
    assert result["similarity"] == pytest.approx(1.0)
    assert result["similar_bugs"][0]["issue_type"] == "division_by_zero"


def test_clearly_different_issue_is_not_duplicate(service):
    service.store_issue(make_issue(), "repo-a")
    result = service.find_similar_issues(
        make_issue(
            rule_id="PY_RES_001",
            issue_type="unclosed_resource",
            message="Opened resource is never closed.",
            code_snippet="handle = open(path)",
        ),
        "repo-b",
    )
    assert result["duplicate"] is False
    assert result["similarity"] == pytest.approx(0.0)


def test_duplicate_threshold_is_configurable(tmp_path):
    service = BugSimilarityService(
        persist_dir=tmp_path / "chroma",
        model=DeterministicModel(),
        threshold=1.0,
    )
    service.store_issue(make_issue(), "repo-a")
    result = service.find_similar_issues(make_issue(file_path="other.py"), "repo-b")
    assert result["similarity"] == pytest.approx(1.0)
    assert result["duplicate"] is True


def test_add_and_find_prevents_self_match(service):
    issue = make_issue()
    service.store_issue(issue, "repo-a")
    result = service.add_and_find(issue, "repo-a")
    assert result == {"duplicate": False, "similarity": 0.0, "similar_bugs": []}
    assert service._collection.count() == 1


def test_similarity_failure_returns_json_safe_unavailable_result(service):
    class FailingModel:
        def encode(self, *_args, **_kwargs):
            raise RuntimeError("model unavailable")

    issue = make_issue()
    original_issue = issue.to_dict()
    service._model = FailingModel()

    result = service.add_and_find(issue, "repo-a")

    assert issue.to_dict() == original_issue
    assert result == BugSimilarityService.unavailable_result()
    json.dumps(result)
