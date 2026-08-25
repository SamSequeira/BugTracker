"""
test_analyze_response_schema.py
---------------------------------
Verifies that the analyze endpoint response dict matches the
AnalyzeRepositoryResponse Pydantic schema so Swagger renders correctly,
and that no runtime ResponseValidationError can occur.
"""

from unittest.mock import AsyncMock, patch
import pytest
from pydantic import ValidationError

from app.schemas.analysis_response import (
    AnalyzeRepositoryResponse,
    AnalysisResult,
    AstAnalysis,
    AstSummary,
    CandidateIssueFinding,
)
from app.services.repository_analysis_service import repository_analysis_service


# --------------------------------------------------------------------------
# Real-world sample that mirrors the ACTUAL runtime shape produced by:
#   RepositoryAnalysisService.analyze_repository()
#   -> ast_generator.generate_ast_for_repository()  (languages_detected is dict)
#   -> candidate_issue_service.generate_from_repository() (issues via .to_dict())
#   -> _format_analysis_result() (summary only, no raw AST file trees)
# --------------------------------------------------------------------------

REAL_ANALYSIS_RESULT = {
    "repository_path": "repositories/abc-demo",
    "ast_analysis": {
        "summary": {
            "total_files": 89,
            "supported_files": 89,
            # languages is a DICT (name -> count), not a list
            "languages": {
                "JavaScript": 17,
                "Python": 72,
            },
        },
    },
    "candidate_issues": [
        {
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "message": "Division by zero detected",
            "file_path": "main.py",
            "line_number": 5,
            "column": 4,
            "code_snippet": "x / 0",
            "evidence": {"operator": "/", "right_operand": "0"},
            "severity": "high",
        }
    ],
    "total_candidate_issues": 1,
}


# --------------------------------------------------------------------------
# Schema validation tests
# --------------------------------------------------------------------------

def test_languages_as_dict_validates():
    """
    REGRESSION: languages must be Dict[str, int] not List[str].
    This was the root cause of the ResponseValidationError seen at runtime.
    """
    payload = {
        "repository_id": "repo-123",
        "analysis_run_id": "run-456",
        "message": "Repository analyzed successfully.",
        "analysis": REAL_ANALYSIS_RESULT,
    }
    response = AnalyzeRepositoryResponse(**payload)
    assert response.analysis.ast_analysis.summary.languages == {
        "JavaScript": 17,
        "Python": 72,
    }


def test_full_real_world_shape_validates():
    """Full real-world response dict must validate without error."""
    payload = {
        "repository_id": "ebcb1ee1-e272-4487-88c9-63a522063bcb",
        "analysis_run_id": "aaaa-bbbb-cccc-dddd",
        "message": "Repository analyzed successfully.",
        "analysis": REAL_ANALYSIS_RESULT,
    }
    response = AnalyzeRepositoryResponse(**payload)
    assert response.repository_id == "ebcb1ee1-e272-4487-88c9-63a522063bcb"
    assert response.analysis.total_candidate_issues == 1
    assert response.analysis.ast_analysis.summary.total_files == 89
    assert response.analysis.candidate_issues[0].severity == "high"


def test_response_does_not_contain_raw_files_ast():
    """
    REGRESSION: Repository analysis response must NOT contain the massive raw files AST array,
    preventing Swagger UI rendering crashes.
    """
    payload = {
        "repository_id": "repo-123",
        "analysis_run_id": "run-456",
        "message": "Repository analyzed successfully.",
        "analysis": REAL_ANALYSIS_RESULT,
    }
    response = AnalyzeRepositoryResponse(**payload)
    response_dict = response.model_dump()

    # Confirm ast_analysis contains summary and NOT files
    assert "summary" in response_dict["analysis"]["ast_analysis"]
    assert "files" not in response_dict["analysis"]["ast_analysis"]


def test_candidate_issue_finding_maps_to_dict_output():
    """CandidateIssueFinding maps exactly to the fields produced by CandidateIssue.to_dict()."""
    issue = CandidateIssueFinding(
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Division by zero",
        file_path="math.py",
        line_number=5,
        column=4,
        code_snippet="x / 0",
        evidence={"right_operand": "0"},
        severity="high",
    )
    assert issue.rule_id == "PY_DIV_001"
    assert issue.column == 4
    assert isinstance(issue.evidence, dict)


def test_empty_candidate_issues_validates():
    """Zero findings (no candidate issues) must still validate."""
    result = dict(REAL_ANALYSIS_RESULT)
    result["candidate_issues"] = []
    result["total_candidate_issues"] = 0

    payload = {
        "repository_id": "repo-123",
        "analysis_run_id": "run-456",
        "message": "Repository analyzed successfully.",
        "analysis": result,
    }
    response = AnalyzeRepositoryResponse(**payload)
    assert response.analysis.total_candidate_issues == 0
    assert response.analysis.candidate_issues == []


def test_analyze_response_schema_rejects_missing_required_field():
    """Schema must reject a payload missing required top-level fields."""
    with pytest.raises(ValidationError):
        AnalyzeRepositoryResponse()


def test_openapi_schema_includes_analyze_endpoint():
    """FastAPI OpenAPI schema must declare a non-empty response for the analyze endpoint."""
    from app.main import app

    schema = app.openapi()
    paths = schema.get("paths", {})
    analyze = paths.get("/api/v1/repositories/analyze/{repository_id}", {})

    assert "post" in analyze, "POST /analyze/{repository_id} missing from OpenAPI schema"

    responses = analyze["post"].get("responses", {})
    assert "200" in responses, "200 response missing from analyze endpoint schema"

    content = responses["200"].get("content", {})
    assert content, "200 response has no content/schema — Swagger cannot render it"

    json_schema = content.get("application/json", {}).get("schema", {})
    assert json_schema, "200 response JSON schema is empty — Swagger will show render error"


@pytest.mark.asyncio
async def test_internal_pipeline_passes_full_ast_to_static_analyzer(tmp_path):
    """
    VERIFICATION: Internal pipeline still generates full AST for all files
    and passes it to candidate_issue_service before response formatting.
    """
    sample_ast_result = {
        "repository_path": str(tmp_path),
        "files_analyzed": [
            {
                "success": True,
                "file": str(tmp_path / "main.py"),
                "language": "Python",
                "ast": {"type": "module", "children": []},
            }
        ],
        "languages_detected": {"Python": 1},
        "total_files": 1,
        "supported_files": 1,
    }

    sample_candidate_result = {
        "repository_path": str(tmp_path),
        "total_candidate_issues": 0,
        "candidate_issues": [],
    }

    with patch("app.services.repository_analysis_service.ast_generator.generate_ast_for_repository", return_value=sample_ast_result) as mock_ast_gen, \
         patch("app.services.repository_analysis_service.candidate_issue_service.generate_from_repository", return_value=sample_candidate_result) as mock_candidate_gen:

        res = await repository_analysis_service.analyze_repository(str(tmp_path))

        # 1. AST generator was called
        mock_ast_gen.assert_called_once_with(str(tmp_path))

        # 2. Candidate issue service received the FULL AST result including files_analyzed
        mock_candidate_gen.assert_called_once_with(sample_ast_result)

        # 3. Formatted response does NOT contain files_analyzed/raw AST
        assert "files" not in res["ast_analysis"]
        assert res["ast_analysis"]["summary"]["total_files"] == 1
        assert res["ast_analysis"]["summary"]["languages"] == {"Python": 1}


@pytest.mark.asyncio
async def test_analyze_file_endpoint_still_returns_full_ast(tmp_path):
    """
    VERIFICATION: Single-file analyze_file endpoint continues returning full AST unchanged.
    """
    code_file = tmp_path / "test.py"
    code_file.write_text("x = 1\n", encoding="utf-8")

    sample_file_ast = {
        "success": True,
        "file": str(code_file),
        "language": "Python",
        "ast": {"type": "module", "children": [{"type": "assignment"}]},
    }

    with patch("app.services.repository_analysis_service.ast_generator.generate_ast", return_value=sample_file_ast):
        res = await repository_analysis_service.analyze_file(str(code_file))

        assert res["success"] is True
        assert "ast" in res
        assert res["ast"]["type"] == "module"
