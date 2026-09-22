"""
test_validation_status.py
--------------------------
Tests for Feature 2: AI Confidence vs Validation Status split.

Covers:
  1. ValidationStatus enum values
  2. EnrichedBugReport has ai_confidence and validation_status fields
  3. validation_status defaults to UNVERIFIED
  4. ai_confidence is independent of validation_status
  5. TestHarnessResultSchema serialises correctly
  6. BugReportSummaryStats has verified_count field
  7. report_exporter CSV includes AI Confidence and Validation Status columns
  8. report_exporter JSON metadata includes verified/unverified counts
  9. report_exporter Markdown includes validation line per bug
  10. report_exporter HTML includes validation badge
"""

import csv
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.bug_report import (
    BugExplanation,
    ClassificationResult,
    EnrichedBugReport,
    EvidenceItem,
    LocationInfo,
    SimilarityInfo,
    StaticAnalysisFinding,
    SuggestedFix,
    TestHarnessResultSchema,
    ValidationStatus,
    BugReportSummaryStats,
)
from app.services.report_exporter import ReportExporter


def _make_report(
    validation_status: str = "UNVERIFIED",
    ai_confidence: float = 0.85,
    **kwargs,
) -> dict:
    """Return a minimal bug report dict with Feature 2 fields."""
    base = {
        "id": "BUG-2026-0001",
        "issue_id": "BUG-2026-0001",
        "title": "Test Bug",
        "description": "A test bug.",
        "file_path": "src/calc.py",
        "file": "src/calc.py",
        "line": 10,
        "location": {"line": 10, "column": 0},
        "language": "Python",
        "function_name": "calc",
        "class_name": None,
        "category": "division_by_zero",
        "severity": "high",
        "priority": "p2",
        "priority_formatted": "P2 • Fix this week",
        "confidence": ai_confidence,
        "ai_confidence": ai_confidence,
        "validation_status": validation_status,
        "status": "Open",
        "static_analysis": {
            "rule_id": "PY_DIV_001",
            "code_snippet": "x / y",
            "evidence": {},
        },
        "similarity": {"is_duplicate": False, "duplicate_of": None, "similar_issues": []},
        "suggestedFix": {"remove": "- x / y", "add": "+ if y != 0: x / y", "note": "Guard zero."},
    }
    base.update(kwargs)
    return base


class TestValidationStatusEnum(unittest.TestCase):

    def test_verified_value(self):
        self.assertEqual(ValidationStatus.VERIFIED, "VERIFIED")

    def test_unverified_value(self):
        self.assertEqual(ValidationStatus.UNVERIFIED, "UNVERIFIED")

    def test_enum_is_str(self):
        self.assertIsInstance(ValidationStatus.VERIFIED, str)


class TestEnrichedBugReportFields(unittest.TestCase):

    def _build_report(self, **overrides) -> EnrichedBugReport:
        base = dict(
            id="BUG-001",
            issue_id="BUG-001",
            title="T",
            description="D",
            file_path="f.py",
            file="f.py",
            line=1,
            location=LocationInfo(line=1),
            category="division_by_zero",
            static_analysis=StaticAnalysisFinding(
                rule_id="PY_DIV_001", issue_type="div", message="m"
            ),
            similarity=SimilarityInfo(),
            explanation=BugExplanation(
                what="w", where="w", why="w", evidence_summary="e",
                category="c", severity_assessment="s", importance_assessment="i",
                similarity_or_duplicate="n",
            ),
        )
        base.update(overrides)
        return EnrichedBugReport(**base)

    def test_default_ai_confidence(self):
        r = self._build_report()
        self.assertEqual(r.ai_confidence, 1.0)

    def test_default_validation_status_is_unverified(self):
        r = self._build_report()
        self.assertEqual(r.validation_status, ValidationStatus.UNVERIFIED)

    def test_set_ai_confidence(self):
        r = self._build_report(ai_confidence=0.72)
        self.assertAlmostEqual(r.ai_confidence, 0.72)

    def test_set_validation_status_verified(self):
        r = self._build_report(validation_status=ValidationStatus.VERIFIED)
        self.assertEqual(r.validation_status, ValidationStatus.VERIFIED)

    def test_test_harness_result_none_by_default(self):
        r = self._build_report()
        self.assertIsNone(r.test_harness_result)

    def test_test_harness_result_schema(self):
        harness = TestHarnessResultSchema(
            generated_test_source="def test_foo(): pass",
            language="python",
            pre_fix_passed=False,
            post_fix_passed=True,
            validated=True,
        )
        r = self._build_report(test_harness_result=harness)
        self.assertTrue(r.test_harness_result.validated)
        self.assertFalse(r.test_harness_result.pre_fix_passed)
        self.assertTrue(r.test_harness_result.post_fix_passed)

    def test_model_dump_includes_fields(self):
        r = self._build_report(ai_confidence=0.9, validation_status=ValidationStatus.VERIFIED)
        d = r.model_dump(mode="json")
        self.assertIn("ai_confidence", d)
        self.assertIn("validation_status", d)
        self.assertEqual(d["validation_status"], "VERIFIED")


class TestBugReportSummaryStatsVerifiedCount(unittest.TestCase):

    def test_verified_count_field_exists(self):
        stats = BugReportSummaryStats()
        self.assertEqual(stats.verified_count, 0)

    def test_verified_count_increments(self):
        stats = BugReportSummaryStats(verified_count=3)
        self.assertEqual(stats.verified_count, 3)


class TestReportExporterFeature2(unittest.TestCase):

    def setUp(self):
        self.exporter = ReportExporter()
        self.verified_report = _make_report(validation_status="VERIFIED", ai_confidence=0.93)
        self.unverified_report = _make_report(validation_status="UNVERIFIED", ai_confidence=0.55)
        self.reports = [self.verified_report, self.unverified_report]

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    def test_csv_has_ai_confidence_column(self):
        content = self.exporter.export_csv(self.reports)
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        self.assertIn("AI Confidence", headers)

    def test_csv_has_validation_status_column(self):
        content = self.exporter.export_csv(self.reports)
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        self.assertIn("Validation Status", headers)

    def test_csv_validation_status_values(self):
        content = self.exporter.export_csv(self.reports)
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        self.assertEqual(rows[0]["Validation Status"], "VERIFIED")
        self.assertEqual(rows[1]["Validation Status"], "UNVERIFIED")

    def test_csv_ai_confidence_values(self):
        content = self.exporter.export_csv(self.reports)
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        self.assertEqual(rows[0]["AI Confidence"], "0.93")
        self.assertEqual(rows[1]["AI Confidence"], "0.55")

    # ------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------

    def test_json_metadata_has_verified_count(self):
        content = self.exporter.export_json(self.reports)
        data = json.loads(content)
        self.assertIn("verified_count", data["metadata"])
        self.assertEqual(data["metadata"]["verified_count"], 1)

    def test_json_metadata_has_unverified_count(self):
        content = self.exporter.export_json(self.reports)
        data = json.loads(content)
        self.assertIn("unverified_count", data["metadata"])
        self.assertEqual(data["metadata"]["unverified_count"], 1)

    # ------------------------------------------------------------------
    # Markdown
    # ------------------------------------------------------------------

    def test_markdown_contains_validation_line(self):
        content = self.exporter.export_markdown(self.reports)
        text = content.decode("utf-8")
        self.assertIn("Validation", text)
        self.assertIn("VERIFIED", text)
        self.assertIn("UNVERIFIED", text)

    def test_markdown_contains_ai_confidence(self):
        content = self.exporter.export_markdown(self.reports)
        text = content.decode("utf-8")
        self.assertIn("AI Confidence", text)

    # ------------------------------------------------------------------
    # HTML
    # ------------------------------------------------------------------

    def test_html_contains_validation_badge(self):
        content = self.exporter.export_html(self.reports)
        text = content.decode("utf-8")
        self.assertIn("VERIFIED", text)
        self.assertIn("UNVERIFIED", text)

    def test_html_contains_confidence_badge(self):
        content = self.exporter.export_html(self.reports)
        text = content.decode("utf-8")
        self.assertIn("AI:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
