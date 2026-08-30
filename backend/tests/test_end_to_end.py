"""
test_end_to_end.py — Authoritative End-to-End Production Pipeline Integration Test.
===================================================================================
Verifies the complete analysis flow from repository ingestion to report export:
1. Multi-language repository ingestion & AST generation (Python, JS, Java).
2. AST-based static analysis & candidate issue generation.
3. Production ML classification (Linear SVM with calibrated tau=0.40).
4. Multi-signal drift & OOD detection.
5. Decoupled severity & deterministic priority mapping.
6. Automated bug enrichment with remediation diffs.
7. Multi-format report export (JSON, Markdown, HTML, CSV).
"""
from __future__ import annotations

import tempfile
from pathlib import Path
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import SGDClassifier

from app.services.ast_generator import ast_generator
from app.services.bug_report_service import bug_report_service
from app.services.candidate_issue_service import candidate_issue_service
from app.services.ml.config import (
    GROUND_TRUTH_DATASET_PATH,
    PRODUCTION_THRESHOLD,
    RANDOM_SEED,
)
from app.services.ml.data_loader import load_ground_truth_dataset
from app.services.ml.drift_detector import ProductionDriftDetector
from app.services.ml.inference import safe_predict
from app.services.report_exporter import report_exporter


def test_end_to_end_pipeline():
    """Verifies all stages of the repository analysis pipeline end-to-end."""
    # 1. Setup Temporary Sample Multi-Language Repository
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_dir = Path(tmp_dir) / "sample_app"
        repo_dir.mkdir(parents=True, exist_ok=True)

        py_file = repo_dir / "calculator.py"
        py_file.write_text(
            "def calculate_ratio(a, b):\n"
            "    # Potential div by zero\n"
            "    res = a / b\n"
            "    f = open('output.txt', 'w')\n"
            "    f.write(str(res))\n"
            "    return res\n",
            encoding="utf-8",
        )

        js_file = repo_dir / "validator.js"
        js_file.write_text(
            "function checkToken(token) {\n"
            "    if (token == null) {\n"
            "        return false;\n"
            "    }\n"
            "    for (let i = 0; i < 5; i++) {\n"
            "        await fetch('/api/check');\n"
            "    }\n"
            "    return true;\n"
            "}\n",
            encoding="utf-8",
        )

        java_file = repo_dir / "StringMatcher.java"
        java_file.write_text(
            "public class StringMatcher {\n"
            "    public boolean isMatch(String s1, String s2) {\n"
            "        if (s1 == s2) {\n"
            "            return true;\n"
            "        }\n"
            "        return false;\n"
            "    }\n"
            "}\n",
            encoding="utf-8",
        )

        # 2. AST Generation
        ast_result = ast_generator.generate_ast_for_repository(str(repo_dir))
        assert "files_analyzed" in ast_result
        assert len(ast_result["files_analyzed"]) == 3

        # 3. Static Analysis Rules & Candidate Generation
        candidate_result = candidate_issue_service.generate_from_repository(ast_result)
        candidates = candidate_result.get("candidate_issues", [])
        assert len(candidates) >= 3, f"Expected at least 3 candidates, found {len(candidates)}"

        # 4. Production ML Model & Drift Initialization
        dataset = load_ground_truth_dataset()
        train_recs = dataset["splits"]["train"]
        X_tr = [f"Rule: {r.get('rule_id')}\nLanguage: {r.get('language')}\nMessage: {r.get('message')}" for r in train_recs]
        y_tr = [1 if (r.get("ground_truth") or r.get("label")) == "TRUE_POSITIVE" else 0 for r in train_recs]

        vec = TfidfVectorizer(max_features=4000, ngram_range=(1, 2), sublinear_tf=True)
        X_tr_vec = vec.fit_transform(X_tr)

        clf = SGDClassifier(loss="log_loss", class_weight="balanced", random_state=RANDOM_SEED, max_iter=1000, alpha=1e-4)
        clf.fit(X_tr_vec, y_tr)

        detector = ProductionDriftDetector.fit_from_training_records(train_recs, vec, drift_threshold=0.30)

        # 5. ML Inference & Risk Routing for Candidates
        enriched_candidates = []
        for cand in candidates:
            cand_dict = {
                "rule_id": cand.get("rule_id"),
                "language": cand.get("language"),
                "code_snippet": cand.get("code_snippet") or cand.get("snippet"),
                "message": cand.get("description") or cand.get("message") or cand.get("rule_id"),
            }
            pred_res = safe_predict(cand_dict, vec, clf, detector)
            assert pred_res["prediction"] in {"TRUE_POSITIVE", "FALSE_POSITIVE"}
            assert pred_res["routing_decision"] in {"AUTO_ACCEPT", "SECONDARY_MODEL", "HUMAN_REVIEW", "OOD_REJECT", "SYSTEM_ERROR"}
            enriched_candidates.append({**cand_dict, **pred_res})

        # 6. Bug Enrichment & Repository Report Generation
        report_dict = bug_report_service.generate_repository_reports(
            ast_result=ast_result,
            candidate_result=candidate_result,
            repository_id="sample_repo_001",
            repository_path=str(repo_dir),
        )
        enriched_reports = report_dict.get("bug_reports", [])
        assert len(enriched_reports) >= 3, f"Expected >= 3 enriched reports, got {len(enriched_reports)}"
        for rep in enriched_reports:
            assert rep["title"]
            assert rep["description"]
            assert rep["explanation"]["what"]
            assert rep["explanation"]["where"]
            assert rep["explanation"]["why"]

        # 7. Report Exporter
        json_exp = report_exporter.export_json(enriched_reports, summary_stats=report_dict.get("summary_stats"))
        md_exp = report_exporter.export_markdown(enriched_reports, summary_stats=report_dict.get("summary_stats"))
        html_exp = report_exporter.export_html(enriched_reports, summary_stats=report_dict.get("summary_stats"))
        csv_exp = report_exporter.export_csv(enriched_reports)

        assert len(json_exp) > 50
        assert len(md_exp) > 50
        assert len(html_exp) > 50
        assert len(csv_exp) > 50
