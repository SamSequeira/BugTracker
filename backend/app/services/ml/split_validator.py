"""
split_validator.py — Independent Dataset & Split Verification Service.
======================================================================
Validates canonical dataset partitions, asserts zero cross-split group leakage,
checks exact duplicate isolation, and evaluates label distributions.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from .config import SAFETY_BENCHMARK_DATASET_PATH, GROUND_TRUTH_DATASET_PATH


def assert_no_group_leakage(train_records: List[Dict[str, Any]], val_records: List[Dict[str, Any]], test_records: List[Dict[str, Any]]) -> None:
    """Asserts zero cross-split group leakage across train, val, and test splits."""
    train_groups = set(r["group_id"] for r in train_records if "group_id" in r)
    val_groups = set(r["group_id"] for r in val_records if "group_id" in r)
    test_groups = set(r["group_id"] for r in test_records if "group_id" in r)

    assert not train_groups.intersection(val_groups), f"Train-Val group leakage: {train_groups.intersection(val_groups)}"
    assert not train_groups.intersection(test_groups), f"Train-Test group leakage: {train_groups.intersection(test_groups)}"
    assert not val_groups.intersection(test_groups), f"Val-Test group leakage: {val_groups.intersection(test_groups)}"


def validate_splits(dataset_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Performs rigorous validation of dataset integrity, partition sizes,
    and cross-split group isolation.
    """
    splits = dataset_payload.get("splits", {})
    train_records = splits.get("train", [])
    val_records = splits.get("val", [])
    test_records = splits.get("test", [])

    total_supervised = len(train_records) + len(val_records) + len(test_records)
    all_supervised = train_records + val_records + test_records

    # 1. Extract Group IDs and Assert Disjointness
    train_groups = set(r["group_id"] for r in train_records if "group_id" in r)
    val_groups = set(r["group_id"] for r in val_records if "group_id" in r)
    test_groups = set(r["group_id"] for r in test_records if "group_id" in r)

    train_val_overlap = train_groups.intersection(val_groups)
    train_test_overlap = train_groups.intersection(test_groups)
    val_test_overlap = val_groups.intersection(test_groups)

    assert not train_val_overlap, f"Train and Validation share groups: {train_val_overlap}"
    assert not train_test_overlap, f"Train and Test share groups: {train_test_overlap}"
    assert not val_test_overlap, f"Validation and Test share groups: {val_test_overlap}"

    # 2. Exact Duplicate Cross-Split Validation
    def _sig(r: Dict[str, Any]) -> str:
        return f"{r.get('repository')}::{r.get('rule_id')}::{r.get('file_path')}::{r.get('line_number')}::{r.get('code_snippet', '').strip()}"

    train_sigs = set(_sig(r) for r in train_records)
    val_sigs = set(_sig(r) for r in val_records)
    test_sigs = set(_sig(r) for r in test_records)

    assert not (train_sigs & val_sigs), "Exact duplicate found between Train and Validation"
    assert not (train_sigs & test_sigs), "Exact duplicate found between Train and Test"
    assert not (val_sigs & test_sigs), "Exact duplicate found between Validation and Test"

    # 3. Supervised Labels Check (Only TP and FP allowed in supervised splits)
    for split_name, recs in [("train", train_records), ("val", val_records), ("test", test_records)]:
        for r in recs:
            gt = r.get("ground_truth") or r.get("label")
            assert gt in ("TRUE_POSITIVE", "FALSE_POSITIVE"), f"Invalid ground-truth '{gt}' in {split_name} split!"

    # 4. Calculate Distributions
    label_dist = Counter(r.get("ground_truth") or r.get("label") for r in all_supervised)
    tp_recs = [r for r in all_supervised if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE"]
    sev_dist = Counter(r.get("severity") or "unknown" for r in tp_recs)
    prio_dist = Counter(r.get("priority") or "unknown" for r in tp_recs)
    lang_dist = Counter(r.get("language") or "unknown" for r in all_supervised)
    repo_dist = Counter(r.get("repository") or "unknown" for r in all_supervised)
    rule_dist = Counter(r.get("rule_id") or "unknown" for r in all_supervised)

    report_payload = {
        "status": "PASS",
        "dataset_version": dataset_payload.get("metadata", {}).get("version", "canonical_v1"),
        "total_supervised_records": total_supervised,
        "split_sizes": {
            "train": len(train_records),
            "validation": len(val_records),
            "test": len(test_records),
        },
        "group_counts": {
            "train_groups": len(train_groups),
            "validation_groups": len(val_groups),
            "test_groups": len(test_groups),
        },
        "leakage_checks": {
            "train_val_overlap_count": len(train_val_overlap),
            "train_test_overlap_count": len(train_test_overlap),
            "val_test_overlap_count": len(val_test_overlap),
            "cross_split_group_leakage": False,
            "exact_duplicate_cross_split_leakage": False,
        },
        "label_distribution": dict(label_dist),
        "severity_distribution_true_positives": dict(sev_dist),
        "priority_distribution_true_positives": dict(prio_dist),
        "language_distribution": dict(lang_dist),
        "repository_distribution": dict(repo_dist),
        "rule_distribution": dict(rule_dist),
    }

    return report_payload
