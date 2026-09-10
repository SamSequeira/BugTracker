"""
train.py — Production ML Model Training Pipeline.
=================================================
Trains and evaluates the production Linear SVM (TF-IDF + SGDClassifier)
and optional DistilBERT validity models on canonical ground-truth data.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from app.services.ml.config import (
    MODELS_DIR,
    PRODUCTION_THRESHOLD,
    RANDOM_SEED,
)
from app.services.ml.data_loader import load_ground_truth_dataset, prepare_validity_data
from app.services.ml.drift_detector import ProductionDriftDetector
from app.services.ml.metrics import calculate_classification_metrics

logger = logging.getLogger(__name__)


def train_production_svm() -> Dict[str, Any]:
    """Trains the primary Linear SVM model and fits the drift detector."""
    dataset = load_ground_truth_dataset()
    splits = dataset.get("splits") or dataset.get("partitions", {})

    train_recs = splits.get("train", [])
    val_recs = splits.get("val", [])
    test_recs = splits.get("test", [])

    X_train, y_train, _ = prepare_validity_data(train_recs)
    X_val, y_val, _ = prepare_validity_data(val_recs)
    X_test, y_test, _ = prepare_validity_data(test_recs)

    # 1. TF-IDF Feature Vectorizer
    vectorizer = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), sublinear_tf=True)
    X_train_vec = vectorizer.fit_transform(X_train)
    X_val_vec = vectorizer.transform(X_val)
    X_test_vec = vectorizer.transform(X_test)

    # 2. Linear SVM with Log-Loss (Probabilistic SGDClassifier)
    classifier = SGDClassifier(
        loss="log_loss",
        class_weight="balanced",
        random_state=RANDOM_SEED,
        max_iter=1000,
        alpha=1e-4,
    )
    classifier.fit(X_train_vec, y_train)

    # 3. Fit Multi-Signal Production Drift Detector
    drift_detector = ProductionDriftDetector.fit_from_training_records(
        train_recs, vectorizer, drift_threshold=0.30
    )

    # 4. Evaluation
    probs_test = classifier.predict_proba(X_test_vec)[:, 1]
    preds_test = (probs_test >= PRODUCTION_THRESHOLD).astype(int)
    test_metrics = calculate_classification_metrics(y_test, preds_test, y_probs=probs_test)

    # 5. Persist Model Artifacts
    validity_dir = MODELS_DIR / "validity"
    validity_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(vectorizer, validity_dir / "vectorizer.joblib")
    joblib.dump(classifier, validity_dir / "classifier.joblib")

    print(f"Production Linear SVM trained successfully. Test Macro F1: {test_metrics['macro_f1']:.4f}")
    return {
        "status": "SUCCESS",
        "test_metrics": test_metrics,
        "model_path": str(validity_dir),
    }


if __name__ == "__main__":
    train_production_svm()
