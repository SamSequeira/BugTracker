"""
test_source_file_pipeline.py
----------------------------
Comprehensive tests for Architecture & Topology pipeline:
1. SourceFileRepository and IssueRecommendationRepository DAL operations
2. AST Generator line counting and file metadata preservation
3. CandidateIssueMapper SourceFile linking and IssueRecommendation extraction
4. RepositoryAnalysisService complete_analysis_run with SourceFile, CandidateIssue,
   IssueStatus, and IssueRecommendation persistence
"""

import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.issue_recommendation import IssueRecommendation
from app.models.issue_status import IssueStatus
from app.models.source_file import SourceFile
from app.repositories.issue_recommendation_repo import issue_recommendation_repository
from app.repositories.source_file_repo import source_file_repository
from app.services.ast_generator import ast_generator
from app.services.candidate_issue_mapper import candidate_issue_mapper
from app.services.repository_analysis_service import repository_analysis_service
from app.services.static_analyzer.models import CandidateIssue as CandidateIssueDataclass


# ===========================================================================
# 1. SourceFileRepository & IssueRecommendationRepository DAL Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_source_file_repository_crud():
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()
    mock_db.flush = AsyncMock()
    run_id = str(uuid.uuid4())
    sf_id = str(uuid.uuid4())

    sf = SourceFile(
        id=sf_id,
        analysis_run_id=run_id,
        file_path="src/utils.py",
        file_name="utils.py",
        extension=".py",
        language="Python",
        line_count=45,
        is_supported=True,
    )

    # Test create_bulk
    created = await source_file_repository.create_bulk(mock_db, [sf])
    assert len(created) == 1
    assert created[0].id == sf_id
    mock_db.add_all.assert_called_once_with([sf])
    mock_db.flush.assert_called_once()

    # Test empty create_bulk
    assert await source_file_repository.create_bulk(mock_db, []) == []

    # Test get_by_id
    mock_db.get.return_value = sf
    fetched = await source_file_repository.get_by_id(mock_db, sf_id)
    assert fetched == sf
    mock_db.get.assert_called_with(SourceFile, sf_id)


@pytest.mark.asyncio
async def test_issue_recommendation_repository_crud():
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()
    mock_db.flush = AsyncMock()
    issue_id = str(uuid.uuid4())
    rec_id = str(uuid.uuid4())

    rec = IssueRecommendation(
        id=rec_id,
        candidate_issue_id=issue_id,
        recommendation="Catch specific exceptions",
        diff_remove="- except:",
        diff_add="+ except Exception as e:",
        priority_order=1,
        fix_type="code_patch",
    )

    # Test create_bulk
    created = await issue_recommendation_repository.create_bulk(mock_db, [rec])
    assert len(created) == 1
    assert created[0].id == rec_id
    mock_db.add_all.assert_called_once_with([rec])
    mock_db.flush.assert_called_once()

    # Test empty create_bulk
    assert await issue_recommendation_repository.create_bulk(mock_db, []) == []

    # Test get_by_id
    mock_db.get.return_value = rec
    fetched = await issue_recommendation_repository.get_by_id(mock_db, rec_id)
    assert fetched == rec


# ===========================================================================
# 2. AST Generator File Metadata & Line Count Tests
# ===========================================================================

def test_ast_generator_line_count_and_metadata(tmp_path):
    code_content = "def hello():\n    print('world')\n    return True\n"
    code_file = tmp_path / "hello.py"
    code_file.write_text(code_content, encoding="utf-8")

    result = ast_generator.generate_ast(str(code_file), "Python")
    assert result["success"] is True
    assert result["line_count"] == 3
    assert result["file_name"] == "hello.py"
    assert result["extension"] == ".py"
    assert result["language"] == "Python"
    assert result["is_supported"] is True
    assert "ast" in result


def test_ast_generator_for_repository_metadata(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "main.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    (sub / "app.js").write_text("console.log('hi');\n", encoding="utf-8")

    results = ast_generator.generate_ast_for_repository(str(tmp_path))
    assert results["total_files"] == 2
    assert results["supported_files"] == 2
    assert "Python" in results["languages_detected"]
    assert "JavaScript" in results["languages_detected"]

    for file_info in results["files_analyzed"]:
        assert file_info["success"] is True
        assert file_info["line_count"] > 0
        assert file_info["file_name"] in ("main.py", "app.js")
        assert file_info["is_supported"] is True


# ===========================================================================
# 3. CandidateIssueMapper SourceFile & Recommendation Linking Tests
# ===========================================================================

def test_mapper_links_source_file_id():
    run_id = str(uuid.uuid4())
    sf_id1 = str(uuid.uuid4())
    sf_id2 = str(uuid.uuid4())

    source_file_map = {
        "src/auth.py": sf_id1,
        "src/app.js": sf_id2,
    }

    findings = [
        {
            "rule_id": "PY_EXC_001",
            "issue_type": "bare_except",
            "message": "Bare except clause",
            "file_path": "src/auth.py",
            "line_number": 10,
            "code_snippet": "except:",
            "severity": "high",
        },
        CandidateIssueDataclass(
            rule_id="JS_EQ_001",
            issue_type="loose_equality",
            message="Use ===",
            file_path="src/app.js",
            line_number=20,
            column=4,
            code_snippet="if (a == b)",
            severity="low",
        ),
    ]

    issues, statuses = candidate_issue_mapper.to_orm_bulk(
        findings,
        run_id,
        source_file_map=source_file_map,
    )

    assert len(issues) == 2
    assert issues[0].source_file_id == sf_id1
    assert issues[1].source_file_id == sf_id2
    assert statuses[0].candidate_issue_id == issues[0].id
    assert statuses[1].candidate_issue_id == issues[1].id


def test_mapper_extracts_recommendations():
    run_id = str(uuid.uuid4())
    finding = {
        "rule_id": "PY_EXC_001",
        "issue_type": "bare_except",
        "message": "Bare except clause",
        "file_path": "src/auth.py",
        "line_number": 10,
        "recommendations": [
            {
                "recommendation": "Catch specific exception (e.g. PyJWTError)",
                "diff_remove": "- except:",
                "diff_add": "+ except PyJWTError as e:",
                "priority_order": 1,
                "fix_type": "code_patch",
            },
            "Add logging to exception handler",
        ],
    }

    issues, statuses, recs = candidate_issue_mapper.to_orm_bulk_with_relations(
        [finding],
        run_id,
    )

    assert len(issues) == 1
    assert len(statuses) == 1
    assert len(recs) == 2

    assert recs[0].candidate_issue_id == issues[0].id
    assert recs[0].recommendation == "Catch specific exception (e.g. PyJWTError)"
    assert recs[0].diff_remove == "- except:"
    assert recs[0].diff_add == "+ except PyJWTError as e:"
    assert recs[0].priority_order == 1
    assert recs[0].fix_type == "code_patch"

    assert recs[1].candidate_issue_id == issues[0].id
    assert recs[1].recommendation == "Add logging to exception handler"
    assert recs[1].priority_order == 2


# ===========================================================================
# 4. RepositoryAnalysisService complete_analysis_run Integration Tests
# ===========================================================================

@pytest.mark.asyncio
async def test_complete_analysis_run_persists_source_files_and_links_issues():
    mock_db = AsyncMock()
    run_id = str(uuid.uuid4())

    analysis_run_mock = AnalysisRun(
        id=run_id,
        repository_id=str(uuid.uuid4()),
        status="running",
    )
    mock_db.get.return_value = analysis_run_mock

    sample_analysis_result = {
        "repository_path": "repositories/demo-repo",
        "summary": {
            "total_files": 2,
            "supported_files": 2,
            "languages": {"Python": 1, "JavaScript": 1},
        },
        "_files_analyzed": [
            {
                "file": "repositories/demo-repo/main.py",
                "file_name": "main.py",
                "extension": ".py",
                "language": "Python",
                "line_count": 50,
                "is_supported": True,
                "success": True,
            },
            {
                "file": "repositories/demo-repo/app.js",
                "file_name": "app.js",
                "extension": ".js",
                "language": "JavaScript",
                "line_count": 80,
                "is_supported": True,
                "success": True,
            },
        ],
        "candidate_issues": [
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero",
                "file_path": "repositories/demo-repo/main.py",
                "line_number": 15,
                "code_snippet": "x / 0",
                "severity": "high",
                "recommendation": "Add zero-check guard: if divisor == 0: raise ValueError()",
                "diff_remove": "- return x / 0",
                "diff_add": "+ if divisor == 0:\n+     raise ValueError()\n+ return x / divisor",
            },
        ],
        "total_candidate_issues": 1,
    }

    captured_source_files = []
    captured_issues = []
    captured_statuses = []
    captured_recs = []

    async def fake_sf_create(db, source_files):
        captured_source_files.extend(source_files)
        return source_files

    async def fake_issue_create(db, issues):
        captured_issues.extend(issues)
        return issues

    async def fake_status_create(db, statuses):
        captured_statuses.extend(statuses)
        return statuses

    async def fake_rec_create(db, recs):
        captured_recs.extend(recs)
        return recs

    with patch(
        "app.services.repository_analysis_service.technology_repository.create_bulk",
        new_callable=AsyncMock,
    ), patch(
        "app.services.repository_analysis_service.architecture_component_repository.create_bulk",
        new_callable=AsyncMock,
    ), patch(
        "app.services.repository_analysis_service.source_file_repository.create_bulk",
        side_effect=fake_sf_create,
    ), patch(
        "app.services.repository_analysis_service.candidate_issue_repository.create_bulk",
        side_effect=fake_issue_create,
    ), patch(
        "app.services.repository_analysis_service.issue_status_repository.create_bulk",
        side_effect=fake_status_create,
    ), patch(
        "app.services.repository_analysis_service.issue_recommendation_repository.create_bulk",
        side_effect=fake_rec_create,
    ), patch(
        "app.services.repository_analysis_service.architecture_summary_repository.create_or_update",
        new_callable=AsyncMock,
    ):
        completed_run = await repository_analysis_service.complete_analysis_run(
            mock_db,
            run_id,
            sample_analysis_result,
        )

        assert completed_run.status == "completed"
        assert completed_run.total_files == 2
        assert completed_run.supported_files == 2
        assert completed_run.candidate_issues_count == 1
        assert completed_run.completed_at is not None

        # Verify SourceFiles created
        assert len(captured_source_files) == 2
        sf_paths = {sf.file_path for sf in captured_source_files}
        assert "repositories/demo-repo/main.py" in sf_paths
        assert "repositories/demo-repo/app.js" in sf_paths

        # Verify CandidateIssue linked to SourceFile
        assert len(captured_issues) == 1
        main_sf = next(sf for sf in captured_source_files if sf.file_name == "main.py")
        assert captured_issues[0].source_file_id == main_sf.id
        assert captured_issues[0].analysis_run_id == run_id

        # Verify IssueStatus created
        assert len(captured_statuses) == 1
        assert captured_statuses[0].candidate_issue_id == captured_issues[0].id

        # Verify IssueRecommendation created
        assert len(captured_recs) == 1
        assert captured_recs[0].candidate_issue_id == captured_issues[0].id
        assert "zero-check guard" in captured_recs[0].recommendation
        assert captured_recs[0].diff_remove is not None
        assert captured_recs[0].diff_add is not None

        # Verify atomic commit
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()
