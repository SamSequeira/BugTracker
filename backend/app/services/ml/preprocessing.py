"""
preprocessing.py — Label transformations and priority mapping.
==============================================================
Provides deterministic mappings for severity and priority, and
consolidated impact transformations for experimental evaluation.
"""
from __future__ import annotations

from typing import Dict, Optional


def severity_to_priority(severity: Optional[str]) -> Optional[str]:
    """
    Deterministic downstream mapping from severity to priority (1-to-1 diagonal mapping).
    """
    if not severity:
        return None
    mapping = {
        "high": "p1",
        "medium": "p2",
        "low": "p3",
    }
    return mapping.get(severity.lower())


def consolidate_severity(severity: Optional[str]) -> Optional[str]:
    """
    Consolidates 3-class severity into binary impact for Configuration B.
    
    high         -> HIGH_IMPACT
    medium + low -> LOWER_IMPACT
    """
    if not severity:
        return None
    sev = severity.lower()
    if sev == "high":
        return "HIGH_IMPACT"
    if sev in ("medium", "low"):
        return "LOWER_IMPACT"
    return None
