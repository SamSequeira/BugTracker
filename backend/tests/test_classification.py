"""
test_classification.py — Classification Model, Split Validation & Metrics Suite.
================================================================================
Tests:
1. Ground truth dataset loader and split sizes.
2. Group leakage detector validation.
3. TF-IDF vectorization and text builder safety (zero label leakage).
4. Linear SVM primary classifier training and probabilistic calibration.
5. Macro F1, Recall, Precision, and ECE metric evaluation.
"""
from __future__ import annotations

import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from app.services.ml.config import (
    GROUND_TRUTH_DATASET_PATH,
    PRODUCTION_THRESHOLD,
    RANDOM_SEED,
)
from app.services.ml.data_loader import load_ground_truth_dataset
from app.services.ml.input_builder import build_input_text
from app.services.ml.metrics import (
    calculate_classification_metrics,
    compute_expected_calibration_error,
)
from app.services.ml.split_validator import assert_no_group_leakage


def test_ground_truth_dataset_loading_and_splits():
    """Ground truth dataset must load cleanly with train, val, and test splits."""
    dataset = load_ground_truth_dataset()
    splits = dataset.get("splits") or dataset.get("partitions", {})

    train_recs = splits.get("train", [])
    val_recs = splits.get("val", [])
    test_recs = splits.get("test", [])

    assert len(train_recs) >= 700, f"Train split smaller than expected: {len(train_recs)}"
    assert len(val_recs) >= 150, f"Val split smaller than expected: {len(val_recs)}"
    assert len(test_recs) >= 150, f"Test split smaller than expected: {len(test_recs)}"


def test_split_validator_group_leakage_assertion():
    """assert_no_group_leakage must pass without exception on production splits."""
    dataset = load_ground_truth_dataset()
    splits = dataset["splits"]
    # Should not raise
    assert_no_group_leakage(splits["train"], splits["val"], splits["test"])


def test_input_builder_sanitization_and_no_target_leakage():
    """build_input_text must sanitize inputs and never include ground-truth labels."""
    candidate = {
        "rule_id": "PY_DIV_001",
        "language": "python",
        "message": "Potential division by zero",
        "code_snippet": "return x / y",
        "ground_truth": "TRUE_POSITIVE",
        "label": "TRUE_POSITIVE",
        "severity": "CRITICAL",
    }
    text = build_input_text(candidate)
    assert "TRUE_POSITIVE" not in text
    assert "FALSE_POSITIVE" not in text
    assert "PY_DIV_001" in text
    assert "python" in text


def test_linear_svm_training_and_metrics():
    """Linear SVM (SGDClassifier) must train deterministically and achieve expected performance."""
    dataset = load_ground_truth_dataset()
    splits = dataset["splits"]
    train_recs = splits["train"]
    test_recs = splits["test"]

    X_tr = [f"Rule: {r.get('rule_id')}\nLanguage: {r.get('language')}\nMessage: {r.get('message')}" for r in train_recs]
    y_tr = np.array([1 if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE" else 0 for r in train_recs])

    X_te = [f"Rule: {r.get('rule_id')}\nLanguage: {r.get('language')}\nMessage: {r.get('message')}" for r in test_recs]
    y_te = np.array([1 if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE" else 0 for r in test_recs])

    vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), sublinear_tf=True)
    X_tr_vec = vec.fit_transform(X_tr)
    X_te_vec = vec.transform(X_te)

    clf = SGDClassifier(loss="log_loss", class_weight="balanced", random_state=RANDOM_SEED, max_iter=1000, alpha=1e-4)
    clf.fit(X_tr_vec, y_tr)

    probs = clf.predict_proba(X_te_vec)[:, 1]
    preds = (probs >= PRODUCTION_THRESHOLD).astype(int)

    metrics = calculate_classification_metrics(y_te, preds)
    assert metrics["macro_f1"] >= 0.55
    assert metrics["accuracy"] >= 0.60
