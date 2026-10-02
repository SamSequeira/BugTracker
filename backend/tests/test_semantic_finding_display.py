"""
test_semantic_finding_display.py
--------------------------------
Verify that CandidateIssueResponse and repository finding mapping
preserve and expose all semantic LLM pipeline output fields:
- title
- bug_type / category
- description / reasoning
- file_path
- exact buggy line / range
- evidence / relevant_code
- expected_behavior
- actual_behavior
- suggested_fix
- confidence
"""

import uuid
from datetime import datetime, timezone
import pytest
from app.models.analysis_run import AnalysisRun
from app.models.candidate_issues import CandidateIssue
from app.models.issue_recommendation import IssueRecommendation
from app.models.repository import Repository
from app.schemas.candidate_issues import CandidateIssueResponse
from app.api.v1.repositories import list_repository_candidate_issues
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from data.dbconnection.base import Base


def test_candidate_issue_response_schema():
    raw_issue = {
        "id": "sem-100",
        "analysis_run_id": "run-100",
        "title": "Unvalidated Dict Key Access",
        "description": "Accessing config['timeout'] without checking existence.",
        "file_path": "backend/app/config.py",
        "line_number": 45,
        "column": None,
        "rule_id": "semantic_bug",
        "issue_type": "semantic_bug",
        "severity": "high",
        "urgency": "needs_review",
        "created_at": datetime.now(timezone.utc),
        "evidence": {
            "source": "semantic_llm",
            "confidence": 0.88,
            "category": "KeyError Risk",
            "bug_type": "KeyError Risk",
            "function_name": "load_config",
            "qualified_name": "backend.app.config.load_config",
            "file": "backend/app/config.py",
            "function_start_line": 40,
            "function_end_line": 50,
            "buggy_line": 45,
            "start_line": 45,
            "end_line": 45,
            "evidence": "return config['timeout']",
            "reasoning": "config may not have 'timeout' configured in all deployment environments.",
            "expected_behavior": "Use config.get('timeout', 30)",
            "actual_behavior": "Raises KeyError when timeout is omitted",
            "relevant_code": "return config['timeout']",
            "suggested_fix": "return config.get('timeout', 30)",
        },
    }

    validated = CandidateIssueResponse.model_validate(raw_issue)
    assert validated.title == "Unvalidated Dict Key Access"
    assert validated.file_path == "backend/app/config.py"
    assert validated.line_number == 45
    assert validated.confidence == 0.88
    assert validated.suggested_fix == "return config.get('timeout', 30)"
    assert validated.evidence["bug_type"] == "KeyError Risk"
    assert validated.evidence["expected_behavior"] == "Use config.get('timeout', 30)"
    assert validated.evidence["actual_behavior"] == "Raises KeyError when timeout is omitted"
    assert validated.evidence["relevant_code"] == "return config['timeout']"


@pytest.mark.asyncio
async def test_repository_candidate_issues_endpoint_mapping():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        repo = Repository(
            id=str(uuid.uuid4()),
            name="semantic-test-repo",
            s3_key="repositories/semantic-test-repo.zip",
        )
        db.add(repo)
        await db.flush()

        run = AnalysisRun(
            id=str(uuid.uuid4()),
            repository_id=repo.id,
            status="completed",
        )
        db.add(run)
        await db.flush()

        issue = CandidateIssue(
            id=str(uuid.uuid4()),
            analysis_run_id=run.id,
            title="Off-by-one Boundary Condition",
            description="Loop iterates through len(items) instead of len(items) - 1.",
            file_path="src/parser.py",
            line_number=28,
            severity="high",
            urgency="needs_review",
            issue_type="semantic_bug",
            message="Loop iterates through len(items) instead of len(items) - 1.",
            code_snippet="for i in range(len(items)):\n    process(items[i+1])",
            evidence={
                "source": "semantic_llm",
                "confidence": 0.95,
                "category": "Boundary Error",
                "bug_type": "Boundary Error",
                "start_line": 27,
                "end_line": 28,
                "buggy_line": 28,
                "evidence": "process(items[i+1])",
                "reasoning": "Accessing items[i+1] on the final iteration will raise IndexError.",
                "expected_behavior": "Range should terminate at len(items) - 1 or iterate pairs.",
                "actual_behavior": "Raises IndexError when i == len(items) - 1.",
                "relevant_code": "process(items[i+1])",
                "suggested_fix": "for i in range(len(items) - 1):",
            },
        )
        db.add(issue)
        await db.flush()

        rec = IssueRecommendation(
            id=str(uuid.uuid4()),
            candidate_issue_id=issue.id,
            recommendation="for i in range(len(items) - 1):",
            diff_remove="for i in range(len(items)):",
            diff_add="for i in range(len(items) - 1):",
            fix_type="ai_patch",
            priority_order=1,
        )
        db.add(rec)
        await db.commit()

        # Call endpoint handler
        resp = await list_repository_candidate_issues(repository_id=repo.id, db=db)
        assert resp["total"] == 1
        item = resp["items"][0]

        # Verify all 10 fields are present and properly mapped
        assert item["title"] == "Off-by-one Boundary Condition"
        assert item["file_path"] == "src/parser.py"
        assert item["line_number"] == 28
        assert item["severity"] == "high"
        assert item["confidence"] == 0.95
        assert item["evidence"]["category"] == "Boundary Error"
        assert item["evidence"]["reasoning"].startswith("Accessing items[i+1]")
        assert item["evidence"]["expected_behavior"].startswith("Range should terminate")
        assert item["evidence"]["actual_behavior"].startswith("Raises IndexError")
        assert item["evidence"]["relevant_code"] == "process(items[i+1])"
        assert item["suggested_fix"]["remove"] == "for i in range(len(items)):"
        assert item["suggested_fix"]["add"] == "for i in range(len(items) - 1):"
