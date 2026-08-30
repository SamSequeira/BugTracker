"""
validator.py — Dataset Quality Validation, Label Integrity & Provenance Checking.
==================================================================================
Validates candidate issues for DistilBERT training, checks for label correctness,
classifies record provenance (REAL_USABLE, REAL_INCOMPLETE, TEST_OR_SYNTHETIC, UNKNOWN),
monitors missing metadata fields, and analyzes class distributions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


SEVERITY_LABELS: List[str] = ["critical", "high", "medium", "low"]
PRIORITY_LABELS: List[str] = ["p1", "p2", "p3", "p4"]

SEVERITY_TO_ID: Dict[str, int] = {label: idx for idx, label in enumerate(SEVERITY_LABELS)}
ID_TO_SEVERITY: Dict[int, str] = {idx: label for idx, label in enumerate(SEVERITY_LABELS)}

PRIORITY_TO_ID: Dict[str, int] = {label: idx for idx, label in enumerate(PRIORITY_LABELS)}
ID_TO_PRIORITY: Dict[int, str] = {idx: label for idx, label in enumerate(PRIORITY_LABELS)}

TEST_MARKERS = [
    "pg-", "prep_", "test_", "api-issue-", "mock_", "seed_",
    "pg_module_", "test.py", "q1.py", "q2.py", "q3.py",
    "duplicate_target.py", "src/file_", "src/part.py", "src/unverif.py"
]


def classify_provenance(record: Dict[str, Any]) -> str:
    """
    Classify a record's provenance into:
      - 'TEST_OR_SYNTHETIC'
      - 'REAL_INCOMPLETE'
      - 'REAL_USABLE'
      - 'UNKNOWN'
    """
    rec_id = str(record.get("id") or "").lower()
    run_id = str(record.get("analysis_run_id") or "").lower()
    file_path = str(record.get("file_path") or "").lower()
    title = str(record.get("title") or "").lower()

    # Check for test fixture markers
    is_test = any(
        m in rec_id or m in run_id or m in file_path or m in title
        for m in TEST_MARKERS
    )
    if is_test:
        return "TEST_OR_SYNTHETIC"

    code_snippet = str(record.get("code_snippet") or "").strip()
    rule_id = str(record.get("rule_id") or "").strip()
    issue_type = str(record.get("issue_type") or "").strip()
    file_p = str(record.get("file_path") or "").strip()

    if not code_snippet or not rule_id or not issue_type or not file_p:
        return "REAL_INCOMPLETE"

    return "REAL_USABLE"


def compute_distribution(labels: List[str], allowed_classes: List[str]) -> Dict[str, Dict[str, Any]]:
    """Compute count and percentage distribution for a list of class labels."""
    total = len(labels)
    dist = {}
    for c in allowed_classes:
        count = labels.count(c)
        pct = round((count / total * 100.0), 2) if total > 0 else 0.0
        dist[c] = {"count": count, "percentage": pct}
    return dist


class DatasetValidator:
    """Validates raw verified records retrieved from PostgreSQL before ML preparation."""

    def __init__(
        self,
        min_samples_per_class: int = 1,
        exclude_test_synthetic: bool = True,
    ) -> None:
        self.min_samples_per_class = min_samples_per_class
        self.exclude_test_synthetic = exclude_test_synthetic

    def validate_records(
        self, records: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Validate a list of candidate issue records and classify provenance.
        Returns:
          (valid_records, validation_report)
        """
        valid_records: List[Dict[str, Any]] = []
        invalid_records: List[Dict[str, Any]] = []
        errors: List[str] = []
        warnings: List[Dict[str, Any]] = []

        provenance_counts = {
            "real_usable": 0,
            "real_incomplete": 0,
            "test_or_synthetic": 0,
            "unknown": 0,
        }

        missing_fields_counts = {
            "missing_code_snippet": 0,
            "missing_message": 0,
            "missing_rule_id": 0,
            "missing_issue_type": 0,
            "missing_language": 0,
            "missing_file_path": 0,
        }

        severity_list: List[str] = []
        priority_list: List[str] = []

        for idx, rec in enumerate(records):
            rec_id = str(rec.get("id") or f"row_{idx}")

            # Classify Provenance
            prov = classify_provenance(rec)
            if prov == "REAL_USABLE":
                provenance_counts["real_usable"] += 1
            elif prov == "REAL_INCOMPLETE":
                provenance_counts["real_incomplete"] += 1
            elif prov == "TEST_OR_SYNTHETIC":
                provenance_counts["test_or_synthetic"] += 1
            else:
                provenance_counts["unknown"] += 1

            # If configured to filter out test/synthetic, skip
            if self.exclude_test_synthetic and prov == "TEST_OR_SYNTHETIC":
                invalid_records.append(rec)
                continue

            # 1. Check ground-truth severity
            sev = str(rec.get("verified_severity") or rec.get("severity") or "").strip().lower()
            prio = str(rec.get("verified_priority") or rec.get("priority") or "").strip().lower()

            if not sev or sev not in SEVERITY_TO_ID:
                invalid_records.append(rec)
                errors.append(f"Record '{rec_id}' has invalid/missing verified_severity: '{sev}'")
                continue

            if not prio or prio not in PRIORITY_TO_ID:
                invalid_records.append(rec)
                errors.append(f"Record '{rec_id}' has invalid/missing verified_priority: '{prio}'")
                continue

            # Check missingness of context fields
            if not rec.get("code_snippet"):
                missing_fields_counts["missing_code_snippet"] += 1
            if not rec.get("message") and not rec.get("description"):
                missing_fields_counts["missing_message"] += 1
            if not rec.get("rule_id"):
                missing_fields_counts["missing_rule_id"] += 1
            if not rec.get("issue_type"):
                missing_fields_counts["missing_issue_type"] += 1
            if not rec.get("language"):
                missing_fields_counts["missing_language"] += 1
            if not rec.get("file_path"):
                missing_fields_counts["missing_file_path"] += 1

            severity_list.append(sev)
            priority_list.append(prio)
            rec["provenance"] = prov
            valid_records.append(rec)

        # Compute distributions
        sev_dist = compute_distribution(severity_list, SEVERITY_LABELS)
        prio_dist = compute_distribution(priority_list, PRIORITY_LABELS)

        # Check for class imbalance & sparse classes
        for sev, data in sev_dist.items():
            if data["count"] < self.min_samples_per_class:
                warnings.append({
                    "type": "sparse_class",
                    "target": "severity",
                    "label": sev,
                    "count": data["count"],
                    "message": f"Severity '{sev}' has {data['count']} samples (< {self.min_samples_per_class} required).",
                })

        for prio, data in prio_dist.items():
            if data["count"] < self.min_samples_per_class:
                warnings.append({
                    "type": "sparse_class",
                    "target": "priority",
                    "label": prio,
                    "count": data["count"],
                    "message": f"Priority '{prio}' has {data['count']} samples (< {self.min_samples_per_class} required).",
                })

        status = "valid"
        if errors:
            status = "invalid" if len(valid_records) == 0 else "valid_with_errors"
        elif warnings:
            status = "valid_with_warnings"

        report = {
            "status": status,
            "total_input_records": len(records),
            "valid_records_count": len(valid_records),
            "invalid_records_count": len(invalid_records),
            "provenance_breakdown": provenance_counts,
            "missingness_statistics": missing_fields_counts,
            "severity_distribution": sev_dist,
            "priority_distribution": prio_dist,
            "warnings": warnings,
            "errors": errors,
        }

        return valid_records, report
