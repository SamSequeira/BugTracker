"""
analyzer.py
-----------
StaticAnalyzer — orchestrates all registered rules against a single
normalized AST dict produced by ASTGenerator.

Usage
-----
    from app.services.static_analyzer import StaticAnalyzer

    issues = StaticAnalyzer().analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
        source_code="...",        # raw source text (optional)
    )

    for issue in issues:
        print(issue.to_dict())
"""

import logging
from typing import Dict, Any, List, Optional

from .models import CandidateIssue
from .rules import ALL_RULES
from .severity import normalize_scanner_severity


logger = logging.getLogger(__name__)


class StaticAnalyzer:
    """
    Applies all registered rules to a normalized AST.

    Rules are executed independently — an exception in one rule does
    not abort the others.  Errors are collected and returned alongside
    the issues so callers can surface them without crashing.
    """

    def __init__(self) -> None:
        self._rules = ALL_RULES

    def analyze(
        self,
        ast: Dict[str, Any],
        language: str,
        file_path: str,
        source_code: Optional[str] = None,
        repository_id: Optional[str] = None,
        similarity_service: Any = None,
    ) -> Dict[str, Any]:
        """
        Run every applicable rule and return a result dict.

        Parameters
        ----------
        ast         : Normalized AST dict (the "ast" key from ASTGenerator output).
        language    : "Python" | "JavaScript" | "Java"
        file_path   : Path of the file being analyzed.
        source_code : Raw source text.  If omitted, code_snippet falls back to
                      the text embedded in each AST node.

        Returns
        -------
        {
            "file_path":    str,
            "language":     str,
            "issues":       [ CandidateIssue.to_dict(), ... ],
            "issue_count":  int,
            "rules_run":    [ rule_id, ... ],
            "errors":       [ { "rule_id": ..., "error": ... }, ... ],
        }
        """
        source_lines: List[str] = (
            source_code.splitlines() if source_code else []
        )

        issues: List[CandidateIssue] = []
        rules_run: List[str] = []
        errors: List[dict] = []

        for rule in self._rules:
            if language not in rule.LANGUAGES:
                continue

            rules_run.append(rule.rule_id)

            try:
                for issue in rule.analyze(ast, file_path, source_lines):
                    issues.append(issue)
            except Exception as exc:  # noqa: BLE001
                errors.append({
                    "rule_id": rule.rule_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        serialized_issues = []
        similarity_result_factory = None
        if repository_id is not None:
            # Imported lazily to avoid a package import cycle: the similarity
            # service consumes CandidateIssue from this package.
            from app.services.bug_similarity_service import BugSimilarityService

            similarity_result_factory = BugSimilarityService
        for issue in issues:
            serialized_issue = issue.to_dict()
            serialized_issue["severity"] = normalize_scanner_severity(
                serialized_issue.get("severity")
            )
            if repository_id is not None:
                if similarity_service is None:
                    serialized_issue["similarity"] = similarity_result_factory.unavailable_result()
                else:
                    try:
                        raw_similarity = similarity_service.add_and_find(issue, repository_id)
                        serialized_issue["similarity"] = similarity_result_factory.safe_result(
                            raw_similarity
                        )
                    except Exception:  # noqa: BLE001 - similarity must not hide findings
                        logger.warning(
                            "Similarity processing failed for repository=%s rule=%s "
                            "file=%s line=%s",
                            repository_id,
                            issue.rule_id,
                            issue.file_path,
                            issue.line_number,
                            exc_info=True,
                        )
                        serialized_issue["similarity"] = similarity_result_factory.unavailable_result()
            serialized_issues.append(serialized_issue)

        return {
            "file_path": file_path,
            "language": language,
            "issues": serialized_issues,
            "issue_count": len(issues),
            "rules_run": rules_run,
            "errors": errors,
        }

    def analyze_repository(
        self,
        ast_for_repository: Dict[str, Any],
        repository_id: Optional[str] = None,
        similarity_service: Any = None,
    ) -> Dict[str, Any]:
        """
        Convenience wrapper: accepts the full dict returned by
        ASTGenerator.generate_ast_for_repository() and runs analysis
        on every successfully parsed file.

        Parameters
        ----------
        ast_for_repository : The dict returned by
            ASTGenerator.generate_ast_for_repository()

        Returns
        -------
        {
            "repository_path": str,
            "files_analyzed":  int,
            "total_issues":    int,
            "results":         [ per-file result dict, ... ],
        }
        """
        results = []
        total_issues = 0

        for file_result in ast_for_repository.get("files_analyzed", []):
            if not file_result.get("success"):
                continue

            file_analysis = self.analyze(
                ast=file_result["ast"],
                language=file_result["language"],
                file_path=file_result["file"],
                repository_id=repository_id,
                similarity_service=similarity_service,
            )
            total_issues += file_analysis["issue_count"]
            results.append(file_analysis)

        return {
            "repository_path": ast_for_repository.get("repository_path", ""),
            "files_analyzed": len(results),
            "total_issues": total_issues,
            "results": results,
        }


# Module-level singleton
static_analyzer = StaticAnalyzer()

"""
analyzer.py
-----------
StaticAnalyzer — orchestrates all registered rules against a single
normalized AST dict produced by ASTGenerator.

Usage
-----
    from app.services.static_analyzer import StaticAnalyzer

    issues = StaticAnalyzer().analyze(
        ast=ast_result["ast"],
        language=ast_result["language"],
        file_path=ast_result["file"],
        source_code="...",        # raw source text (optional)
    )

    for issue in issues:
        print(issue.to_dict())
"""

import logging
from typing import Dict, Any, List, Optional

from .models import CandidateIssue
from .rules import ALL_RULES
from .severity import normalize_scanner_severity


logger = logging.getLogger(__name__)


class StaticAnalyzer:
    """
    Applies all registered rules to a normalized AST.

    Rules are executed independently — an exception in one rule does
    not abort the others.  Errors are collected and returned alongside
    the issues so callers can surface them without crashing.
    """

    def __init__(self) -> None:
        self._rules = ALL_RULES

    def analyze(
        self,
        ast: Dict[str, Any],
        language: str,
        file_path: str,
        source_code: Optional[str] = None,
        repository_id: Optional[str] = None,
        similarity_service: Any = None,
    ) -> Dict[str, Any]:
        """
        Run every applicable rule and return a result dict.

        Parameters
        ----------
        ast         : Normalized AST dict (the "ast" key from ASTGenerator output).
        language    : "Python" | "JavaScript" | "Java"
        file_path   : Path of the file being analyzed.
        source_code : Raw source text.  If omitted, code_snippet falls back to
                      the text embedded in each AST node.

        Returns
        -------
        {
            "file_path":    str,
            "language":     str,
            "issues":       [ CandidateIssue.to_dict(), ... ],
            "issue_count":  int,
            "rules_run":    [ rule_id, ... ],
            "errors":       [ { "rule_id": ..., "error": ... }, ... ],
        }
        """
        source_lines: List[str] = (
            source_code.splitlines() if source_code else []
        )

        issues: List[CandidateIssue] = []
        rules_run: List[str] = []
        errors: List[dict] = []

        for rule in self._rules:
            if language not in rule.LANGUAGES:
                continue

            rules_run.append(rule.rule_id)

            try:
                for issue in rule.analyze(ast, file_path, source_lines):
                    issues.append(issue)
            except Exception as exc:  # noqa: BLE001
                errors.append({
                    "rule_id": rule.rule_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })

        serialized_issues = []
        similarity_result_factory = None
        if repository_id is not None:
            # Imported lazily to avoid a package import cycle: the similarity
            # service consumes CandidateIssue from this package.
            from app.services.bug_similarity_service import BugSimilarityService

            similarity_result_factory = BugSimilarityService
        for issue in issues:
            serialized_issue = issue.to_dict()
            serialized_issue["severity"] = normalize_scanner_severity(
                serialized_issue.get("severity")
            )
            if repository_id is not None:
                if similarity_service is None:
                    serialized_issue["similarity"] = similarity_result_factory.unavailable_result()
                else:
                    try:
                        raw_similarity = similarity_service.add_and_find(issue, repository_id)
                        serialized_issue["similarity"] = similarity_result_factory.safe_result(
                            raw_similarity
                        )
                    except Exception:  # noqa: BLE001 - similarity must not hide findings
                        logger.warning(
                            "Similarity processing failed for repository=%s rule=%s "
                            "file=%s line=%s",
                            repository_id,
                            issue.rule_id,
                            issue.file_path,
                            issue.line_number,
                            exc_info=True,
                        )
                        serialized_issue["similarity"] = similarity_result_factory.unavailable_result()
            serialized_issues.append(serialized_issue)

        return {
            "file_path": file_path,
            "language": language,
            "issues": serialized_issues,
            "issue_count": len(issues),
            "rules_run": rules_run,
            "errors": errors,
        }

    def analyze_repository(
        self,
        ast_for_repository: Dict[str, Any],
        repository_id: Optional[str] = None,
        similarity_service: Any = None,
    ) -> Dict[str, Any]:
        """
        Convenience wrapper: accepts the full dict returned by
        ASTGenerator.generate_ast_for_repository() and runs analysis
        on every successfully parsed file.

        Parameters
        ----------
        ast_for_repository : The dict returned by
            ASTGenerator.generate_ast_for_repository()

        Returns
        -------
        {
            "repository_path": str,
            "files_analyzed":  int,
            "total_issues":    int,
            "results":         [ per-file result dict, ... ],
        }
        """
        results = []
        total_issues = 0

        for file_result in ast_for_repository.get("files_analyzed", []):
            if not file_result.get("success"):
                continue

            file_analysis = self.analyze(
                ast=file_result["ast"],
                language=file_result["language"],
                file_path=file_result["file"],
                repository_id=repository_id,
                similarity_service=similarity_service,
            )
            total_issues += file_analysis["issue_count"]
            results.append(file_analysis)

        return {
            "repository_path": ast_for_repository.get("repository_path", ""),
            "files_analyzed": len(results),
            "total_issues": total_issues,
            "results": results,
        }

    def get_all_metrics(self) -> Dict[str, Any]:
        """Aggregate suppression and reporting metrics across all registered rules."""
        return {rule.rule_id: rule.get_metrics() for rule in self._rules}

    def reset_all_metrics(self) -> None:
        """Reset metrics counters across all registered rules."""
        for rule in self._rules:
            rule.reset_metrics()


# Module-level singleton
static_analyzer = StaticAnalyzer()

