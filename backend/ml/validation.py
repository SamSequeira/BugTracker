"""
validation.py — Production Model Cross-Validation & Generalization Audit.
========================================================================
Runs Leave-One-Repository-Out (LORO) cross-validation on canonical ground-truth data,
reporting per-class, per-repository, and aggregate metrics.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier
from sklearn.metrics import classification_report, confusion_matrix

from app.services.ml.config import (
    PRODUCTION_THRESHOLD,
    RANDOM_SEED,
)
from app.services.ml.data_loader import load_ground_truth_dataset, prepare_validity_data
from app.services.ml.metrics import calculate_classification_metrics

logger = logging.getLogger(__name__)


def run_loro_cross_validation(verbose: bool = True) -> Dict[str, Any]:
    """Runs Leave-One-Repository-Out cross-validation across all repositories in the ground truth dataset."""
    dataset = load_ground_truth_dataset()
    splits = dataset.get("splits") or dataset.get("partitions", {})
    all_recs = splits.get("train", []) + splits.get("val", []) + splits.get("test", [])

    repos = sorted(list(set(r.get("repository", "unknown") for r in all_recs if r.get("repository"))))
    if verbose:
        print(f"Running LORO Cross-Validation across {len(repos)} repositories...")

    fold_metrics = []
    all_y_true = []
    all_y_pred = []
    all_y_probs = []

    for repo in repos:
        tr_recs = [r for r in all_recs if r.get("repository") != repo]
        te_recs = [r for r in all_recs if r.get("repository") == repo]

        if not te_recs:
            continue

        X_tr, y_tr, _ = prepare_validity_data(tr_recs)
        X_te, y_te, _ = prepare_validity_data(te_recs)

        if len(set(y_tr)) < 2 or len(set(y_te)) < 1:
            continue

        vec = TfidfVectorizer(max_features=5000, ngram_range=(1, 2), sublinear_tf=True, token_pattern=r'(?u)\b\w+\b|[^\w\s]')
        X_tr_v = vec.fit_transform(X_tr)
        X_te_v = vec.transform(X_te)

        clf = SGDClassifier(loss="log_loss", class_weight="balanced", random_state=RANDOM_SEED, max_iter=1000, alpha=1e-4)
        clf.fit(X_tr_v, y_tr)

        probs = clf.predict_proba(X_te_v)[:, 1]
        preds = (probs >= PRODUCTION_THRESHOLD).astype(int)

        m = calculate_classification_metrics(y_te, preds, y_probs=probs, target_names=["FALSE_POSITIVE", "TRUE_POSITIVE"])
        fold_metrics.append({
            "repository": repo,
            "n_samples": len(te_recs),
            "macro_f1": m["macro_f1"],
            "accuracy": m["accuracy"],
            "macro_precision": m["macro_precision"],
            "macro_recall": m["macro_recall"],
            "weighted_f1": m["weighted_f1"],
        })
        all_y_true.extend(y_te)
        all_y_pred.extend(preds)
        all_y_probs.extend(probs)

        if verbose:
            print(f"  Repo [{repo:25s}] N={len(te_recs):3d} | Macro F1: {m['macro_f1']:.4f} | Acc: {m['accuracy']:.4f}")

    mean_f1 = float(np.mean([f["macro_f1"] for f in fold_metrics]))
    mean_acc = float(np.mean([f["accuracy"] for f in fold_metrics]))
    
    # Global pooled unseen metrics
    global_metrics = calculate_classification_metrics(all_y_true, all_y_pred, y_probs=all_y_probs, target_names=["FALSE_POSITIVE", "TRUE_POSITIVE"])
    cm = confusion_matrix(all_y_true, all_y_pred, labels=[0, 1])

    if verbose:
        print("\n=======================================================")
        print(f"Mean Unseen Repository Macro F1: {mean_f1:.4f}")
        print(f"Mean Unseen Repository Accuracy: {mean_acc:.4f}")
        print(f"Global Pooled Macro F1:         {global_metrics['macro_f1']:.4f}")
        print(f"Global Pooled Accuracy:         {global_metrics['accuracy']:.4f}")
        print(f"Global Pooled Macro Precision:  {global_metrics['macro_precision']:.4f}")
        print(f"Global Pooled Macro Recall:     {global_metrics['macro_recall']:.4f}")
        print(f"Global Pooled Weighted F1:      {global_metrics['weighted_f1']:.4f}")
        print(f"Global Pooled ECE:              {global_metrics.get('ece', 0.0):.4f}")
        print("\nPer-Class Breakdown:")
        for cls_name, cls_stats in global_metrics.get("per_class", {}).items():
            print(f"  {cls_name:15s} -> Precision: {cls_stats['precision']:.4f}, Recall: {cls_stats['recall']:.4f}, F1: {cls_stats['f1']:.4f}, Support: {cls_stats['support']}")
        print("\nPooled Confusion Matrix [TN, FP / FN, TP]:")
        print(cm)
        print("=======================================================\n")

    return {
        "status": "SUCCESS",
        "mean_loro_f1": mean_f1,
        "mean_loro_acc": mean_acc,
        "global_metrics": global_metrics,
        "confusion_matrix": cm.tolist(),
        "folds": fold_metrics,
    }


if __name__ == "__main__":
    run_loro_cross_validation()
