"""Stage 2 integration tests for static analysis and bug similarity."""

from __future__ import annotations

import asyncio
import json

from app.services.ast_generator import ast_generator
from app.services.repository_analysis_service import RepositoryAnalysisService


class RecordingSimilarityService:
    def __init__(self) -> None:
        self.calls = []

    def add_and_find(self, issue, repository_id: str) -> dict:
        self.calls.append((issue, repository_id))
        return {
            "duplicate": False,
            "similarity": 0.42,
            "similar_bugs": [],
        }


class FailingSimilarityService:
    def add_and_find(self, issue, repository_id: str) -> dict:
        raise RuntimeError("Chroma is unavailable")


def _repository_ast(tmp_path):
    source = tmp_path / "example.py"
    source.write_text(
        "def divide(total, divisor):\n    return total / 0\n",
        encoding="utf-8",
    )
    file_result = ast_generator.generate_ast(str(source), "Python")
    return {
        "repository_path": str(tmp_path),
        "total_files": 1,
        "supported_files": 1,
        "languages_detected": ["Python"],
        "files_analyzed": [file_result],
    }


def _run_repository_analysis(service, repo_path, repository_id):
    return asyncio.run(service.analyze_repository(str(repo_path), repository_id))


def test_repository_analysis_uses_ast_internally_without_returning_it(
    tmp_path, monkeypatch
):
    ast_result = _repository_ast(tmp_path)
    similarity = RecordingSimilarityService()
    service = RepositoryAnalysisService(similarity_service=similarity)
    monkeypatch.setattr(
        "app.services.repository_analysis_service.ast_generator.generate_ast_for_repository",
        lambda _path: ast_result,
    )

    response = _run_repository_analysis(service, tmp_path, "repository-123")

    assert response["repository_path"] == ast_result["repository_path"]
    assert response["summary"] == {
        "total_files": 1,
        "supported_files": 1,
        "languages": ["Python"],
    }
    assert "ast" in ast_result["files_analyzed"][0]
    assert response["files"] == [
        {
            key: value
            for key, value in ast_result["files_analyzed"][0].items()
            if key != "ast"
        }
    ]
    assert all("ast" not in file_result for file_result in response["files"])
    assert "static_analysis" in response

    issues = response["static_analysis"]["results"][0]["issues"]
    assert issues
    assert len(similarity.calls) == len(issues)
    assert {repository_id for _, repository_id in similarity.calls} == {"repository-123"}
    assert all(issue["similarity"]["similarity"] == 0.42 for issue in issues)
    json.dumps(response)


def test_similarity_failure_preserves_static_analysis_findings(tmp_path, monkeypatch):
    ast_result = _repository_ast(tmp_path)
    service = RepositoryAnalysisService(similarity_service=FailingSimilarityService())
    monkeypatch.setattr(
        "app.services.repository_analysis_service.ast_generator.generate_ast_for_repository",
        lambda _path: ast_result,
    )

    response = _run_repository_analysis(service, tmp_path, "repository-123")

    issues = response["static_analysis"]["results"][0]["issues"]
    assert issues
    assert all(issue["rule_id"] == "PY_DIV_001" for issue in issues)
    assert all(
        issue["similarity"]["available"] is False
        and issue["similarity"]["duplicate"] is False
        and issue["similarity"]["similar_bugs"] == []
        for issue in issues
    )
    json.dumps(response)


def test_cyclic_similarity_result_is_not_attached_to_api_response(tmp_path, monkeypatch):
    class CyclicSimilarityService:
        def add_and_find(self, issue, repository_id: str) -> dict:
            result = {"duplicate": False, "similarity": 0.5, "similar_bugs": []}
            result["similar_bugs"].append(result)
            return result

    ast_result = _repository_ast(tmp_path)
    service = RepositoryAnalysisService(similarity_service=CyclicSimilarityService())
    monkeypatch.setattr(
        "app.services.repository_analysis_service.ast_generator.generate_ast_for_repository",
        lambda _path: ast_result,
    )

    response = _run_repository_analysis(service, tmp_path, "repository-123")

    json.dumps(response)
    similarity = response["static_analysis"]["results"][0]["issues"][0]["similarity"]
    assert similarity["available"] is False
    assert similarity["similar_bugs"] == []
