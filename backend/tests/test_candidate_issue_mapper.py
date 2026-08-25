"""
test_candidate_issue_mapper.py
-------------------------------
Unit tests for CandidateIssueMapper service.
"""

import uuid
from app.services.candidate_issue_mapper import candidate_issue_mapper
from app.services.static_analyzer.models import CandidateIssue as CandidateIssueDataclass


def test_mapper_from_dataclass():
    run_id = str(uuid.uuid4())
    dataclass_issue = CandidateIssueDataclass(
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Possible division by zero detected",
        file_path="src/math.py",
        line_number=42,
        column=10,
        code_snippet="res = a / 0",
        evidence={"operator": "/"},
        severity="critical",
    )

    issue_orm, status_orm = candidate_issue_mapper.to_orm(dataclass_issue, run_id)

    assert issue_orm.id is not None
    assert issue_orm.analysis_run_id == run_id
    assert issue_orm.title == "Division By Zero (PY_DIV_001)"
    assert "Possible division by zero detected" in issue_orm.description
    assert "Code Snippet:\nres = a / 0" in issue_orm.description
    assert issue_orm.file_path == "src/math.py"
    assert issue_orm.line_number == 42
    assert issue_orm.severity == "critical"
    assert issue_orm.urgency == "high"

    assert status_orm.candidate_issue_id == issue_orm.id
    assert status_orm.status == "open"


def test_mapper_from_dict():
    run_id = str(uuid.uuid4())
    dict_issue = {
        "rule_id": "JS_EQ_001",
        "issue_type": "loose_equality",
        "message": "Use === instead of ==",
        "file_path": "src/app.js",
        "line_number": 15,
        "code_snippet": "if (a == b)",
        "severity": "low",
    }

    issue_orm, status_orm = candidate_issue_mapper.to_orm(dict_issue, run_id)

    assert issue_orm.analysis_run_id == run_id
    assert issue_orm.title == "Loose Equality (JS_EQ_001)"
    assert issue_orm.severity == "low"
    assert issue_orm.urgency == "low"
    assert status_orm.candidate_issue_id == issue_orm.id
    assert status_orm.status == "open"


def test_mapper_bulk():
    run_id = str(uuid.uuid4())
    findings = [
        CandidateIssueDataclass(
            rule_id="PY_BARE_EXCEPT",
            issue_type="bare_except",
            message="Bare except block used",
            file_path="src/main.py",
            line_number=10,
            column=0,
            code_snippet="except:",
            severity="medium",
        ),
        {
            "rule_id": "JAVA_EMPTY_CATCH",
            "issue_type": "empty_catch",
            "message": "Empty catch block",
            "file_path": "src/Main.java",
            "line_number": 25,
            "severity": "high",
        },
    ]

    issues_orm, statuses_orm = candidate_issue_mapper.to_orm_bulk(findings, run_id)

    assert len(issues_orm) == 2
    assert len(statuses_orm) == 2
    assert issues_orm[0].urgency == "medium"
    assert issues_orm[1].urgency == "high"
    assert statuses_orm[0].candidate_issue_id == issues_orm[0].id
    assert statuses_orm[1].candidate_issue_id == issues_orm[1].id
