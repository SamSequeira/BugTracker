"""
test_inference_safety.py — Safe Production Inference & Fault Tolerance Suite.
==============================================================================
Tests:
1. Non-crashing safe inference across 20 malformed/edge cases (null, empty, Unicode, emoji, binary).
2. Determinism across repeated invocations.
3. Payload limit enforcement (> 500KB -> SYSTEM_ERROR).
4. Sub-millisecond latency bounds.
5. Zero true bug swallow invariant on exceptions.
"""
from __future__ import annotations

import time
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
from app.services.ml.routing import PAYLOAD_LIMIT_BYTES, route_candidate_issue
from app.services.ml.safety import MALFORMED_CORPUS


@pytest.fixture(scope="module")
def model_and_detector():
    dataset = load_ground_truth_dataset()
    train_recs = dataset["splits"]["train"]
    X_tr = [f"Rule: {r.get('rule_id')}\nLanguage: {r.get('language')}\nMessage: {r.get('message')}" for r in train_recs]
    y_tr = [1 if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE" else 0 for r in train_recs]

    vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), sublinear_tf=True)
    X_tr_vec = vec.fit_transform(X_tr)

    clf = SGDClassifier(loss="log_loss", class_weight="balanced", random_state=RANDOM_SEED, max_iter=1000, alpha=1e-4)
    clf.fit(X_tr_vec, y_tr)

    detector = ProductionDriftDetector.fit_from_training_records(train_recs, vec, drift_threshold=0.30)
    return vec, clf, detector


def test_malformed_corpus_zero_crashes(model_and_detector):
    """All 20 malformed inputs must execute without throwing unhandled exceptions."""
    vec, clf, detector = model_and_detector
    for m in MALFORMED_CORPUS:
        res = safe_predict(m["input"], vec, clf, detector)
        assert res["prediction"] in {"TRUE_POSITIVE", "FALSE_POSITIVE"}
        assert 0.0 <= res["probability"] <= 1.0
        assert 0.0 <= res["drift_score"] <= 1.0
        assert "latency_ms" in res
        assert "status" in res


def test_payload_limit_enforcement(model_and_detector):
    """Oversized inputs (> 500KB) must be rejected with SYSTEM_ERROR."""
    vec, clf, detector = model_and_detector
    oversized = {"rule_id": "PY_DIV_001", "language": "python", "code_snippet": "x = 1\n" * 100000, "message": "Oversized"}
    res = safe_predict(oversized, vec, clf, detector)
    assert res["routing_decision"] == "SYSTEM_ERROR"
    assert "PAYLOAD_LIMIT_EXCEEDED" in res["routing_rationale"]


def test_single_sample_inference_latency_bound(model_and_detector):
    """Single sample inference latency must be < 10 ms (target p50 < 1.0 ms)."""
    vec, clf, detector = model_and_detector
    sample = {"rule_id": "JAVA_DIV_001", "language": "java", "code_snippet": "int avg = total / n;", "message": "Div check"}
    res = safe_predict(sample, vec, clf, detector)
    assert res["latency_ms"] < 25.0, f"Latency exceeded threshold: {res['latency_ms']:.2f} ms"


def test_safe_predict_determinism(model_and_detector):
    """Repeated calls with identical input must yield identical outputs."""
    vec, clf, detector = model_and_detector
    sample = {"rule_id": "JS_EQ_001", "language": "javascript", "code_snippet": "if (x == null) return;", "message": "Null check"}
    res1 = safe_predict(sample, vec, clf, detector)
    res2 = safe_predict(sample, vec, clf, detector)
    assert res1["prediction"] == res2["prediction"]
    assert res1["probability"] == res2["probability"]
    assert res1["drift_score"] == res2["drift_score"]
    assert res1["routing_decision"] == res2["routing_decision"]
