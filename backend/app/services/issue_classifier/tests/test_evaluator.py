"""
Unit tests for MultiTaskEvaluator and under-classification tracking.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

from app.services.issue_classifier.evaluator import MultiTaskEvaluator


class TestMultiTaskEvaluator(unittest.TestCase):

    def setUp(self):
        self.evaluator = MultiTaskEvaluator()

    def test_perfect_predictions(self):
        y_true_sev = [0, 1, 2, 3]
        y_pred_sev = [0, 1, 2, 3]
        y_true_prio = [0, 1, 2, 3]
        y_pred_prio = [0, 1, 2, 3]

        metrics = self.evaluator.evaluate(y_true_sev, y_pred_sev, y_true_prio, y_pred_prio)

        self.assertEqual(metrics["mean_macro_f1"], 1.0)
        self.assertEqual(metrics["severity"]["accuracy"], 1.0)
        self.assertEqual(metrics["priority"]["accuracy"], 1.0)
        self.assertEqual(metrics["underclassifications"]["severity_underclassifications"]["total"], 0)
        self.assertEqual(metrics["underclassifications"]["priority_underclassifications"]["total"], 0)

    def test_underclassification_tracking(self):
        # 0: critical, 1: high, 2: medium, 3: low
        # 0: p1, 1: p2, 2: p3, 3: p4
        y_true_sev = [0, 0, 1, 3]   # critical, critical, high, low
        y_pred_sev = [3, 2, 3, 0]   # low (under!), medium (under!), low (under!), critical (over)

        y_true_prio = [0, 0, 1, 3]  # p1, p1, p2, p4
        y_pred_prio = [3, 2, 3, 0]  # p4 (under!), p3 (under!), p4 (under!), p1 (over)

        metrics = self.evaluator.evaluate(y_true_sev, y_pred_sev, y_true_prio, y_pred_prio)

        sev_under = metrics["underclassifications"]["severity_underclassifications"]
        prio_under = metrics["underclassifications"]["priority_underclassifications"]

        # Critical -> Low (1), Critical -> Medium (1), High -> Low (1) => 3 total
        self.assertEqual(sev_under["total"], 3)
        self.assertIn("critical -> low", sev_under["counts"])
        self.assertIn("critical -> medium", sev_under["counts"])
        self.assertIn("high -> low", sev_under["counts"])

        # P1 -> P4 (1), P1 -> P3 (1), P2 -> P4 (1) => 3 total
        self.assertEqual(prio_under["total"], 3)
        self.assertIn("p1 -> p4", prio_under["counts"])
        self.assertIn("p1 -> p3", prio_under["counts"])
        self.assertIn("p2 -> p4", prio_under["counts"])


if __name__ == "__main__":
    unittest.main()
