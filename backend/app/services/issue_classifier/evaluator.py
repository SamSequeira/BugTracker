"""
evaluator.py — Independent Multi-Task Evaluation & Under-Classification Metrics.
================================================================================
Calculates Accuracy, Precision, Recall, Macro-F1, Weighted-F1, per-class metrics,
confusion matrices, and specialized under-classification error rates.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)

from .config import (
    ID_TO_PRIORITY,
    ID_TO_SEVERITY,
    PRIORITY_LABELS,
    SEVERITY_LABELS,
    UNDERCLASSIFICATION_PRIORITY_PAIRS,
    UNDERCLASSIFICATION_SEVERITY_PAIRS,
)


class MultiTaskEvaluator:
    """Evaluates multi-task severity and priority predictions."""

    @staticmethod
    def evaluate_task(
        y_true: List[int],
        y_pred: List[int],
        labels: List[str],
        id_to_label: Dict[int, str],
    ) -> Dict[str, Any]:
        """Calculate comprehensive classification metrics for a single task."""
        if len(y_true) == 0:
            return {
                "accuracy": 0.0,
                "macro_f1": 0.0,
                "weighted_f1": 0.0,
                "macro_precision": 0.0,
                "macro_recall": 0.0,
                "per_class": {},
                "confusion_matrix": [],
            }

        acc = accuracy_score(y_true, y_pred)
        macro_f1 = f1_score(y_true, y_pred, average="macro", zero_division=0)
        weighted_f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)
        macro_prec = precision_score(y_true, y_pred, average="macro", zero_division=0)
        macro_rec = recall_score(y_true, y_pred, average="macro", zero_division=0)

        # Per-class P, R, F1, Support
        p_class, r_class, f1_class, support = precision_recall_fscore_support(
            y_true,
            y_pred,
            labels=list(range(len(labels))),
            zero_division=0,
        )

        per_class_metrics = {}
        for idx, label_name in enumerate(labels):
            per_class_metrics[label_name] = {
                "precision": float(p_class[idx]),
                "recall": float(r_class[idx]),
                "f1": float(f1_class[idx]),
                "support": int(support[idx]),
            }

        cm = confusion_matrix(y_true, y_pred, labels=list(range(len(labels))))

        return {
            "accuracy": float(acc),
            "macro_f1": float(macro_f1),
            "weighted_f1": float(weighted_f1),
            "macro_precision": float(macro_prec),
            "macro_recall": float(macro_rec),
            "per_class": per_class_metrics,
            "confusion_matrix": cm.tolist(),
        }

    @staticmethod
    def calculate_underclassifications(
        y_true_sev: List[str],
        y_pred_sev: List[str],
        y_true_prio: List[str],
        y_pred_prio: List[str],
    ) -> Dict[str, Any]:
        """
        Identify and count critical under-classification errors where severe/high-priority
        issues are mistakenly downgraded to low/medium severity or p3/p4 priority.
        """
        sev_errors: Dict[str, int] = {}
        total_sev_under = 0

        for actual, pred in zip(y_true_sev, y_pred_sev):
            pair = (actual, pred)
            if pair in UNDERCLASSIFICATION_SEVERITY_PAIRS:
                key = f"{actual} -> {pred}"
                sev_errors[key] = sev_errors.get(key, 0) + 1
                total_sev_under += 1

        prio_errors: Dict[str, int] = {}
        total_prio_under = 0

        for actual, pred in zip(y_true_prio, y_pred_prio):
            pair = (actual, pred)
            if pair in UNDERCLASSIFICATION_PRIORITY_PAIRS:
                key = f"{actual} -> {pred}"
                prio_errors[key] = prio_errors.get(key, 0) + 1
                total_prio_under += 1

        n = len(y_true_sev)
        return {
            "severity_underclassifications": {
                "counts": sev_errors,
                "total": total_sev_under,
                "rate": (total_sev_under / n) if n > 0 else 0.0,
            },
            "priority_underclassifications": {
                "counts": prio_errors,
                "total": total_prio_under,
                "rate": (total_prio_under / n) if n > 0 else 0.0,
            },
        }

    def evaluate(
        self,
        severity_true: List[int],
        severity_pred: List[int],
        priority_true: List[int],
        priority_pred: List[int],
    ) -> Dict[str, Any]:
        """Compute full multi-task evaluation metrics."""
        sev_metrics = self.evaluate_task(
            severity_true,
            severity_pred,
            SEVERITY_LABELS,
            ID_TO_SEVERITY,
        )

        prio_metrics = self.evaluate_task(
            priority_true,
            priority_pred,
            PRIORITY_LABELS,
            ID_TO_PRIORITY,
        )

        # Labels as string for under-classification check
        y_true_sev_str = [ID_TO_SEVERITY.get(i, "unknown") for i in severity_true]
        y_pred_sev_str = [ID_TO_SEVERITY.get(i, "unknown") for i in severity_pred]
        y_true_prio_str = [ID_TO_PRIORITY.get(i, "unknown") for i in priority_true]
        y_pred_prio_str = [ID_TO_PRIORITY.get(i, "unknown") for i in priority_pred]

        under_metrics = self.calculate_underclassifications(
            y_true_sev_str,
            y_pred_sev_str,
            y_true_prio_str,
            y_pred_prio_str,
        )

        # Primary multi-task comparison score: Mean of Macro F1
        mean_macro_f1 = (sev_metrics["macro_f1"] + prio_metrics["macro_f1"]) / 2.0

        return {
            "mean_macro_f1": float(mean_macro_f1),
            "severity": sev_metrics,
            "priority": prio_metrics,
            "underclassifications": under_metrics,
        }
