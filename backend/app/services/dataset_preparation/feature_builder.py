"""
feature_builder.py — Deterministic DistilBERT text representation and group hashing.
===================================================================================
Constructs structured input text for candidate issues without target label leakage,
serializes evidence deterministically, and generates group IDs for leakage prevention.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional, Union


def serialize_evidence(evidence: Any) -> str:
    """
    Deterministically serialize evidence into a consistent key-sorted string.
    Handles nested dicts, lists, and primitives safely.
    """
    if not evidence or not isinstance(evidence, dict):
        return "None"

    items = []
    for key in sorted(evidence.keys()):
        val = evidence[key]
        if isinstance(val, (dict, list)):
            val_str = json.dumps(val, sort_keys=True)
        else:
            val_str = str(val)
        items.append(f"{key}={val_str}")

    return "; ".join(items) if items else "None"


def generate_group_id(issue: Union[Dict[str, Any], Any]) -> str:
    """
    Generate a deterministic grouping signature to prevent data leakage across splits.
    Groups issues sharing the same rule_id, file_path, and code_snippet.
    """
    if isinstance(issue, dict):
        data = issue
    elif hasattr(issue, "to_dict"):
        data = issue.to_dict()
    else:
        data = getattr(issue, "__dict__", {})

    rule_id = str(data.get("rule_id") or "").strip()
    file_path = str(data.get("file_path") or "").strip()
    code_snippet = str(data.get("code_snippet") or "").strip()

    sig = f"{rule_id}::{file_path}::{code_snippet}"
    group_hash = hashlib.sha256(sig.encode("utf-8")).hexdigest()[:16]
    return f"grp_{group_hash}"


def build_training_text(issue: Union[Dict[str, Any], Any]) -> str:
    """
    Construct a structured, reproducible text representation for DistilBERT input.

    Format:
      Rule ID: <rule_id>
      Issue Type: <issue_type>
      Language: <language>
      File Path: <file_path>
      Message: <message>
      Description: <description>
      Code:
      <code_snippet>
      Evidence:
      <serialized_evidence>

    Safety Guarantees:
      - Does NOT contain verified_severity or verified_priority (prevents label leakage).
      - Does NOT contain detector_severity / severity (prevents detector memorization bias).
    """
    if isinstance(issue, dict):
        data = issue
    elif hasattr(issue, "to_dict"):
        data = issue.to_dict()
    else:
        data = getattr(issue, "__dict__", {})

    rule_id = str(data.get("rule_id") or "").strip() or "Unknown"
    issue_type = str(data.get("issue_type") or "").strip() or "Unknown"
    language = str(data.get("language") or "").strip() or "Unknown"
    file_path = str(data.get("file_path") or "").strip() or "Unknown"
    message = str(data.get("message") or "").strip() or "None"
    description = str(data.get("description") or "").strip() or "None"
    code_snippet = str(data.get("code_snippet") or "").strip() or "None"
    evidence_str = serialize_evidence(data.get("evidence"))

    lines = [
        f"Rule ID: {rule_id}",
        f"Issue Type: {issue_type}",
        f"Language: {language}",
        f"File Path: {file_path}",
        f"Message: {message}",
        f"Description: {description}",
        "Code:",
        code_snippet,
        "Evidence:",
        evidence_str,
    ]

    return "\n".join(lines).strip()
