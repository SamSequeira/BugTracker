"""
deduplicator.py — Exact duplicate detection and removal for ML export.
======================================================================
Removes exact duplicate training examples deterministically without modifying PostgreSQL.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def compute_exact_signature(record: Dict[str, Any]) -> str:
    """
    Compute a deterministic hashable signature for exact duplicate identification.
    Uses intrinsic issue properties (repository, rule_id, issue_type, language, file_path, line_number, code_snippet)
    WITHOUT leaking or relying on target ground-truth or detector labels.
    """
    repo = str(record.get("repository") or record.get("repository_id") or record.get("repository_name") or "").strip()
    rule_id = str(record.get("rule_id") or "").strip()
    issue_type = str(record.get("issue_type") or "").strip()
    language = str(record.get("language") or "").strip()
    file_path = str(record.get("file_path") or "").strip()
    line_number = str(record.get("line_number") or "")
    code_snippet = str(record.get("code_snippet") or "").strip()

    if repo:
        return f"{repo}::{rule_id}::{issue_type}::{language}::{file_path}::{line_number}::{code_snippet}"
    return f"{rule_id}::{issue_type}::{language}::{file_path}::{line_number}::{code_snippet}"


class DatasetDeduplicator:
    """Deterministic deduplication of verified records for ML dataset export."""

    def deduplicate(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
        """
        Deduplicate records based on full training signature.
        Returns:
          (unique_records, deduplication_stats)
        """
        seen_signatures = set()
        unique_records: List[Dict[str, Any]] = []
        duplicates_detected = 0

        for r in records:
            sig = compute_exact_signature(r)
            if sig not in seen_signatures:
                seen_signatures.add(sig)
                unique_records.append(r)
            else:
                duplicates_detected += 1

        stats = {
            "total_verified_records": len(records),
            "exact_duplicates_detected": duplicates_detected,
            "records_removed_from_ml_export": duplicates_detected,
            "final_unique_records": len(unique_records),
        }

        return unique_records, stats
