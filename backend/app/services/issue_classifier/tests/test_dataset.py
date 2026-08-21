"""
Unit tests for DatasetPipeline, validation, splitting & deduplication.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

from app.services.issue_classifier.dataset import DatasetPipeline


class TestDatasetPipeline(unittest.TestCase):

    def setUp(self):
        self.pipeline = DatasetPipeline()

    def test_label_parsing_valid(self):
        rec = {
            "rule_id": "PY_DIV_001",
            "message": "Division by zero",
            "code_snippet": "x / 0",
            "severity": "critical",
            "priority": "p1",
        }
        _, sev_id, prio_id = self.pipeline.validate_and_parse_record(rec)
        self.assertEqual(sev_id, 0)
        self.assertEqual(prio_id, 0)

    def test_label_parsing_invalid_severity(self):
        rec = {
            "rule_id": "PY_DIV_001",
            "message": "Division by zero",
            "code_snippet": "x / 0",
            "severity": "fatal",  # Invalid
            "priority": "p1",
        }
        with self.assertRaises(ValueError):
            self.pipeline.validate_and_parse_record(rec)

    def test_label_parsing_invalid_priority(self):
        rec = {
            "rule_id": "PY_DIV_001",
            "message": "Division by zero",
            "code_snippet": "x / 0",
            "severity": "high",
            "priority": "urgent",  # Invalid
        }
        with self.assertRaises(ValueError):
            self.pipeline.validate_and_parse_record(rec)

    def test_deduplication(self):
        records = [
            {"rule_id": "PY_DIV_001", "message": "Div by zero", "code_snippet": "x / 0", "severity": "high", "priority": "p1"},
            {"rule_id": "PY_DIV_001", "message": "Div by zero", "code_snippet": "x / 0", "severity": "high", "priority": "p1"},  # Duplicate
            {"rule_id": "JAVA_LOOP_001", "message": "Infinite loop", "code_snippet": "while(true){}", "severity": "medium", "priority": "p2"},
        ]
        unique = self.pipeline.deduplicate_records(records)
        self.assertEqual(len(unique), 2)

    def test_dataset_split_proportions(self):
        records = [
            {"rule_id": f"RULE_{i}", "message": f"msg {i}", "code_snippet": f"code {i}", "severity": "low", "priority": "p4"}
            for i in range(100)
        ]
        train, val, test = self.pipeline.split_dataset(records, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, seed=42)

        self.assertEqual(len(train), 70)
        self.assertEqual(len(val), 15)
        self.assertEqual(len(test), 15)

        # Ensure no overlap
        train_codes = set(r["code_snippet"] for r in train)
        val_codes = set(r["code_snippet"] for r in val)
        test_codes = set(r["code_snippet"] for r in test)

        self.assertEqual(len(train_codes.intersection(val_codes)), 0)
        self.assertEqual(len(train_codes.intersection(test_codes)), 0)
        self.assertEqual(len(val_codes.intersection(test_codes)), 0)

    def test_compute_class_weights(self):
        # 10 samples of class 0, 90 samples of class 1
        labels = [0] * 10 + [1] * 90
        weights = self.pipeline.compute_class_weights(labels, num_classes=2)

        self.assertEqual(len(weights), 2)
        # Class 0 should have higher weight than class 1
        self.assertGreater(weights[0].item(), weights[1].item())


if __name__ == "__main__":
    unittest.main()
