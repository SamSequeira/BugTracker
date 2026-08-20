from app.services.static_analyzer.models import CandidateIssue

from app.services.candidate_issue_generator import (
    generate_candidate_issues,
)


def main():

    # -----------------------------------------
    # Create sample issue
    # -----------------------------------------

    issue1 = CandidateIssue(
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Possible division by zero",
        file_path="test.py",
        line_number=10,
        column=5,
        code_snippet="x = a / 0",
        evidence={
            "operator": "/",
            "right_operand": "0"
        },
        severity="medium",
    )

    # -----------------------------------------
    # Duplicate issue
    # -----------------------------------------

    issue2 = CandidateIssue(
        rule_id="PY_DIV_001",
        issue_type="division_by_zero",
        message="Possible division by zero",
        file_path="test.py",
        line_number=10,
        column=5,
        code_snippet="x = a / 0",
        evidence={
            "operator": "/",
            "right_operand": "0"
        },
        severity="medium",
    )

    issues = [issue1, issue2]

    # -----------------------------------------
    # Generate candidate issues
    # -----------------------------------------

    result = generate_candidate_issues(issues)

    print("\n========== CANDIDATE ISSUE TEST ==========")

    print("Input issues:", len(issues))
    print("Output issues:", len(result))

    for issue in result:

        print("\n--- Candidate Issue ---")

        print("Rule ID      :", issue.rule_id)
        print("Issue Type   :", issue.issue_type)
        print("File         :", issue.file_path)
        print("Line         :", issue.line_number)
        print("Code         :", issue.code_snippet)
        print("Description  :", issue.message)
        print("Evidence     :", issue.evidence)
        print("Severity     :", issue.severity)


if __name__ == "__main__":
    main()