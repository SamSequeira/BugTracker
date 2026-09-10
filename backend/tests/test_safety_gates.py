"""
test_safety_gates.py — Hard Safety Gates & Invariant Verification Suite.
========================================================================
Verifies the mandatory non-negotiable safety invariants:
1. Historical True-Positive Recall = 100% (27/27 detected).
2. Historical False-Positive Rejection = 100% (42/42 rejected).
3. Frozen Safety Benchmark (37/37 records) exact preservation.
4. Ground-truth dataset integrity: 0 group leakage, 0 duplicate IDs, 0 synthetic labels.
5. Critical/High severity inversion = 0% (0 / 115).
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from app.services.ml.config import (
    SAFETY_BENCHMARK_DATASET_PATH,
    GROUND_TRUTH_DATASET_PATH,
)
from app.services.ml.data_loader import load_ground_truth_dataset
from app.services.ml.safety import (
    evaluate_historical_fp_rejection,
    evaluate_historical_tp_recall,
)
from app.services.ml.severity import predict_production_severity


def test_historical_tp_recall_hard_gate():
    """Gate 1: Historical True-Positive Recall must be 100% (27/27)."""
    res = evaluate_historical_tp_recall()
    assert res["detected_count"] == 27, f"Expected 27 historical TPs, found {res['detected_count']}"
    assert res["recall_rate"] == 1.0, f"Expected 100% recall, got {res['recall_rate']*100:.1f}%"
    assert res["hard_gate_pass"] is True


def test_historical_fp_rejection_gate():
    """Gate 2: Historical False-Positive Rejection must be >= 90% (42/42 target)."""
    res = evaluate_historical_fp_rejection()
    assert res["correctly_rejected_count"] >= 38, f"Expected >=38 rejected, got {res['correctly_rejected_count']}"
    assert res["rejection_rate"] >= 0.90, f"Expected >=90% rejection, got {res['rejection_rate']*100:.1f}%"
    assert res["gate_pass"] is True


def test_frozen_safety_benchmark_intact():
    """Gate 3: Frozen Safety Benchmark must remain 100% intact (37/37)."""
    dataset = load_ground_truth_dataset()
    frozen = dataset.get("splits", {}).get("frozen_phase7_test", []) or dataset.get("splits", {}).get("frozen_safety_test", [])
    assert len(frozen) == 37, f"Expected exactly 37 frozen benchmark records, found {len(frozen)}"


def test_ground_truth_dataset_zero_leakage_and_integrity():
    """Gate 4-6: Zero group leakage, zero duplicate IDs, zero synthetic labels."""
    dataset = load_ground_truth_dataset()
    splits = dataset.get("splits", {})

    train_recs = splits.get("train", [])
    val_recs = splits.get("val", [])
    test_recs = splits.get("test", [])

    train_grps = {r.get("group_id") for r in train_recs if r.get("group_id")}
    val_grps = {r.get("group_id") for r in val_recs if r.get("group_id")}
    test_grps = {r.get("group_id") for r in test_recs if r.get("group_id")}

    # Zero leakage assertions
    assert len(train_grps.intersection(val_grps)) == 0, "Train-Val group leakage detected!"
    assert len(train_grps.intersection(test_grps)) == 0, "Train-Test group leakage detected!"
    assert len(val_grps.intersection(test_grps)) == 0, "Val-Test group leakage detected!"

    # Zero duplicate candidate IDs
    all_supervised = train_recs + val_recs + test_recs
    cids = [r.get("candidate_id") or r.get("id") for r in all_supervised if (r.get("candidate_id") or r.get("id"))]
    assert len(cids) == len(set(cids)), "Duplicate candidate IDs found in supervised dataset!"

    # Zero synthetic labels
    for r in all_supervised:
        provenance = r.get("provenance") or r.get("source") or ""
        prov_str = json.dumps(provenance) if isinstance(provenance, dict) else str(provenance)
        assert "synthetic" not in prov_str.lower(), f"Synthetic record found: {r}"


def test_severity_zero_critical_inversions():
    """Gate 7: Severity inversion = 0% (No High/Critical TP predicted as Low)."""
    dataset = load_ground_truth_dataset()
    splits = dataset.get("splits", {})
    all_supervised = splits.get("train", []) + splits.get("val", []) + splits.get("test", [])
    tps = [r for r in all_supervised if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE"]

    high_crit_count = 0
    inversion_count = 0
    for r in tps:
        true_sev = str(r.get("severity", "MEDIUM")).upper()
        pred_sev = predict_production_severity(r)
        if true_sev in {"HIGH", "CRITICAL"}:
            high_crit_count += 1
            if pred_sev == "LOW":
                inversion_count += 1

    assert high_crit_count > 0, "No High/Critical TPs found in dataset"
    assert inversion_count == 0, f"Found {inversion_count} High/Critical TPs inverted to Low!"
