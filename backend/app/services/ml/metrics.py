"""
metrics.py — Comprehensive Evaluation Metrics & Calibration Calculators.
=======================================================================
Calculates Accuracy, Precision, Recall, Macro/Weighted F1, Per-Class Metrics,
Confusion Matrices, ROC-AUC, PR-AUC, Brier Score, and Expected Calibration Error (ECE).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def compute_expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    Computes Expected Calibration Error (ECE) across binned confidence intervals.
    """
    if len(y_true) == 0:
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    ece = 0.0
    n_samples = len(y_true)

    for b in range(n_bins):
        mask = bin_indices == b
        bin_count = np.sum(mask)
        if bin_count > 0:
            bin_acc = np.mean(y_true[mask])
            bin_conf = np.mean(y_prob[mask])
            ece += (bin_count / n_samples) * np.abs(bin_acc - bin_conf)

    return float(ece)


def calculate_classification_metrics(
    y_true: Union[List[int], np.ndarray],
    y_pred: Union[List[int], np.ndarray],
    y_probs: Optional[Union[List[float], np.ndarray]] = None,
    target_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Computes full suite of classification and calibration metrics.
    """
    y_t = np.array(y_true, dtype=int)
    y_p = np.array(y_pred, dtype=int)

    acc = float(accuracy_score(y_t, y_p))
    macro_p = float(precision_score(y_t, y_p, average="macro", zero_division=0))
    macro_r = float(recall_score(y_t, y_p, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y_t, y_p, average="macro", zero_division=0))
    weighted_f1 = float(f1_score(y_t, y_p, average="weighted", zero_division=0))

    per_class_p = precision_score(y_t, y_p, average=None, zero_division=0).tolist()
    per_class_r = recall_score(y_t, y_p, average=None, zero_division=0).tolist()
    per_class_f1 = f1_score(y_t, y_p, average=None, zero_division=0).tolist()

    cm = confusion_matrix(y_t, y_p).tolist()

    per_class_dict: Dict[str, Dict[str, float]] = {}
    classes = target_names or [f"class_{i}" for i in range(len(per_class_p))]
    for i, name in enumerate(classes):
        if i < len(per_class_p):
            per_class_dict[name] = {
                "precision": float(per_class_p[i]),
                "recall": float(per_class_r[i]),
                "f1": float(per_class_f1[i]),
                "support": int(np.sum(y_t == i)),
            }

    results: Dict[str, Any] = {
        "accuracy": acc,
        "macro_precision": macro_p,
        "macro_recall": macro_r,
        "macro_f1": macro_f1,
        "weighted_f1": weighted_f1,
        "per_class": per_class_dict,
        "confusion_matrix": cm,
    }

    # Probability & Calibration Metrics
    if y_probs is not None and len(y_probs) == len(y_t):
        probs = np.array(y_probs, dtype=float)
        # Binary case
        if len(classes) == 2:
            if probs.ndim == 2:
                pos_probs = probs[:, 1]
            else:
                pos_probs = probs

            try:
                results["roc_auc"] = float(roc_auc_score(y_t, pos_probs))
            except Exception:
                results["roc_auc"] = None

            try:
                results["pr_auc"] = float(average_precision_score(y_t, pos_probs))
            except Exception:
                results["pr_auc"] = None

            try:
                results["brier_score"] = float(brier_score_loss(y_t, pos_probs))
            except Exception:
                results["brier_score"] = None

            try:
                results["ece"] = compute_expected_calibration_error(y_t, pos_probs)
            except Exception:
                results["ece"] = None

    return results
