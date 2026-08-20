"""
error_analysis.py — Error Analysis & Misclassification Reporting.
=================================================================
Generates detailed error reports sorted by misclassification severity,
prioritizing critical under-classification errors.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .config import (
    UNDERCLASSIFICATION_PRIORITY_PAIRS,
    UNDERCLASSIFICATION_SEVERITY_PAIRS,
)


def compute_misclassification_severity_rank(
    actual_sev: str,
    pred_sev: str,
    actual_prio: str,
    pred_prio: str,
) -> int:
    """
    Rank error severity for sorting (higher score = more severe error):
        - Critical -> Low: Rank 100
        - P1 -> P4: Rank 95
        - Critical -> Medium: Rank 80
        - P1 -> P3: Rank 75
        - High -> Low: Rank 70
        - P2 -> P4: Rank 65
        - Other errors: Rank 10
        - Correct: Rank 0
    """
    score = 0
    sev_pair = (actual_sev, pred_sev)
    prio_pair = (actual_prio, pred_prio)

    if sev_pair == ("critical", "low"):
        score += 100
    elif sev_pair == ("critical", "medium"):
        score += 80
    elif sev_pair == ("high", "low"):
        score += 70
    elif actual_sev != pred_sev:
        score += 10

    if prio_pair == ("p1", "p4"):
        score += 95
    elif prio_pair == ("p1", "p3"):
        score += 75
    elif prio_pair == ("p2", "p4"):
        score += 65
    elif actual_prio != pred_prio:
        score += 10

    return score


class ErrorAnalyzer:
    """Generates structured error reports for multi-task predictions."""

    @staticmethod
    def generate_error_report(
        records: List[Dict[str, Any]],
        actual_severity: List[str],
        predicted_severity: List[str],
        severity_confidences: List[float],
        actual_priority: List[str],
        predicted_priority: List[str],
        priority_confidences: List[float],
    ) -> List[Dict[str, Any]]:
        """
        Build an error report list sorted with most serious errors first.
        """
        errors = []

        for idx, (rec, act_s, pred_s, conf_s, act_p, pred_p, conf_p) in enumerate(
            zip(
                records,
                actual_severity,
                predicted_severity,
                severity_confidences,
                actual_priority,
                predicted_priority,
                priority_confidences,
            )
        ):
            # Check if there is any misclassification
            if act_s != pred_s or act_p != pred_p:
                rank = compute_misclassification_severity_rank(act_s, pred_s, act_p, pred_p)
                is_underclass_sev = (act_s, pred_s) in UNDERCLASSIFICATION_SEVERITY_PAIRS
                is_underclass_prio = (act_p, pred_p) in UNDERCLASSIFICATION_PRIORITY_PAIRS

                errors.append({
                    "index": idx,
                    "rule_id": rec.get("rule_id", "N/A"),
                    "issue_type": rec.get("issue_type", "N/A"),
                    "code_snippet": rec.get("code_snippet", "")[:60],
                    "actual_severity": act_s,
                    "predicted_severity": pred_s,
                    "severity_confidence": round(conf_s, 4),
                    "actual_priority": act_p,
                    "predicted_priority": pred_p,
                    "priority_confidence": round(conf_p, 4),
                    "is_underclassification": is_underclass_sev or is_underclass_prio,
                    "severity_rank": rank,
                })

        # Sort descending by severity rank
        errors.sort(key=lambda x: x["severity_rank"], reverse=True)
        return errors
