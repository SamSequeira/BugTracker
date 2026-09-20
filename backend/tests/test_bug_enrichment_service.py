"""
test_bug_enrichment_service.py
------------------------------
Comprehensive test suite for Bug Enrichment and Complete Bug Report Generation.
Tests:
  1. Single issue enrichment and field preservation
  2. Batch issue enrichment with deduplication and similarity linking
  3. AST context extraction (enclosing function and class) across Python, JS, Java
  4. Structured evidence collection and typing
  5. 8-criteria human-readable explanation generation
  6. Graceful degradation when optional data is missing
  7. Remediation diff generation for supported rules
  8. End-to-end repository report generation and summary stats
  9. Backward-compatible API response formats and pure JSON serializability
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.bug_report import (
    EnrichedBugReport,
    BugReportSummaryStats,
    EvidenceItem,
    SimilarityInfo,
)
from app.services.ast_generator import ASTGenerator
from app.services.bug_enrichment_service import (
    BugEnrichmentService,
    bug_enrichment_service,
)
from app.services.bug_report_service import (
    BugReportService,
    bug_report_service,
)
from app.services.candidate_issue_service import candidate_issue_service
from app.services.repository_analysis_service import RepositoryAnalysisService
from app.services.static_analyzer.models import CandidateIssue


class TestBugEnrichmentService(unittest.TestCase):
    """Unit and integration tests for the Bug Enrichment Layer."""

    def setUp(self):
        self.ast_gen = ASTGenerator()
        self.enrichment_svc = BugEnrichmentService()

    # -------------------------------------------------------------------------
    # 1. Single Issue Enrichment
    # -------------------------------------------------------------------------

    def test_single_issue_enrichment_preserves_static_and_candidate_data(self):
        raw_issue = {
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "message": "Division by potentially zero value: the divisor `divisor` may be zero.",
            "file_path": "src/calculator.py",
            "line_number": 12,
            "column": 4,
            "code_snippet": "return total / divisor",
            "evidence": {"operator": "/", "right_operand": "divisor"},
            "severity": "high",
        }

        report = self.enrichment_svc.enrich_issue(
            issue=raw_issue,
            repository_id="repo-alpha",
            repository_path="/workspace/repo-alpha",
            index=1,
        )

        self.assertIsInstance(report, EnrichedBugReport)
        self.assertTrue(report.id.startswith("BUG-2026-"))
        self.assertEqual(report.issue_id, report.id)
        self.assertEqual(report.file_path, "src/calculator.py")
        self.assertEqual(report.file, "src/calculator.py")
        self.assertEqual(report.line, 12)
        self.assertEqual(report.language, "Python")
        self.assertEqual(report.severity, "high")
        self.assertEqual(report.priority, "p2")
        self.assertEqual(report.priority_formatted, "P2 • Fix this week")
        self.assertEqual(report.category, "division_by_zero")
        self.assertEqual(report.status, "Open")

        # Static analysis finding preservation
        self.assertEqual(report.static_analysis.rule_id, "PY_DIV_001")
        self.assertEqual(report.static_analysis.message, raw_issue["message"])
        self.assertEqual(report.static_analysis.code_snippet, "return total / divisor")
        self.assertEqual(report.static_analysis.evidence["right_operand"], "divisor")

        # Candidate issue preservation
        self.assertEqual(report.candidate_issue["rule_id"], "PY_DIV_001")
        self.assertEqual(report.candidate_issue["line_number"], 12)

    # -------------------------------------------------------------------------
    # 2. AST Context Extraction (Function & Class)
    # -------------------------------------------------------------------------

    def test_ast_context_extraction_python(self):
        py_source = textwrap.dedent("""\
            class MathService:
                def __init__(self):
                    self.name = 'math'

                def compute_average(self, total, count):
                    return total / count
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
            f.write(py_source)
            f_path = f.name

        try:
            ast_res = self.ast_gen.generate_ast(f_path, "Python")
            self.assertTrue(ast_res["success"])

            raw_issue = {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Potential division by zero",
                "file_path": f_path,
                "line_number": 6,
                "column": 15,
                "code_snippet": "total / count",
                "evidence": {"operator": "/", "right_operand": "count"},
                "severity": "high",
            }

            report = self.enrichment_svc.enrich_issue(
                issue=raw_issue,
                ast_dict=ast_res["ast"],
                source_code=py_source,
            )

            self.assertEqual(report.function_name, "compute_average")
            self.assertEqual(report.class_name, "MathService")
            self.assertIn("MathService.compute_average()", report.title)
            self.assertTrue(len(report.codeSnippet) >= 1)
            self.assertTrue(any(line.isErr and "total / count" in line.text for line in report.codeSnippet))
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_ast_context_extraction_javascript(self):
        js_source = textwrap.dedent("""\
            class OrderManager {
                processDiscount(price, factor) {
                    if (factor == 0) {
                        return 0;
                    }
                    return price / factor;
                }
            }
        """)
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, encoding="utf-8") as f:
            f.write(js_source)
            f_path = f.name

        try:
            ast_res = self.ast_gen.generate_ast(f_path, "JavaScript")
            self.assertTrue(ast_res["success"])

            raw_issue = {
                "rule_id": "JS_EQ_001",
                "issue_type": "loose_equality",
                "message": "Loose equality used",
                "file_path": f_path,
                "line_number": 3,
                "column": 12,
                "code_snippet": "factor == 0",
                "evidence": {"operator": "=="},
                "severity": "medium",
            }

            report = self.enrichment_svc.enrich_issue(
                issue=raw_issue,
                ast_dict=ast_res["ast"],
                source_code=js_source,
            )

            self.assertEqual(report.function_name, "processDiscount")
            self.assertEqual(report.class_name, "OrderManager")
            self.assertEqual(report.language, "JavaScript")
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_ast_context_extraction_java(self):
        java_source = textwrap.dedent("""\
            public class DataProcessor {
                public void handleData(String path) {
                    try {
                        int x = 10;
                    } catch (Exception e) {}
                }
            }
        """)
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False, encoding="utf-8") as f:
            f.write(java_source)
            f_path = f.name

        try:
            ast_res = self.ast_gen.generate_ast(f_path, "Java")
            self.assertTrue(ast_res["success"])

            raw_issue = {
                "rule_id": "JAVA_EXC_001",
                "issue_type": "empty_catch",
                "message": "Empty catch block",
                "file_path": f_path,
                "line_number": 5,
                "column": 10,
                "code_snippet": "catch (Exception e) {}",
                "evidence": {"exception_type": "Exception"},
                "severity": "medium",
            }

            report = self.enrichment_svc.enrich_issue(
                issue=raw_issue,
                ast_dict=ast_res["ast"],
                source_code=java_source,
            )

            self.assertEqual(report.function_name, "handleData")
            self.assertEqual(report.class_name, "DataProcessor")
            self.assertEqual(report.language, "Java")
        finally:
            Path(f_path).unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # 3. Structured Evidence Collection
    # -------------------------------------------------------------------------

    def test_structured_evidence_collection(self):
        raw_issue = {
            "rule_id": "PY_RES_001",
            "issue_type": "unclosed_resource",
            "message": "open() called outside with-statement",
            "file_path": "src/io_handler.py",
            "line_number": 25,
            "column": 8,
            "code_snippet": "f = open(path, 'r')",
            "evidence": {"call": "open", "arg": "path"},
            "severity": "high",
        }

        classification = {
            "severity": {"label": "high", "confidence": 0.95, "probabilities": {"high": 0.95, "critical": 0.05}},
            "priority": {"label": "p1", "confidence": 0.91, "probabilities": {"p1": 0.91, "p2": 0.09}},
            "needs_review": False,
        }

        report = self.enrichment_svc.enrich_issue(
            issue=raw_issue,
            classification=classification,
        )

        evidence_types = [ev.type for ev in report.evidence]
        self.assertIn("static_analysis", evidence_types)
        self.assertIn("source", evidence_types)
        self.assertIn("classification", evidence_types)

        # Check classification evidence
        classif_ev = next(ev for ev in report.evidence if ev.type == "classification")
        self.assertEqual(classif_ev.data["confidence"], 0.93)
        self.assertFalse(classif_ev.data["needs_review"])

        # Check static analysis evidence
        static_ev = next(ev for ev in report.evidence if ev.type == "static_analysis")
        self.assertEqual(static_ev.data["rule_id"], "PY_RES_001")
        self.assertEqual(static_ev.data["rule_evidence"]["call"], "open")

    # -------------------------------------------------------------------------
    # 4. Human-Readable Explanation Answering All 8 Criteria
    # -------------------------------------------------------------------------

    def test_explanation_answers_all_eight_criteria(self):
        raw_issue = {
            "rule_id": "JS_AWA_001",
            "issue_type": "await_in_loop",
            "message": "await inside loop executes sequentially instead of concurrently.",
            "file_path": "src/services/api.js",
            "line_number": 44,
            "column": 12,
            "code_snippet": "await fetchItem(items[i])",
            "evidence": {"loop_type": "for_statement"},
            "severity": "medium",
        }

        report = self.enrichment_svc.enrich_issue(issue=raw_issue)
        exp = report.explanation

        # 1. What is the issue?
        self.assertTrue(len(exp.what) > 10)
        self.assertIn("await inside loop", exp.what)

        # 2. Where is it?
        self.assertIn("src/services/api.js", exp.where)
        self.assertIn("line 44", exp.where)

        # 3. Why was it detected?
        self.assertIn("JS_AWA_001", exp.why)

        # 4. What evidence supports it?
        self.assertIn("await fetchItem(items[i])", exp.evidence_summary)
        self.assertIn("loop_type='for_statement'", exp.evidence_summary)

        # 5. What category does it belong to?
        self.assertIn("await_in_loop", exp.category)

        # 6. How severe is it?
        self.assertIn("MEDIUM", exp.severity_assessment)

        # 7. How important is it to fix?
        self.assertIn("Priority", exp.importance_assessment)

        # 8. Is it similar or duplicate to another issue?
        self.assertIn("independent finding", exp.similarity_or_duplicate)

        # Full narrative
        self.assertTrue(len(exp.full_text) > 100)
        self.assertIn("### Issue Overview", exp.full_text)

    # -------------------------------------------------------------------------
    # 5. Batch Deduplication and Similarity Linking
    # -------------------------------------------------------------------------

    def test_batch_enrichment_deduplication_and_similarity(self):
        issues = [
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero in calculation",
                "file_path": "src/calc.py",
                "line_number": 10,
                "column": 4,
                "code_snippet": "a / b",
                "evidence": {"operator": "/"},
                "severity": "high",
            },
            # Exact duplicate at same file, line, rule
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero in calculation",
                "file_path": "src/calc.py",
                "line_number": 10,
                "column": 4,
                "code_snippet": "a / b",
                "evidence": {"operator": "/"},
                "severity": "high",
            },
            # Similar occurrence of same rule in another file
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero in metrics",
                "file_path": "src/metrics.py",
                "line_number": 55,
                "column": 8,
                "code_snippet": "total / n",
                "evidence": {"operator": "/"},
                "severity": "high",
            },
            # Distinct independent issue
            {
                "rule_id": "PY_RES_001",
                "issue_type": "unclosed_resource",
                "message": "File open not closed",
                "file_path": "src/io.py",
                "line_number": 20,
                "column": 0,
                "code_snippet": "open(p)",
                "evidence": {"call": "open"},
                "severity": "medium",
            },
        ]

        reports = self.enrichment_svc.enrich_issues_batch(issues, repository_id="repo-test")

        self.assertEqual(len(reports), 4)

        # Issue 1: Primary original
        self.assertFalse(reports[0].similarity.is_duplicate)
        self.assertIsNone(reports[0].duplicate_of)

        # Issue 2: Flagged as duplicate of Issue 1
        self.assertTrue(reports[1].similarity.is_duplicate)
        self.assertEqual(reports[1].similarity.duplicate_of, reports[0].id)
        self.assertEqual(reports[1].similarity.relationship_type, "duplicate")

        # Issue 3: Flagged as similar (same rule across different files)
        self.assertFalse(reports[2].similarity.is_duplicate)
        self.assertEqual(reports[2].similarity.relationship_type, "similar")
        self.assertTrue(len(reports[2].similar_issues) >= 1)

        # Issue 4: Independent
        self.assertFalse(reports[3].similarity.is_duplicate)
        self.assertEqual(reports[3].similarity.relationship_type, "independent")

    # -------------------------------------------------------------------------
    # 6. Graceful Degradation on Missing Optional Data
    # -------------------------------------------------------------------------

    def test_missing_optional_data_does_not_crash(self):
        bare_issue = {
            "rule_id": "UNKNOWN_RULE",
            "issue_type": "generic_error",
            "message": "Something went wrong",
            "file_path": "orphan_file.txt",
            "line_number": 1,
        }

        # Enrich with completely missing AST, source, classification, similarity
        report = self.enrichment_svc.enrich_issue(
            issue=bare_issue,
            ast_dict=None,
            source_code=None,
            classification=None,
            similarity_info=None,
        )

        self.assertIsInstance(report, EnrichedBugReport)
        self.assertEqual(report.file_path, "orphan_file.txt")
        self.assertEqual(report.line, 1)
        self.assertEqual(report.category, "generic_error")
        self.assertEqual(report.confidence, 1.0)
        self.assertIsNone(report.classification)
        self.assertIsNone(report.function_name)
        self.assertIsNone(report.class_name)
        self.assertFalse(report.similarity.is_duplicate)

        # Serializes cleanly to JSON
        json_str = json.dumps(report.model_dump(mode="json"))
        self.assertIn("orphan_file.txt", json_str)

    # -------------------------------------------------------------------------
    # 7. Remediation / Suggested Fix Generation
    # -------------------------------------------------------------------------

    def test_remediation_diff_generation_for_rules(self):
        rules_to_test = [
            ("PY_DIV_001", "a / b", {"right_operand": "b"}, "Python"),
            ("PY_RES_001", "open(path, 'r')", {}, "Python"),
            ("PY_EXC_001", "except:", {}, "Python"),
            ("PY_ASS_001", "assert x > 0", {}, "Python"),
            ("PY_MUT_001", "def f(items=[]):", {"param_name": "items"}, "Python"),
            ("JS_EQ_001", "x == y", {"operator": "=="}, "JavaScript"),
            ("JS_AWA_001", "await fetch()", {}, "JavaScript"),
            ("JAVA_EXC_001", "catch (Exception e) {}", {}, "Java"),
            ("JAVA_EQ_001", "s1 == s2", {"left_operand": "s1", "right_operand": "s2"}, "Java"),
            ("JAVA_RES_001", "new FileReader(path)", {}, "Java"),
            ("JAVA_LOOP_001", "while (true) {}", {}, "Java"),
        ]

        for rule_id, snippet, ev, lang in rules_to_test:
            fix = self.enrichment_svc._generate_suggested_fix(
                rule_id=rule_id,
                issue_type=rule_id.lower(),
                snippet=snippet,
                evidence=ev,
                language=lang,
            )
            self.assertIsNotNone(fix)
            self.assertTrue(len(fix.note) > 0, f"Fix note empty for {rule_id}")

    # -------------------------------------------------------------------------
    # 8. End-to-End Bug Report Service & Summary Stats
    # -------------------------------------------------------------------------

    def test_end_to_end_bug_report_service_generation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir)

            py_file = repo_path / "calc.py"
            py_file.write_text(
                "def divide(a, b):\n    return a / b\n",
                encoding="utf-8"
            )

            js_file = repo_path / "app.js"
            js_file.write_text(
                "function test(x, y) {\n    return x == y;\n}\n",
                encoding="utf-8"
            )

            ast_res = self.ast_gen.generate_ast_for_repository(str(repo_path))
            result = bug_report_service.generate_repository_reports(
                ast_result=ast_res,
                repository_id="test-repo-100",
                repository_path=str(repo_path),
            )

            self.assertIn("bug_reports", result)
            self.assertIn("summary_stats", result)
            self.assertIn("total_reports", result)
            self.assertIn("candidate_issues", result)
            self.assertIn("ast_analysis", result)

            stats = result["summary_stats"]
            self.assertEqual(stats["total_bugs"], result["total_reports"])
            self.assertTrue(result["total_reports"] >= 2)
            self.assertTrue(stats["total_files_analyzed"] >= 2)

            # Check pure JSON serializability
            serialized = json.dumps(result)
            self.assertTrue(len(serialized) > 200)

    # -------------------------------------------------------------------------
    # 9. RepositoryAnalysisService Full Pipeline Integration
    # -------------------------------------------------------------------------

    def test_repository_analysis_service_pipeline_backward_compatibility(self):
        import asyncio

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir)
            source = repo_path / "module.py"
            source.write_text(
                "def read(path):\n    f = open(path, 'r')\n    return f.read()\n",
                encoding="utf-8"
            )

            svc = RepositoryAnalysisService()
            response = asyncio.run(svc.analyze_repository(str(repo_path), repository_id="repo-xyz"))

            # Check legacy keys exist and match expectations
            self.assertEqual(response["repository_path"], str(repo_path))
            self.assertEqual(response["repository_id"], "repo-xyz")
            self.assertIn("ast_analysis", response)
            self.assertIn("candidate_issues", response)
            self.assertIn("total_candidate_issues", response)
            self.assertIn("summary", response)
            self.assertIn("files", response)
            self.assertIn("static_analysis", response)

            # Check new enriched bug report keys
            self.assertIn("bug_reports", response)
            self.assertIn("total_reports", response)
            self.assertIn("summary_stats", response)
            self.assertTrue(len(response["bug_reports"]) >= 1)

            first_report = response["bug_reports"][0]
            self.assertEqual(first_report["static_analysis"]["rule_id"], "PY_RES_001")
            self.assertIn("open() called outside a `with` statement", first_report["description"])
            self.assertIn("what", first_report["explanation"])
            self.assertIn("where", first_report["explanation"])
            self.assertIn("why", first_report["explanation"])

            # Verify entire response is JSON serializable
            json.dumps(response)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""
test_bug_enrichment_service.py
------------------------------
Comprehensive test suite for Bug Enrichment and Complete Bug Report Generation.
Tests:
  1. Single issue enrichment and field preservation
  2. Batch issue enrichment with deduplication and similarity linking
  3. AST context extraction (enclosing function and class) across Python, JS, Java
  4. Structured evidence collection and typing
  5. 8-criteria human-readable explanation generation
  6. Graceful degradation when optional data is missing
  7. Remediation diff generation for supported rules
  8. End-to-end repository report generation and summary stats
  9. Backward-compatible API response formats and pure JSON serializability
"""

import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.schemas.bug_report import (
    EnrichedBugReport,
    BugReportSummaryStats,
    EvidenceItem,
    SimilarityInfo,
)
from app.services.ast_generator import ASTGenerator
from app.services.bug_enrichment_service import (
    BugEnrichmentService,
    bug_enrichment_service,
)
from app.services.bug_report_service import (
    BugReportService,
    bug_report_service,
)
from app.services.candidate_issue_service import candidate_issue_service
from app.services.repository_analysis_service import RepositoryAnalysisService
from app.services.static_analyzer.models import CandidateIssue


class TestBugEnrichmentService(unittest.TestCase):
    """Unit and integration tests for the Bug Enrichment Layer."""

    def setUp(self):
        self.ast_gen = ASTGenerator()
        self.enrichment_svc = BugEnrichmentService()

    # -------------------------------------------------------------------------
    # 1. Single Issue Enrichment
    # -------------------------------------------------------------------------

    def test_single_issue_enrichment_preserves_static_and_candidate_data(self):
        raw_issue = {
            "rule_id": "PY_DIV_001",
            "issue_type": "division_by_zero",
            "message": "Division by potentially zero value: the divisor `divisor` may be zero.",
            "file_path": "src/calculator.py",
            "line_number": 12,
            "column": 4,
            "code_snippet": "return total / divisor",
            "evidence": {"operator": "/", "right_operand": "divisor"},
            "severity": "high",
        }

        report = self.enrichment_svc.enrich_issue(
            issue=raw_issue,
            repository_id="repo-alpha",
            repository_path="/workspace/repo-alpha",
            index=1,
        )

        self.assertIsInstance(report, EnrichedBugReport)
        self.assertTrue(report.id.startswith("BUG-2026-"))
        self.assertEqual(report.issue_id, report.id)
        self.assertEqual(report.file_path, "src/calculator.py")
        self.assertEqual(report.file, "src/calculator.py")
        self.assertEqual(report.line, 12)
        self.assertEqual(report.language, "Python")
        self.assertEqual(report.severity, "high")
        self.assertEqual(report.priority, "p2")
        self.assertEqual(report.priority_formatted, "P2 • Fix this week")
        self.assertEqual(report.category, "division_by_zero")
        self.assertEqual(report.status, "Open")

        # Static analysis finding preservation
        self.assertEqual(report.static_analysis.rule_id, "PY_DIV_001")
        self.assertEqual(report.static_analysis.message, raw_issue["message"])
        self.assertEqual(report.static_analysis.code_snippet, "return total / divisor")
        self.assertEqual(report.static_analysis.evidence["right_operand"], "divisor")

        # Candidate issue preservation
        self.assertEqual(report.candidate_issue["rule_id"], "PY_DIV_001")
        self.assertEqual(report.candidate_issue["line_number"], 12)

    # -------------------------------------------------------------------------
    # 2. AST Context Extraction (Function & Class)
    # -------------------------------------------------------------------------

    def test_ast_context_extraction_python(self):
        py_source = textwrap.dedent("""\
            class MathService:
                def __init__(self):
                    self.name = 'math'

                def compute_average(self, total, count):
                    return total / count
        """)
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
            f.write(py_source)
            f_path = f.name

        try:
            ast_res = self.ast_gen.generate_ast(f_path, "Python")
            self.assertTrue(ast_res["success"])

            raw_issue = {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Potential division by zero",
                "file_path": f_path,
                "line_number": 6,
                "column": 15,
                "code_snippet": "total / count",
                "evidence": {"operator": "/", "right_operand": "count"},
                "severity": "high",
            }

            report = self.enrichment_svc.enrich_issue(
                issue=raw_issue,
                ast_dict=ast_res["ast"],
                source_code=py_source,
            )

            self.assertEqual(report.function_name, "compute_average")
            self.assertEqual(report.class_name, "MathService")
            self.assertIn("MathService.compute_average()", report.title)
            self.assertTrue(len(report.codeSnippet) >= 1)
            self.assertTrue(any(line.isErr and "total / count" in line.text for line in report.codeSnippet))
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_ast_context_extraction_javascript(self):
        js_source = textwrap.dedent("""\
            class OrderManager {
                processDiscount(price, factor) {
                    if (factor == 0) {
                        return 0;
                    }
                    return price / factor;
                }
            }
        """)
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False, encoding="utf-8") as f:
            f.write(js_source)
            f_path = f.name

        try:
            ast_res = self.ast_gen.generate_ast(f_path, "JavaScript")
            self.assertTrue(ast_res["success"])

            raw_issue = {
                "rule_id": "JS_EQ_001",
                "issue_type": "loose_equality",
                "message": "Loose equality used",
                "file_path": f_path,
                "line_number": 3,
                "column": 12,
                "code_snippet": "factor == 0",
                "evidence": {"operator": "=="},
                "severity": "medium",
            }

            report = self.enrichment_svc.enrich_issue(
                issue=raw_issue,
                ast_dict=ast_res["ast"],
                source_code=js_source,
            )

            self.assertEqual(report.function_name, "processDiscount")
            self.assertEqual(report.class_name, "OrderManager")
            self.assertEqual(report.language, "JavaScript")
        finally:
            Path(f_path).unlink(missing_ok=True)

    def test_ast_context_extraction_java(self):
        java_source = textwrap.dedent("""\
            public class DataProcessor {
                public void handleData(String path) {
                    try {
                        int x = 10;
                    } catch (Exception e) {}
                }
            }
        """)
        with tempfile.NamedTemporaryFile(suffix=".java", mode="w", delete=False, encoding="utf-8") as f:
            f.write(java_source)
            f_path = f.name

        try:
            ast_res = self.ast_gen.generate_ast(f_path, "Java")
            self.assertTrue(ast_res["success"])

            raw_issue = {
                "rule_id": "JAVA_EXC_001",
                "issue_type": "empty_catch",
                "message": "Empty catch block",
                "file_path": f_path,
                "line_number": 5,
                "column": 10,
                "code_snippet": "catch (Exception e) {}",
                "evidence": {"exception_type": "Exception"},
                "severity": "medium",
            }

            report = self.enrichment_svc.enrich_issue(
                issue=raw_issue,
                ast_dict=ast_res["ast"],
                source_code=java_source,
            )

            self.assertEqual(report.function_name, "handleData")
            self.assertEqual(report.class_name, "DataProcessor")
            self.assertEqual(report.language, "Java")
        finally:
            Path(f_path).unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # 3. Structured Evidence Collection
    # -------------------------------------------------------------------------

    def test_structured_evidence_collection(self):
        raw_issue = {
            "rule_id": "PY_RES_001",
            "issue_type": "unclosed_resource",
            "message": "open() called outside with-statement",
            "file_path": "src/io_handler.py",
            "line_number": 25,
            "column": 8,
            "code_snippet": "f = open(path, 'r')",
            "evidence": {"call": "open", "arg": "path"},
            "severity": "high",
        }

        classification = {
            "severity": {"label": "high", "confidence": 0.95, "probabilities": {"high": 0.95, "critical": 0.05}},
            "priority": {"label": "p1", "confidence": 0.91, "probabilities": {"p1": 0.91, "p2": 0.09}},
            "needs_review": False,
        }

        report = self.enrichment_svc.enrich_issue(
            issue=raw_issue,
            classification=classification,
        )

        evidence_types = [ev.type for ev in report.evidence]
        self.assertIn("static_analysis", evidence_types)
        self.assertIn("source", evidence_types)
        self.assertIn("classification", evidence_types)

        # Check classification evidence
        classif_ev = next(ev for ev in report.evidence if ev.type == "classification")
        self.assertEqual(classif_ev.data["confidence"], 0.93)
        self.assertFalse(classif_ev.data["needs_review"])

        # Check static analysis evidence
        static_ev = next(ev for ev in report.evidence if ev.type == "static_analysis")
        self.assertEqual(static_ev.data["rule_id"], "PY_RES_001")
        self.assertEqual(static_ev.data["rule_evidence"]["call"], "open")

    # -------------------------------------------------------------------------
    # 4. Human-Readable Explanation Answering All 8 Criteria
    # -------------------------------------------------------------------------

    def test_explanation_answers_all_eight_criteria(self):
        raw_issue = {
            "rule_id": "JS_AWA_001",
            "issue_type": "await_in_loop",
            "message": "await inside loop executes sequentially instead of concurrently.",
            "file_path": "src/services/api.js",
            "line_number": 44,
            "column": 12,
            "code_snippet": "await fetchItem(items[i])",
            "evidence": {"loop_type": "for_statement"},
            "severity": "medium",
        }

        report = self.enrichment_svc.enrich_issue(issue=raw_issue)
        exp = report.explanation

        # 1. What is the issue?
        self.assertTrue(len(exp.what) > 10)
        self.assertIn("await inside loop", exp.what)

        # 2. Where is it?
        self.assertIn("src/services/api.js", exp.where)
        self.assertIn("line 44", exp.where)

        # 3. Why was it detected?
        self.assertIn("JS_AWA_001", exp.why)

        # 4. What evidence supports it?
        self.assertIn("await fetchItem(items[i])", exp.evidence_summary)
        self.assertIn("loop_type='for_statement'", exp.evidence_summary)

        # 5. What category does it belong to?
        self.assertIn("await_in_loop", exp.category)

        # 6. How severe is it?
        self.assertIn("MEDIUM", exp.severity_assessment)

        # 7. How important is it to fix?
        self.assertIn("Priority", exp.importance_assessment)

        # 8. Is it similar or duplicate to another issue?
        self.assertIn("independent finding", exp.similarity_or_duplicate)

        # Full narrative
        self.assertTrue(len(exp.full_text) > 100)
        self.assertIn("### Issue Overview", exp.full_text)

    # -------------------------------------------------------------------------
    # 5. Batch Deduplication and Similarity Linking
    # -------------------------------------------------------------------------

    def test_batch_enrichment_deduplication_and_similarity(self):
        issues = [
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero in calculation",
                "file_path": "src/calc.py",
                "line_number": 10,
                "column": 4,
                "code_snippet": "a / b",
                "evidence": {"operator": "/"},
                "severity": "high",
            },
            # Exact duplicate at same file, line, rule
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero in calculation",
                "file_path": "src/calc.py",
                "line_number": 10,
                "column": 4,
                "code_snippet": "a / b",
                "evidence": {"operator": "/"},
                "severity": "high",
            },
            # Similar occurrence of same rule in another file
            {
                "rule_id": "PY_DIV_001",
                "issue_type": "division_by_zero",
                "message": "Division by zero in metrics",
                "file_path": "src/metrics.py",
                "line_number": 55,
                "column": 8,
                "code_snippet": "total / n",
                "evidence": {"operator": "/"},
                "severity": "high",
            },
            # Distinct independent issue
            {
                "rule_id": "PY_RES_001",
                "issue_type": "unclosed_resource",
                "message": "File open not closed",
                "file_path": "src/io.py",
                "line_number": 20,
                "column": 0,
                "code_snippet": "open(p)",
                "evidence": {"call": "open"},
                "severity": "medium",
            },
        ]

        reports = self.enrichment_svc.enrich_issues_batch(issues, repository_id="repo-test")

        self.assertEqual(len(reports), 4)

        # Issue 1: Primary original
        self.assertFalse(reports[0].similarity.is_duplicate)
        self.assertIsNone(reports[0].duplicate_of)

        # Issue 2: Flagged as duplicate of Issue 1
        self.assertTrue(reports[1].similarity.is_duplicate)
        self.assertEqual(reports[1].similarity.duplicate_of, reports[0].id)
        self.assertEqual(reports[1].similarity.relationship_type, "duplicate")

        # Issue 3: Flagged as similar (same rule across different files)
        self.assertFalse(reports[2].similarity.is_duplicate)
        self.assertEqual(reports[2].similarity.relationship_type, "similar")
        self.assertTrue(len(reports[2].similar_issues) >= 1)

        # Issue 4: Independent
        self.assertFalse(reports[3].similarity.is_duplicate)
        self.assertEqual(reports[3].similarity.relationship_type, "independent")

    # -------------------------------------------------------------------------
    # 6. Graceful Degradation on Missing Optional Data
    # -------------------------------------------------------------------------

    def test_missing_optional_data_does_not_crash(self):
        bare_issue = {
            "rule_id": "UNKNOWN_RULE",
            "issue_type": "generic_error",
            "message": "Something went wrong",
            "file_path": "orphan_file.txt",
            "line_number": 1,
        }

        # Enrich with completely missing AST, source, classification, similarity
        report = self.enrichment_svc.enrich_issue(
            issue=bare_issue,
            ast_dict=None,
            source_code=None,
            classification=None,
            similarity_info=None,
        )

        self.assertIsInstance(report, EnrichedBugReport)
        self.assertEqual(report.file_path, "orphan_file.txt")
        self.assertEqual(report.line, 1)
        self.assertEqual(report.category, "generic_error")
        self.assertEqual(report.confidence, 1.0)
        self.assertIsNone(report.classification)
        self.assertIsNone(report.function_name)
        self.assertIsNone(report.class_name)
        self.assertFalse(report.similarity.is_duplicate)

        # Serializes cleanly to JSON
        json_str = json.dumps(report.model_dump(mode="json"))
        self.assertIn("orphan_file.txt", json_str)

    # -------------------------------------------------------------------------
    # 7. Remediation / Suggested Fix Generation
    # -------------------------------------------------------------------------

    def test_remediation_diff_generation_for_rules(self):
        rules_to_test = [
            ("PY_DIV_001", "a / b", {"right_operand": "b"}, "Python"),
            ("PY_RES_001", "open(path, 'r')", {}, "Python"),
            ("PY_EXC_001", "except:", {}, "Python"),
            ("PY_ASS_001", "assert x > 0", {}, "Python"),
            ("PY_MUT_001", "def f(items=[]):", {"param_name": "items"}, "Python"),
            ("JS_EQ_001", "x == y", {"operator": "=="}, "JavaScript"),
            ("JS_AWA_001", "await fetch()", {}, "JavaScript"),
            ("JAVA_EXC_001", "catch (Exception e) {}", {}, "Java"),
            ("JAVA_EQ_001", "s1 == s2", {"left_operand": "s1", "right_operand": "s2"}, "Java"),
            ("JAVA_RES_001", "new FileReader(path)", {}, "Java"),
            ("JAVA_LOOP_001", "while (true) {}", {}, "Java"),
        ]

        for rule_id, snippet, ev, lang in rules_to_test:
            fix = self.enrichment_svc._generate_suggested_fix(
                rule_id=rule_id,
                issue_type=rule_id.lower(),
                snippet=snippet,
                evidence=ev,
                language=lang,
            )
            self.assertIsNotNone(fix)
            self.assertTrue(len(fix.note) > 0, f"Fix note empty for {rule_id}")

    # -------------------------------------------------------------------------
    # 8. End-to-End Bug Report Service & Summary Stats
    # -------------------------------------------------------------------------

    def test_end_to_end_bug_report_service_generation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir)

            py_file = repo_path / "calc.py"
            py_file.write_text(
                "def divide(a, b):\n    return a / 0\n",
                encoding="utf-8"
            )

            js_file = repo_path / "app.js"
            js_file.write_text(
                "function test(x, y) {\n    return x == y;\n}\n",
                encoding="utf-8"
            )

            ast_res = self.ast_gen.generate_ast_for_repository(str(repo_path))
            result = bug_report_service.generate_repository_reports(
                ast_result=ast_res,
                repository_id="test-repo-100",
                repository_path=str(repo_path),
            )

            self.assertIn("bug_reports", result)
            self.assertIn("summary_stats", result)
            self.assertIn("total_reports", result)
            self.assertIn("candidate_issues", result)
            self.assertIn("ast_analysis", result)

            stats = result["summary_stats"]
            self.assertEqual(stats["total_bugs"], result["total_reports"])
            self.assertTrue(result["total_reports"] >= 2)
            self.assertTrue(stats["total_files_analyzed"] >= 2)

            # Check pure JSON serializability
            serialized = json.dumps(result)
            self.assertTrue(len(serialized) > 200)

    # -------------------------------------------------------------------------
    # 9. RepositoryAnalysisService Full Pipeline Integration
    # -------------------------------------------------------------------------

    def test_repository_analysis_service_pipeline_backward_compatibility(self):
        import asyncio

        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_path = Path(tmp_dir)
            source = repo_path / "module.py"
            source.write_text(
                "def read(path):\n    f = open(path, 'r')\n    return f.read()\n",
                encoding="utf-8"
            )

            svc = RepositoryAnalysisService()
            response = asyncio.run(svc.analyze_repository(str(repo_path), repository_id="repo-xyz"))

            # Check legacy keys exist and match expectations
            self.assertEqual(response["repository_path"], str(repo_path))
            self.assertEqual(response["repository_id"], "repo-xyz")
            self.assertIn("ast_analysis", response)
            self.assertIn("candidate_issues", response)
            self.assertIn("total_candidate_issues", response)
            self.assertIn("summary", response)
            self.assertIn("files", response)
            self.assertIn("static_analysis", response)

            # Check new enriched bug report keys
            self.assertIn("bug_reports", response)
            self.assertIn("total_reports", response)
            self.assertIn("summary_stats", response)
            self.assertTrue(len(response["bug_reports"]) >= 1)

            first_report = response["bug_reports"][0]
            self.assertEqual(first_report["static_analysis"]["rule_id"], "PY_RES_001")
            self.assertIn("called outside", first_report["description"])
            self.assertIn("what", first_report["explanation"])
            self.assertIn("where", first_report["explanation"])
            self.assertIn("why", first_report["explanation"])

            # Verify entire response is JSON serializable
            json.dumps(response)


if __name__ == "__main__":
    unittest.main(verbosity=2)
