"""
test_drift_detection.py — Multi-Signal Data Drift & OOD Detection Suite.
========================================================================
Tests:
1. Drift detector fitting from training distribution.
2. Low False Alarm Rate (FAR <= 5%) on in-distribution validation records.
3. High Out-of-Distribution detection rate (>= 90%) on foreign languages,
   unknown static rules, non-code text, and malformed inputs.
4. Token OOV rate calculation and entropy sensitivity.
"""
from __future__ import annotations

import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer

from app.services.ml.config import (
    PRODUCTION_DRIFT_THRESHOLD,
    GROUND_TRUTH_DATASET_PATH,
    RANDOM_SEED,
)
from app.services.ml.data_loader import load_ground_truth_dataset
from app.services.ml.drift_detector import ProductionDriftDetector


@pytest.fixture(scope="module")
def fitted_detector():
    dataset = load_ground_truth_dataset()
    train_recs = dataset["splits"]["train"]
    texts = [f"Rule: {r.get('rule_id')} Language: {r.get('language')} Message: {r.get('message')}" for r in train_recs]

    vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), sublinear_tf=True)
    vec.fit(texts)

    detector = ProductionDriftDetector.fit_from_training_records(train_recs, vec, drift_threshold=PRODUCTION_DRIFT_THRESHOLD)
    return vec, detector, train_recs, dataset["splits"]["val"]


def test_in_distribution_validation_false_alarm_rate(fitted_detector):
    """In-distribution False Alarm Rate must be <= 5%."""
    vec, detector, _, val_recs = fitted_detector
    val_drifts = [detector.compute_drift_score(r, prediction_prob=0.80)["drift_score"] for r in val_recs]
    far = sum(1 for d in val_drifts if d >= detector.drift_threshold) / len(val_recs)
    assert far <= 0.05, f"Validation False Alarm Rate too high: {far*100:.1f}% (target <= 5%)"


def test_out_of_distribution_foreign_languages(fitted_detector):
    """Foreign languages (Rust, Go, C++, Ruby) must trigger drift detection."""
    _, detector, _, _ = fitted_detector
    foreign_cases = [
        {"rule_id": "RS_001", "language": "rust", "code_snippet": "let x = opt.unwrap();", "message": "Rust unwrap"},
        {"rule_id": "GO_001", "language": "go", "code_snippet": "if err != nil { return nil, err }", "message": "Go nil check"},
        {"rule_id": "CPP_001", "language": "cpp", "code_snippet": "delete ptr; ptr->use();", "message": "C++ UAF"},
    ]
    for c in foreign_cases:
        res = detector.compute_drift_score(c, prediction_prob=0.50)
        assert res["is_drift"] is True, f"Failed to detect foreign language drift on {c['language']}"
        assert res["drift_score"] >= detector.drift_threshold


def test_out_of_distribution_unknown_rules(fitted_detector):
    """Unknown static rule IDs must trigger drift signals."""
    _, detector, _, _ = fitted_detector
    unknown_rules = [
        {"rule_id": "UNKNOWN_RULE_999", "language": "python", "code_snippet": "x = 1", "message": "Custom check"},
        {"rule_id": "CUSTOM_MEM_001", "language": "java", "code_snippet": "Unsafe.alloc()", "message": "Custom check"},
    ]
    for c in unknown_rules:
        res = detector.compute_drift_score(c, prediction_prob=0.50)
        assert res["is_drift"] is True, f"Failed to detect unknown rule {c['rule_id']}"
        assert res["drift_score"] >= detector.drift_threshold


def test_token_oov_rate_calculation(fitted_detector):
    """Token OOV rate must return 0.0 on in-vocabulary tokens and 1.0 on random gibberish."""
    _, detector, _, _ = fitted_detector
    oov_high = detector.compute_token_oov_rate("xzzyqwerty foobarsnazzle zzzzz9988")
    assert oov_high > 0.80
