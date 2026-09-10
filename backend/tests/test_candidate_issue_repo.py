"""
test_candidate_issue_repo.py
-----------------------------
Unit tests for CandidateIssueRepository and IssueStatusRepository.
"""

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models.candidate_issues import CandidateIssue
from app.models.issue_status import IssueStatus
from app.repositories.candidate_issue_repo import CandidateIssueRepository
from app.repositories.issue_status_repo import IssueStatusRepository


@pytest.mark.asyncio
async def test_candidate_issue_repo_create_bulk():
    repo = CandidateIssueRepository()
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()

    issues = [
        CandidateIssue(
            id=str(uuid.uuid4()),
            analysis_run_id=str(uuid.uuid4()),
            title="Test Issue 1",
            description="Desc 1",
            file_path="foo.py",
            line_number=1,
            severity="high",
            urgency="high",
        ),
        CandidateIssue(
            id=str(uuid.uuid4()),
            analysis_run_id=str(uuid.uuid4()),
            title="Test Issue 2",
            description="Desc 2",
            file_path="bar.py",
            line_number=2,
            severity="medium",
            urgency="medium",
        ),
    ]

    res = await repo.create_bulk(mock_db, issues)

    assert len(res) == 2
    mock_db.add_all.assert_called_once_with(issues)
    mock_db.flush.assert_called_once()
    # Confirm db.commit was NOT called inside create_bulk to preserve transaction control
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_issue_status_repo_create_bulk():
    repo = IssueStatusRepository()
    mock_db = AsyncMock()
    mock_db.add_all = MagicMock()

    statuses = [
        IssueStatus(
            id=str(uuid.uuid4()),
            candidate_issue_id=str(uuid.uuid4()),
            status="open",
        ),
    ]

    res = await repo.create_bulk(mock_db, statuses)

    assert len(res) == 1
    mock_db.add_all.assert_called_once_with(statuses)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
