"""
routing.py — Production Risk-Controlled Routing & Human Triaging Engine.
========================================================================
Implements deterministic 5-way routing:
1. AUTO_ACCEPT: High-certainty predictions with low drift.
2. SECONDARY_MODEL: Ambiguous margins routed to secondary model cross-verification.
3. HUMAN_REVIEW: Model disagreement, high entropy, unknown rule/language.
4. OOD_REJECT: High drift score (>= 0.30) indicating foreign language or unparseable input.
5. SYSTEM_ERROR: Payload limit exceeded (> 500KB) or input corruption.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

PAYLOAD_LIMIT_BYTES = 500 * 1024  # 500 KB safe limit


def route_candidate_issue(
    record: Dict[str, Any],
    svm_prob: float,
    drift_score: float,
    is_drift: bool,
    distilbert_prob: Optional[float] = None,
    payload_bytes: int = 200,
) -> Tuple[str, str, float]:
    """
    Deterministic risk-controlled routing policy.
    Returns: (routing_decision, rationale, final_confidence)
    """
    # 1. Payload Limit Guard (> 500KB)
    if payload_bytes > PAYLOAD_LIMIT_BYTES:
        return "SYSTEM_ERROR", "PAYLOAD_LIMIT_EXCEEDED (> 500KB)", 0.0

    # 2. Extreme OOD Drift Guard
    if drift_score >= 0.30 or is_drift:
        return "OOD_REJECT", f"HIGH_DRIFT_SCORE ({drift_score:.2f} >= 0.30)", svm_prob

    # 3. Unknown Rule / Language Guard
    rule_id = str(record.get("rule_id", ""))
    lang = str(record.get("language", "")).lower()
    if "UNKNOWN" in rule_id or "CUSTOM" in rule_id or lang not in {"python", "javascript", "java"}:
        return "HUMAN_REVIEW", "UNRECOGNIZED_RULE_OR_LANGUAGE", svm_prob

    # 4. Strict High-Precision Auto-Accept (p >= 0.90 or p <= 0.05 with low drift)
    if svm_prob >= 0.90 and drift_score < 0.25:
        return "AUTO_ACCEPT", "HIGH_CONFIDENCE_TRUE_POSITIVE (p >= 0.90)", svm_prob
    if svm_prob <= 0.05 and drift_score < 0.25:
        return "AUTO_ACCEPT", "HIGH_CONFIDENCE_FALSE_POSITIVE (p <= 0.05)", svm_prob

    # 5. Moderate Confidence -> Secondary Model (DistilBERT) Cross-Verification
    if distilbert_prob is not None:
        svm_pred = svm_prob >= 0.40
        bert_pred = distilbert_prob >= 0.50
        if svm_pred != bert_pred:
            return "HUMAN_REVIEW", "MODEL_DISAGREEMENT (SVM vs DistilBERT)", (svm_prob + distilbert_prob) / 2.0
        # If models agree in the ultra-confident regions
        consensus_prob = (svm_prob + distilbert_prob) / 2.0
        if consensus_prob >= 0.90 or consensus_prob <= 0.10:
            return "AUTO_ACCEPT", "CASCADE_CONSENSUS_HIGH_CERTAINTY", consensus_prob
        return "SECONDARY_MODEL", "CASCADE_CONSENSUS_REQUIRES_SECONDARY_INSPECTION", consensus_prob

    # If secondary model not available, route moderate band to human review
    return "HUMAN_REVIEW", "AMBIGUOUS_CONFIDENCE_BAND (0.05 < p < 0.90)", svm_prob
