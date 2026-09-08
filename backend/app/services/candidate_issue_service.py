"""
Candidate Issue Service

Connects the Static Analyzer with the
Candidate Issue Generator.
"""

from typing import Dict, Any

from app.services.static_analyzer.analyzer import static_analyzer
from app.services.static_analyzer.models import CandidateIssue

from app.services.candidate_issue_generator import (
    generate_candidate_issues,
    candidate_issues_to_dict,
)


class CandidateIssueService:
    """
    Generates clean candidate issues from
    repository AST results.
    """

    def generate_from_repository(
        self,
        ast_for_repository: Dict[str, Any]
    ) -> Dict[str, Any]:

        # -----------------------------------------
        # STEP 1: Run Static Analysis
        # -----------------------------------------

        static_analysis_result = (
            static_analyzer.analyze_repository(
                ast_for_repository
            )
        )

        all_candidate_issues = []

        # -----------------------------------------
        # STEP 2: Process every analyzed file
        # -----------------------------------------

        for file_result in static_analysis_result["results"]:

            issues = file_result.get("issues", [])

            # Convert dictionaries returned by
            # StaticAnalyzer back into CandidateIssue objects.

            issue_objects = []

            for issue in issues:

                issue_object = CandidateIssue(
                    rule_id=issue["rule_id"],
                    issue_type=issue["issue_type"],
                    message=issue["message"],
                    file_path=issue["file_path"],
                    line_number=issue["line_number"],
                    column=issue["column"],
                    code_snippet=issue["code_snippet"],
                    evidence=issue["evidence"],
                    severity=issue.get(
                        "severity",
                        "medium"
                    ),
                    confidence=issue.get(
                        "confidence",
                        "medium"
                    ),
                )

                issue_objects.append(issue_object)

            # -----------------------------------------
            # STEP 3: Validate + remove duplicates
            # -----------------------------------------

            candidate_issues = generate_candidate_issues(
                issue_objects
            )

            all_candidate_issues.extend(
                candidate_issues
            )

        # -----------------------------------------
        # STEP 4: Final repository-level cleanup
        # -----------------------------------------

        all_candidate_issues = generate_candidate_issues(
            all_candidate_issues
        )

        # -----------------------------------------
        # STEP 5: Return API-friendly result
        # -----------------------------------------

        return {
            "repository_path":
                ast_for_repository.get(
                    "repository_path",
                    ""
                ),

            "total_candidate_issues":
                len(all_candidate_issues),

            "candidate_issues":
                candidate_issues_to_dict(
                    all_candidate_issues
                ),
        }

    def generate_enriched_from_repository(
        self,
        ast_for_repository: Dict[str, Any],
        repository_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Generate candidate issues and enrich them into full bug reports.
        """
        from app.services.bug_report_service import bug_report_service

        candidate_result = self.generate_from_repository(ast_for_repository)
        return bug_report_service.generate_repository_reports(
            ast_result=ast_for_repository,
            candidate_result=candidate_result,
            repository_id=repository_id,
        )


# Global instance
candidate_issue_service = CandidateIssueService()