"""
input_builder.py — Deterministic structured text representation for ML models.
=============================================================================
Transforms candidate issues into standardized text inputs without target leakage.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


def normalize_evidence_dict(evidence: Optional[Dict[str, Any]]) -> str:
    """
    Deterministically serializes evidence dictionary into clean key=value lines.
    Strips IDs, paths, timestamps, and target labels to prevent data leakage.
    """
    if not evidence or not isinstance(evidence, dict):
        return "none"

    forbidden_keys = {
        "id", "candidate_id", "repository_id", "analysis_run_id", "user_id",
        "created_at", "updated_at", "verified_at", "verified_severity",
        "verified_priority", "verification_notes", "ground_truth",
        "false_positive_reason", "target", "label",
    }

    normalized_items = []
    for k in sorted(evidence.keys()):
        k_clean = str(k).strip()
        if k_clean.lower() in forbidden_keys:
            continue

        val = evidence[k]
        if val is None:
            val_str = "null"
        elif isinstance(val, bool):
            val_str = "true" if val else "false"
        elif isinstance(val, (int, float)):
            val_str = str(val)
        elif isinstance(val, (list, tuple, set)):
            val_str = "[" + ", ".join(sorted(str(x) for x in val)) + "]"
        elif isinstance(val, dict):
            sub_kvs = [f"{sk}:{val[sk]}" for sk in sorted(val.keys()) if sk.lower() not in forbidden_keys]
            val_str = "{" + ", ".join(sub_kvs) + "}"
        else:
            val_str = str(val).strip().replace("\n", " ")
            # Strip absolute Windows/Unix paths from values
            val_str = re.sub(r'[A-Za-z]:\\[\w\-\\.]+', '<path>', val_str)
            val_str = re.sub(r'/[\w\-\\.]+', '<path>', val_str)

        normalized_items.append(f"{k_clean}={val_str}")

    return "\n".join(normalized_items) if normalized_items else "none"


def build_input_text(record: Dict[str, Any], representation: str = "structured") -> str:
    """
    Builds input string for transformer/baseline models based on chosen representation format.
    
    Representations:
      - 'rep_a' / 'A': message + code_snippet
      - 'rep_b' / 'B': rule_id + message + code_snippet
      - 'rep_c' / 'C': rule_id + language + confidence + message + code_snippet
      - 'rep_d' / 'D': rule_id + language + message + surrounding_code_context
      - 'structured': full structured text with evidence and issue type
    """
    rule_id = str(record.get("rule_id") or "UNKNOWN").strip()
    language = str(record.get("language") or "Unknown").strip()
    issue_type = str(record.get("issue_type") or "Static Analysis Warning").strip()
    description = str(record.get("message") or record.get("description") or "Potential static analysis issue detected.").strip()
    code_snippet = str(record.get("code_snippet") or "").strip()
    confidence = str(record.get("confidence") or (record.get("evidence") or {}).get("confidence", "medium")).strip()
    surrounding_context = str(record.get("surrounding_context") or code_snippet).strip()

    rep_mode = representation.lower().strip()

    if rep_mode in ("rep_a", "a"):
        return f"{description}\n\n{code_snippet}"

    if rep_mode in ("rep_b", "b"):
        return f"RULE: {rule_id}\nMESSAGE: {description}\nCODE:\n{code_snippet}"

    if rep_mode in ("rep_c", "c"):
        return f"RULE: {rule_id}\nLANGUAGE: {language}\nCONFIDENCE: {confidence}\nMESSAGE: {description}\nCODE:\n{code_snippet}"

    if rep_mode in ("rep_d", "d"):
        return f"RULE: {rule_id}\nLANGUAGE: {language}\nMESSAGE: {description}\nCONTEXT:\n{surrounding_context}"

    # Default: Full structured text
    raw_evidence = record.get("evidence")
    if not isinstance(raw_evidence, dict):
        raw_evidence = {}

    evidence_text = normalize_evidence_dict(raw_evidence)

    text_blocks = [
        f"RULE:\n{rule_id}",
        f"LANGUAGE:\n{language}",
        f"ISSUE TYPE:\n{issue_type}",
        f"DESCRIPTION:\n{description}",
        f"CODE:\n{code_snippet}",
        f"EVIDENCE:\n{evidence_text}",
    ]

    return "\n\n".join(text_blocks)

