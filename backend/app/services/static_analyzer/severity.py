"""
severity.py
-----------
Active repository-scanner severity taxonomy.

The clone/upload static analyzer emits only:
  low | medium | high

High is the highest scanner severity. Incoming "critical" values are
folded into "high" so the scanner never stores or returns a separate
Critical class.
"""

from __future__ import annotations

from typing import Optional

SCANNER_SEVERITIES = ("low", "medium", "high")


def normalize_scanner_severity(severity: Optional[str]) -> str:
    """Map a detector severity onto the active scanner taxonomy."""
    sev = (severity or "medium").strip().lower()
    if sev == "critical":
        return "high"
    if sev in SCANNER_SEVERITIES:
        return sev
    return "medium"
