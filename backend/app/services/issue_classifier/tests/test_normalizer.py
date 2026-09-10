"""
Unit tests for IssueNormalizer and ablation modes.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

from app.services.issue_classifier.config import NormalizationConfig
from app.services.issue_classifier.normalizer import IssueNormalizer
from app.services.static_analyzer.models import CandidateIssue


class TestIssueNormalizer(unittest.TestCase):

    def setUp(self):
        self.sample_issue = {
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
                "right_node_type": "integer",
                "classification": "definitely_zero",
            },
            "language": "Python",
        }

    def test_standard_normalization(self):
        normalizer = IssueNormalizer()
        text = normalizer.normalize(self.sample_issue)

        self.assertIn("Language: Python", text)
        self.assertIn("Rule ID: PY_DIV_001", text)
        self.assertIn("Issue Type: division_by_zero", text)
        self.assertIn("Message: Division by zero: the divisor `0` is always zero.", text)
        self.assertIn("Code: x / 0", text)
        self.assertIn("Evidence:", text)
        self.assertIn("Operator: /", text)
        self.assertIn("Right Operand: 0", text)
        self.assertIn("Classification: definitely_zero", text)

        # File-level metadata must NOT be included in model input
        self.assertNotIn("src/math_utils.py", text)
        self.assertNotIn("line_number", text)
        self.assertNotIn("column", text)

    def test_rule_id_ablation_mode(self):
        config = NormalizationConfig(include_rule_id=False)
        normalizer = IssueNormalizer(config=config)
        text = normalizer.normalize(self.sample_issue)

        self.assertNotIn("Rule ID:", text)
        self.assertNotIn("PY_DIV_001", text)
        self.assertIn("Issue Type: division_by_zero", text)
        self.assertIn("Code: x / 0", text)

    def test_candidate_issue_object_support(self):
        obj = CandidateIssue(
            rule_id="JAVA_EQ_001",
            issue_type="string_equality",
            message="String comparison using ==",
            file_path="App.java",
            line_number=10,
            column=4,
            code_snippet="str == other",
            evidence={"left": "str", "right": "other"},
            severity="high",
        )
        normalizer = IssueNormalizer()
        text = normalizer.normalize(obj, language="Java")

        self.assertIn("Language: Java", text)
        self.assertIn("Rule ID: JAVA_EQ_001", text)
        self.assertIn("Code: str == other", text)
        self.assertIn("Left: str", text)

    def test_missing_evidence_and_optional_fields(self):
        sparse_issue = {
            "rule_id": "JS_EQ_001",
            "message": "Loose equality",
            "code_snippet": "a == b",
        }
        normalizer = IssueNormalizer()
        text = normalizer.normalize(sparse_issue, language="JavaScript")

        self.assertIn("Language: JavaScript", text)
        self.assertIn("Rule ID: JS_EQ_001", text)
        self.assertIn("Message: Loose equality", text)
        self.assertIn("Code: a == b", text)
        self.assertNotIn("Evidence:", text)


if __name__ == "__main__":
    unittest.main()
