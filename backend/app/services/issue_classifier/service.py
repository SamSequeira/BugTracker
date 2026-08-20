"""
service.py — Issue Classification Service Interface.
=====================================================
Integrates the IssueClassifier inference engine with repository-level
candidate issue processing pipelines.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .classifier import IssueClassifier
from .config import InferenceConfig


class IssueClassificationService:
    """Service layer for applying ML classification to candidate issues."""

    def __init__(
        self,
        classifier: Optional[IssueClassifier] = None,
        config: Optional[InferenceConfig] = None,
    ) -> None:
        self.config = config or InferenceConfig()
        self.classifier = classifier or IssueClassifier(config=self.config)

    def classify_candidate_issues(
        self,
        issues: List[Dict[str, Any]],
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Classify a list of candidate issue dictionaries."""
        return self.classifier.enrich_candidate_issues_batch(issues, language=language)

    def classify_analysis_result(
        self,
        analysis_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Classify candidate issues inside a static analyzer result dict."""
        return self.classifier.classify_repository_analysis(analysis_result)


# Global singleton instance
issue_classification_service = IssueClassificationService()
