"""
test_report_exporter.py
-----------------------
Unit and integration tests for ReportExporter across all supported formats:
PDF, CSV, JSON, Markdown, and HTML.
"""

import csv
import io
import json
import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.report_exporter import ReportExporter, report_exporter
from app.services.bug_report_service import bug_report_service


class TestReportExporter(unittest.TestCase):
    """Tests for multi-format export of bug reports."""

    def setUp(self):
        self.exporter = ReportExporter()
        self.sample_reports = [
            {
                "id": "BUG-2026-0001",
                "issue_id": "BUG-2026-0001",
                "title": "Potential Division by Zero in calculate()",
                "description": "Division by potentially zero value: the divisor `divisor` may be zero at runtime.",
                "file_path": "src/calculator.py",
                "file": "src/calculator.py",
                "line": 15,
                "location": {"line": 15, "column": 8},
                "language": "Python",
                "function_name": "calculate",
                "class_name": "CalculatorService",
                "category": "division_by_zero",
                "severity": "high",
                "priority": "p2",
                "priority_formatted": "P2 • Fix this week",
                "confidence": 0.95,
                "status": "Open",
                "static_analysis": {
                    "rule_id": "PY_DIV_001",
                    "code_snippet": "total / divisor",
                    "evidence": {"operator": "/", "right_operand": "divisor"},
                },
                "similarity": {
                    "is_duplicate": False,
                    "duplicate_of": None,
                    "similar_issues": [],
                },
                "suggestedFix": {
                    "remove": "- total / divisor",
                    "add": "+ if (divisor != 0):\n+     total / divisor",
                    "note": "Validate that divisor is non-zero before dividing.",
                },
            },
            {
                "id": "BUG-2026-0002",
                "issue_id": "BUG-2026-0002",
                "title": "Unclosed File Resource in read_config()",
                "description": "open() called outside with-statement.",
                "file_path": "src/config.py",
                "file": "src/config.py",
                "line": 42,
                "location": {"line": 42, "column": 4},
                "language": "Python",
                "function_name": "read_config",
                "class_name": None,
                "category": "unclosed_resource",
                "severity": "critical",
                "priority": "p1",
                "priority_formatted": "P1 • Fix immediately",
                "confidence": 0.99,
                "status": "Open",
                "static_analysis": {
                    "rule_id": "PY_RES_001",
                    "code_snippet": "f = open('config.json')",
                    "evidence": {"call": "open"},
                },
                "similarity": {
                    "is_duplicate": True,
                    "duplicate_of": "BUG-2026-0001",
                    "similar_issues": ["BUG-2026-0001"],
                },
                "suggestedFix": {
                    "note": "Use with open(...) as f: to ensure safe cleanup.",
                },
            },
        ]
        self.sample_stats = {
            "total_bugs": 2,
            "critical": 1,
            "high": 1,
            "medium": 0,
            "low": 0,
            "priority_p1": 1,
            "priority_p2": 1,
            "priority_p3": 0,
            "priority_p4": 0,
            "duplicates_count": 1,
        }
        self.repo_info = {
            "id": "repo-test-123",
            "name": "MyProject",
            "path": "/workspace/MyProject",
        }

    # -------------------------------------------------------------------------
    # 1. CSV EXPORT TESTS
    # -------------------------------------------------------------------------

    def test_export_csv_headers_and_content(self):
        content, media_type, filename = self.exporter.export(
            reports=self.sample_reports,
            format_type="csv",
            summary_stats=self.sample_stats,
            repo_info=self.repo_info,
        )

        self.assertEqual(media_type, "text/csv; charset=utf-8")
        self.assertTrue(filename.startswith("MyProject_bugs_"))
        self.assertTrue(filename.endswith(".csv"))

        # Decode CSV (handling BOM)
        csv_text = content.decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(csv_text)))

        # Header check
        self.assertIn("Bug ID", reader[0])
        self.assertIn("Severity", reader[0])
        self.assertIn("Remediation Note", reader[0])

        # Rows check
        self.assertEqual(len(reader), 3)  # Header + 2 bug rows
        row1 = reader[1]
        self.assertEqual(row1[0], "BUG-2026-0001")
        self.assertEqual(row1[2], "HIGH")
        self.assertEqual(row1[8], "calculate")
        self.assertEqual(row1[9], "CalculatorService")
        self.assertEqual(row1[11], "PY_DIV_001")

        row2 = reader[2]
        self.assertEqual(row2[0], "BUG-2026-0002")
        self.assertEqual(row2[2], "CRITICAL")
        self.assertEqual(row2[14], "BUG-2026-0001")  # duplicate_of

    # -------------------------------------------------------------------------
    # 2. JSON EXPORT TESTS
    # -------------------------------------------------------------------------

    def test_export_json_validity_and_roundtrip(self):
        content, media_type, filename = self.exporter.export(
            reports=self.sample_reports,
            format_type="json",
            summary_stats=self.sample_stats,
            repo_info=self.repo_info,
        )

        self.assertEqual(media_type, "application/json")
        self.assertTrue(filename.endswith(".json"))

        parsed = json.loads(content.decode("utf-8"))
        self.assertIn("metadata", parsed)
        self.assertIn("summary_stats", parsed)
        self.assertIn("bug_reports", parsed)
        self.assertEqual(parsed["metadata"]["total_bugs"], 2)
        self.assertEqual(len(parsed["bug_reports"]), 2)
        self.assertEqual(parsed["bug_reports"][0]["id"], "BUG-2026-0001")

    # -------------------------------------------------------------------------
    # 3. MARKDOWN EXPORT TESTS
    # -------------------------------------------------------------------------

    def test_export_markdown_formatting(self):
        content, media_type, filename = self.exporter.export(
            reports=self.sample_reports,
            format_type="md",
            summary_stats=self.sample_stats,
            repo_info=self.repo_info,
        )

        self.assertEqual(media_type, "text/markdown; charset=utf-8")
        self.assertTrue(filename.endswith(".md"))

        md_text = content.decode("utf-8")
        self.assertIn("# Bug Triage & Security Audit Report", md_text)
        self.assertIn("**Repository:** `MyProject`", md_text)
        self.assertIn("## Executive Summary", md_text)
        self.assertIn("### 1. [BUG-2026-0001] Potential Division by Zero in calculate()", md_text)
        self.assertIn("```python", md_text)
        self.assertIn("total / divisor", md_text)
        self.assertIn("```diff", md_text)

    # -------------------------------------------------------------------------
    # 4. HTML EXPORT TESTS
    # -------------------------------------------------------------------------

    def test_export_html_formatting(self):
        content, media_type, filename = self.exporter.export(
            reports=self.sample_reports,
            format_type="html",
            summary_stats=self.sample_stats,
            repo_info=self.repo_info,
        )

        self.assertEqual(media_type, "text/html; charset=utf-8")
        self.assertTrue(filename.endswith(".html"))

        html_text = content.decode("utf-8")
        self.assertIn("<!DOCTYPE html>", html_text)
        self.assertIn("<title>Bug Triage Report - MyProject</title>", html_text)
        self.assertIn("BUG-2026-0001", html_text)
        self.assertIn("BUG-2026-0002", html_text)
        self.assertIn("window.print()", html_text)

    # -------------------------------------------------------------------------
    # 5. PDF EXPORT TESTS
    # -------------------------------------------------------------------------

    def test_export_pdf_valid_pdf_structure(self):
        content, media_type, filename = self.exporter.export(
            reports=self.sample_reports,
            format_type="pdf",
            summary_stats=self.sample_stats,
            repo_info=self.repo_info,
        )

        self.assertEqual(media_type, "application/pdf")
        self.assertTrue(filename.endswith(".pdf"))

        # Check standard PDF 1.4 header and trailer
        self.assertTrue(content.startswith(b"%PDF-1.4"))
        self.assertIn(b"%%EOF", content)
        self.assertIn(b"/Catalog", content)
        self.assertIn(b"/Pages", content)
        self.assertIn(b"/Helvetica", content)
        self.assertTrue(len(content) > 500)

    # -------------------------------------------------------------------------
    # 6. INVALID FORMAT & EMPTY REPORTS HANDLING
    # -------------------------------------------------------------------------

    def test_unsupported_format_raises_value_error(self):
        with self.assertRaises(ValueError):
            self.exporter.export(reports=[], format_type="docx")

    def test_empty_reports_export_handles_gracefully(self):
        for fmt in ("pdf", "csv", "json", "md", "html"):
            content, media_type, filename = self.exporter.export(
                reports=[],
                format_type=fmt,
                summary_stats=None,
                repo_info=None,
            )
            self.assertTrue(len(content) > 0, f"Empty content for format {fmt}")
            self.assertTrue(len(filename) > 0)

    # -------------------------------------------------------------------------
    # 7. BugReportService INTEGRATION
    # -------------------------------------------------------------------------

    def test_bug_report_service_export_delegation(self):
        content, media_type, filename = bug_report_service.export_reports(
            reports=self.sample_reports,
            format_type="pdf",
            summary_stats=self.sample_stats,
            repo_info=self.repo_info,
        )
        self.assertTrue(content.startswith(b"%PDF-1.4"))
        self.assertEqual(media_type, "application/pdf")


if __name__ == "__main__":
    unittest.main(verbosity=2)
