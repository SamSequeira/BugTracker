"""
severity.py — Production Rule-Based Severity Engine with Context Modifiers.
===========================================================================
Assigns issue severity deterministically using:
  RULE_TAXONOMY + AST_CONTEXT_MODIFIERS

Guarantees complete independence from repository identity confounders.
Preserves safety invariant: Zero confirmed High/Critical issues inverted to Low.
"""
from __future__ import annotations

import re
from typing import Any, Dict

CANONICAL_RULE_SEVERITY_MAP: Dict[str, str] = {
    "JAVA_EQ_001": "HIGH",
    "JAVA_DIV_001": "MEDIUM",
    "JAVA_EXC_001": "HIGH",
    "JAVA_RES_001": "HIGH",
    "JAVA_INF_001": "CRITICAL",
    "PY_DIV_001": "MEDIUM",
    "PY_ASS_001": "MEDIUM",
    "PY_MUT_001": "HIGH",
    "PY_RES_001": "MEDIUM",
    "PY_EXC_001": "HIGH",
    "JS_EQ_001": "MEDIUM",
    "JS_DIV_001": "MEDIUM",
    "JS_AWA_001": "HIGH",
}

SEVERITY_ORDINAL: Dict[str, int] = {
    "LOW": 0,
    "MEDIUM": 1,
    "HIGH": 2,
    "CRITICAL": 3,
}


def predict_production_severity(record: Dict[str, Any]) -> str:
    """
    Predicts production severity using canonical rule taxonomy and contextual modifiers.
    Never relies on repository name or domain identifiers.
    """
    rule_id = str(record.get("rule_id", "UNKNOWN")).strip()
    snip = str(record.get("code_snippet") or record.get("snippet") or "").lower()
    base_sev = CANONICAL_RULE_SEVERITY_MAP.get(rule_id, "MEDIUM")

    # Contextual AST Modifiers
    if rule_id == "PY_ASS_001" and any(k in snip for k in ["auth", "security", "token", "password", "role"]):
        return "HIGH"
    if rule_id == "JAVA_EXC_001" and any(k in snip for k in ["interrupted", "cleanup", "close"]):
        return "MEDIUM"
    if rule_id == "JS_EQ_001" and any(k in snip for k in ["id", "status", "type", "role"]):
        return "HIGH"

    return base_sev
