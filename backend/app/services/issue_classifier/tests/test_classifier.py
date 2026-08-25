"""
Unit tests for IssueClassifier inference, probability outputs & thresholding.
"""
from __future__ import annotations

import pathlib
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

import torch

from app.services.issue_classifier.classifier import IssueClassifier
from app.services.issue_classifier.config import InferenceConfig


class TestIssueClassifier(unittest.TestCase):

    def setUp(self):
        self.mock_tokenizer = MagicMock()
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[101, 102], [101, 102]]),
            "attention_mask": torch.tensor([[1, 1], [1, 1]]),
        }

        self.mock_model = MagicMock()
        # Mock batch of 2 outputs:
        # Sample 0: High confidence (0.90 for high, 0.85 for p1)
        # Sample 1: Low confidence (0.40 for medium, 0.45 for p2)
        sev_probs = torch.tensor([
            [0.05, 0.90, 0.04, 0.01],
            [0.20, 0.20, 0.40, 0.20],
        ])
        prio_probs = torch.tensor([
            [0.85, 0.10, 0.03, 0.02],
            [0.25, 0.45, 0.20, 0.10],
        ])
        self.mock_model.return_value = {
            "severity_probabilities": sev_probs,
            "priority_probabilities": prio_probs,
        }

        self.classifier = IssueClassifier(
            config=InferenceConfig(confidence_threshold=0.80, device="cpu"),
            model=self.mock_model,
            tokenizer=self.mock_tokenizer,
        )

    def test_predict_batch_structure_and_thresholding(self):
        issues = [
            {"rule_id": "PY_DIV_001", "message": "Div by zero", "code_snippet": "x / 0"},
            {"rule_id": "JAVA_EQ_001", "message": "String equality", "code_snippet": "a == b"},
        ]

        predictions = self.classifier.predict_batch(issues)

        self.assertEqual(len(predictions), 2)

        # Sample 0: Confident
        pred0 = predictions[0]
        self.assertEqual(pred0["severity"]["label"], "high")
        self.assertAlmostEqual(pred0["severity"]["confidence"], 0.90, places=2)
        self.assertEqual(pred0["priority"]["label"], "p1")
        self.assertAlmostEqual(pred0["priority"]["confidence"], 0.85, places=2)
        self.assertFalse(pred0["needs_review"])  # Confidences >= 0.80

        # Sample 1: Low confidence
        pred1 = predictions[1]
        self.assertEqual(pred1["severity"]["label"], "medium")
        self.assertAlmostEqual(pred1["severity"]["confidence"], 0.40, places=2)
        self.assertEqual(pred1["priority"]["label"], "p2")
        self.assertAlmostEqual(pred1["priority"]["confidence"], 0.45, places=2)
        self.assertTrue(pred1["needs_review"])  # Confidences < 0.80

    def test_enrich_candidate_issue_preserves_fields(self):
        raw_issue = {
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "message": "Division by zero: the divisor `0` is always zero.",
            "file_path": "src/math_utils.py",
            "line_number": 2,
            "column": 0,
            "code_snippet": "x / 0",
            "evidence": {
                "operator": "/",
                "right_operand": "0",
                "classification": "definitely_zero",
            },
            "severity": "high",
        }

        # Override mock for single issue
        self.mock_tokenizer.return_value = {
            "input_ids": torch.tensor([[101, 102]]),
            "attention_mask": torch.tensor([[1, 1]]),
        }
        self.mock_model.return_value = {
            "severity_probabilities": torch.tensor([[0.05, 0.90, 0.04, 0.01]]),
            "priority_probabilities": torch.tensor([[0.85, 0.10, 0.03, 0.02]]),
        }

        enriched = self.classifier.enrich_candidate_issue(raw_issue, language="Python")

        # Original fields must remain untouched
        self.assertEqual(enriched["rule_id"], "PY_DIV_001")
        self.assertEqual(enriched["file_path"], "src/math_utils.py")
        self.assertEqual(enriched["line_number"], 2)
        self.assertEqual(enriched["code_snippet"], "x / 0")
        self.assertEqual(enriched["evidence"]["classification"], "definitely_zero")

        # Classification block appended
        self.assertIn("classification", enriched)
        self.assertIn("severity", enriched["classification"])
        self.assertIn("priority", enriched["classification"])
        self.assertIn("needs_review", enriched["classification"])


if __name__ == "__main__":
    unittest.main()
