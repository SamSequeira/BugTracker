"""
error_analysis.py — Automated Failure Pattern and Error Diagnostic Generator.
=============================================================================
Groups prediction mistakes across rules, languages, repositories, and confidence levels.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional


def generate_error_analysis_report(
    test_records: List[Dict[str, Any]],
    y_true: List[int],
    y_pred: List[int],
    y_probs: List[float],
    task_name: str = "Stage 1: Validity Classification",
    target_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Analyzes misclassifications and returns structured error statistics."""
    labels = target_names or ["FALSE_POSITIVE", "TRUE_POSITIVE"]
    errors: List[Dict[str, Any]] = []

    for i, (rec, yt, yp, prob) in enumerate(zip(test_records, y_true, y_pred, y_probs)):
        if yt != yp:
            errors.append({
                "candidate_id": rec.get("candidate_id", f"item_{i}"),
                "rule_id": rec.get("rule_id", "UNKNOWN"),
                "language": rec.get("language", "Unknown"),
                "repository": rec.get("repository", "Unknown"),
                "file_path": rec.get("file_path", "unknown"),
                "line_number": rec.get("line_number", 0),
                "code_snippet": rec.get("code_snippet", "")[:120],
                "ground_truth": labels[yt] if yt < len(labels) else str(yt),
                "prediction": labels[yp] if yp < len(labels) else str(yp),
                "confidence_score": float(prob),
                "analyzer_confidence": rec.get("confidence", "medium"),
                "false_positive_reason": rec.get("false_positive_reason"),
            })

    total_test = len(y_true)
    error_count = len(errors)
    error_rate = (error_count / total_test) * 100 if total_test > 0 else 0.0

    by_rule = Counter(e["rule_id"] for e in errors)
    by_lang = Counter(e["language"] for e in errors)
    by_repo = Counter(e["repository"] for e in errors)
    by_conf = Counter(e["analyzer_confidence"] for e in errors)

    return {
        "task_name": task_name,
        "total_test": total_test,
        "error_count": error_count,
        "error_rate": error_rate,
        "errors": errors,
        "by_rule": dict(by_rule),
        "by_language": dict(by_lang),
        "by_repository": dict(by_repo),
        "by_analyzer_confidence": dict(by_conf),
    }
