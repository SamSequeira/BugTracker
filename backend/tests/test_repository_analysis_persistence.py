"""
test_repository_analysis_persistence.py
-----------------------------------------
Focused tests for database persistence integration in the repository analysis workflow.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.analysis_run import AnalysisRun
from app.services.repository_analysis_service import repository_analysis_service


@pytest.mark.asyncio
async def test_successful_analysis_persistence():
    """TEST 1: SUCCESSFUL PERSISTENCE"""
    run_id = str(uuid.uuid4())
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    analysis_run_mock = AnalysisRun(
        id=run_id,
        repository_id=str(uuid.uuid4()),
        status="running",
    )
    mock_db.get.return_value = analysis_run_mock

    sample_analysis_result = {
        "repository_path": "repositories/test-repo",
        "ast_analysis": {
            "summary": {
                "total_files": 10,
                "supported_files": 8,
                "languages": {"Python": 8},
            },
        },
        "candidate_issues": [
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero",
                "file_path": "math.py",
                "line_number": 5,
                "code_snippet": "x / 0",
                "severity": "high",
            },
            {
                "rule_id": "PY_BARE_EXCEPT",
                "issue_type": "bare_except",
                "message": "Bare except clause",
                "file_path": "app.py",
                "line_number": 12,
                "code_snippet": "except:",
                "severity": "medium",
            },
        ],
        "total_candidate_issues": 2,
    }

    with patch(
        "app.services.repository_analysis_service.technology_repository.create_bulk",
        new_callable=AsyncMock,
    ) as mock_tech_create, patch(
        "app.services.repository_analysis_service.architecture_component_repository.create_bulk",
        new_callable=AsyncMock,
    ) as mock_comp_create, patch(
        "app.services.repository_analysis_service.source_file_repository.create_bulk",
        new_callable=AsyncMock,
    ) as mock_source_create, patch(
        "app.services.repository_analysis_service.candidate_issue_repository.create_bulk",
        new_callable=AsyncMock,
    ) as mock_issue_create, patch(
        "app.services.repository_analysis_service.issue_status_repository.create_bulk",
        new_callable=AsyncMock,
    ) as mock_status_create, patch(
        "app.services.repository_analysis_service.issue_recommendation_repository.create_bulk",
        new_callable=AsyncMock,
    ) as mock_rec_create, patch(
        "app.services.repository_analysis_service.architecture_summary_repository.create_or_update",
        new_callable=AsyncMock,
    ) as mock_summary_save:

        updated_run = await repository_analysis_service.complete_analysis_run(
            mock_db,
            run_id,
            sample_analysis_result,
        )

        assert updated_run.status == "completed"
        assert updated_run.total_files == 10
        assert updated_run.supported_files == 8
        assert updated_run.candidate_issues_count == 2
        assert updated_run.completed_at is not None

        # Verify DAL repositories were called with mapped objects
        mock_tech_create.assert_called_once()
        mock_comp_create.assert_called_once()
        mock_source_create.assert_called_once()
        mock_issue_create.assert_called_once()
        mock_status_create.assert_called_once()
        mock_rec_create.assert_called_once()
        mock_summary_save.assert_called_once()

        # Verify exactly one commit for the final persistence phase
        mock_db.commit.assert_called_once()
        mock_db.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_static_analysis_failure_recording():
    """TEST 2: STATIC ANALYSIS FAILURE RECORDING"""
    run_id = str(uuid.uuid4())
    mock_db = AsyncMock()

    analysis_run_mock = AnalysisRun(
        id=run_id,
        repository_id=str(uuid.uuid4()),
        status="running",
    )
    mock_db.get.return_value = analysis_run_mock

    failed_run = await repository_analysis_service.record_analysis_failure(
        mock_db,
        run_id,
        "AST Generation Failed: SyntaxError in main.py",
    )

    assert failed_run is not None
    assert failed_run.status == "failed"
    assert "AST Generation Failed" in failed_run.error_message
    assert failed_run.completed_at is not None

    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_database_persistence_failure_rollback():
    """TEST 3: DATABASE PERSISTENCE FAILURE ROLLBACK"""
    run_id = str(uuid.uuid4())
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    analysis_run_mock = AnalysisRun(
        id=run_id,
        repository_id=str(uuid.uuid4()),
        status="running",
    )
    mock_db.get.return_value = analysis_run_mock

    sample_result = {
        "ast_analysis": {"summary": {"total_files": 5, "supported_files": 5}},
        "candidate_issues": [
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero",
                "file_path": "a.py",
                "line_number": 1,
                "code_snippet": "1/0",
                "severity": "high",
            }
        ],
        "total_candidate_issues": 1,
    }

    # Simulate DB error during create_bulk using correct patch target
    with patch(
        "app.services.repository_analysis_service.candidate_issue_repository.create_bulk",
        side_effect=Exception("Database Connection Dropped"),
    ):
        with pytest.raises(Exception, match="Database Connection Dropped"):
            await repository_analysis_service.complete_analysis_run(
                mock_db,
                run_id,
                sample_result,
            )

    # Rollback must be called when persistence fails
    mock_db.rollback.assert_called()
    assert analysis_run_mock.status == "failed"
    assert "Persistence error: Database Connection Dropped" in analysis_run_mock.error_message
