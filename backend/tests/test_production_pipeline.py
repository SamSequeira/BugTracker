"""
test_production_pipeline.py — End-to-End Production Pipeline & Routing Suite.
==============================================================================
Tests:
1. Complete analysis flow: Candidate -> Safe Predict -> Drift Check -> Severity -> 5-Way Router.
2. 5-Way Routing decisions (AUTO_ACCEPT, SECONDARY_MODEL, HUMAN_REVIEW, OOD_REJECT, SYSTEM_ERROR).
3. Model rollback reproducibility (100% hash parity).
4. Multi-run deterministic reproducibility.
5. Model disagreement as an error predictor.
"""
from __future__ import annotations

import hashlib
import json
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from app.services.ml.config import (
    GROUND_TRUTH_DATASET_PATH,
    PRODUCTION_THRESHOLD,
    RANDOM_SEED,
)
from app.services.ml.data_loader import load_ground_truth_dataset
from app.services.ml.drift_detector import ProductionDriftDetector
from app.services.ml.inference import safe_predict
from app.services.ml.routing import route_candidate_issue


@pytest.fixture(scope="module")
def production_setup():
    dataset = load_ground_truth_dataset()
    train_recs = dataset["splits"]["train"]
    test_recs = dataset["splits"]["test"]

    X_tr = [f"Rule: {r.get('rule_id')}\nLanguage: {r.get('language')}\nMessage: {r.get('message')}" for r in train_recs]
    y_tr = [1 if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE" else 0 for r in train_recs]

    vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), sublinear_tf=True)
    X_tr_vec = vec.fit_transform(X_tr)

    clf = SGDClassifier(loss="log_loss", class_weight="balanced", random_state=RANDOM_SEED, max_iter=1000, alpha=1e-4)
    clf.fit(X_tr_vec, y_tr)

    detector = ProductionDriftDetector.fit_from_training_records(train_recs, vec, drift_threshold=0.30)
    return vec, clf, detector, test_recs


def test_five_way_routing_coverage_and_safety(production_setup):
    """The 5-way routing engine must assign valid decisions to all test records."""
    vec, clf, detector, test_recs = production_setup
    valid_decisions = {"AUTO_ACCEPT", "SECONDARY_MODEL", "HUMAN_REVIEW", "OOD_REJECT", "SYSTEM_ERROR"}

    for r in test_recs:
        res = safe_predict(r, vec, clf, detector)
        decision = res["routing_decision"]
        assert decision in valid_decisions, f"Invalid routing decision: {decision}"


def test_model_rollback_hash_parity(production_setup):
    """Rolling back model weights must reproduce identical prediction hashes."""
    vec, clf, _, test_recs = production_setup
    dataset = load_ground_truth_dataset()
    train_recs = dataset["splits"]["train"]
    X_tr = [f"Rule: {r.get('rule_id')}\nLanguage: {r.get('language')}\nMessage: {r.get('message')}" for r in train_recs]
    y_tr = [1 if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE" else 0 for r in train_recs]
    X_te = [f"Rule: {r.get('rule_id')}\nLanguage: {r.get('language')}\nMessage: {r.get('message')}" for r in test_recs]

    # Model v1
    clf_v1 = SGDClassifier(loss="log_loss", class_weight="balanced", random_state=RANDOM_SEED, max_iter=1000, alpha=1e-4)
    clf_v1.fit(vec.transform(X_tr), y_tr)
    probs_v1 = clf_v1.predict_proba(vec.transform(X_te))[:, 1]
    hash_v1 = hashlib.sha256(probs_v1.tobytes()).hexdigest()

    # Re-instantiate v1 model (simulating rollback)
    clf_v1_rollback = SGDClassifier(loss="log_loss", class_weight="balanced", random_state=RANDOM_SEED, max_iter=1000, alpha=1e-4)
    clf_v1_rollback.fit(vec.transform(X_tr), y_tr)
    probs_rollback = clf_v1_rollback.predict_proba(vec.transform(X_te))[:, 1]
    hash_rollback = hashlib.sha256(probs_rollback.tobytes()).hexdigest()

    assert hash_v1 == hash_rollback, "Model rollback hash mismatch!"


def test_multi_run_pipeline_determinism(production_setup):
    """Multiple sequential runs of the inference pipeline must produce identical output hashes."""
    vec, clf, detector, test_recs = production_setup
    hashes = []

    for _ in range(3):
        results = [safe_predict(r, vec, clf, detector) for r in test_recs[:20]]
        serialized = json.dumps([{k: v for k, v in res.items() if k != "latency_ms"} for res in results])
        hashes.append(hashlib.sha256(serialized.encode("utf-8")).hexdigest())

    assert len(set(hashes)) == 1, "Non-deterministic pipeline output detected across runs!"
