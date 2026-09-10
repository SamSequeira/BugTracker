"""
bug_enrichment_service.py
-------------------------
Bug Enrichment Service.
Combines Static Analysis findings, AST metadata, ML classification,
Severity/Priority predictions, and Similarity/Deduplication into complete
structured bug reports with actionable explanations.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from app.schemas.bug_report import (
    BugExplanation,
    ClassificationResult,
    CodeContext,
    CodeLine,
    EnrichedBugReport,
    EvidenceItem,
    LocationInfo,
    SimilarBugMatch,
    SimilarityInfo,
    StaticAnalysisFinding,
    SuggestedFix,
    TestHarnessResultSchema,
    ValidationStatus,
)
from app.services.bug_similarity_service import BugSimilarityService
from app.services.issue_classifier.config import ID_TO_PRIORITY, ID_TO_SEVERITY
from app.services.language_detector import detect_language

logger = logging.getLogger(__name__)

PRIORITY_DISPLAY_MAP = {
    "p1": "P1 • Fix now",
    "p2": "P2 • Fix this week",
    "p3": "P3 • Backlog",
    "p4": "P4 • Low priority",
}

SEVERITY_IMPACT_MAP = {
    "critical": "Critical vulnerability or fatal failure that could compromise system security or cause immediate crash.",
    "high": "High-risk issue that likely leads to runtime exceptions, data corruption, or resource leakage in production.",
    "medium": "Moderate issue that violates reliability best practices or creates unpredictable edge-case behavior.",
    "low": "Low-severity code quality or style deviation with minor operational impact.",
}

PRIORITY_URGENCY_MAP = {
    "p1": "Immediate remediation required. Block release until resolved.",
    "p2": "High urgency. Fix in current development sprint.",
    "p3": "Moderate urgency. Schedule for upcoming backlog iteration.",
    "p4": "Low urgency. Address during routine maintenance or refactoring.",
}

RULE_TITLE_TEMPLATES = {
    "PY_DIV_001": "Potential Division by Zero in {scope}",
    "PY_RES_001": "Unclosed File Resource outside with-statement in {scope}",
    "PY_EXC_001": "Bare except clause catching all exceptions in {scope}",
    "PY_ASS_001": "Assert statement used in production code in {scope}",
    "PY_MUT_001": "Mutable default argument in function definition {scope}",
    "JS_DIV_001": "Potential Division by Zero in {scope}",
    "JS_EQ_001": "Loose equality comparison (== / !=) in {scope}",
    "JS_AWA_001": "Sequential await expression inside loop in {scope}",
    "JAVA_DIV_001": "Potential Division by Zero in {scope}",
    "JAVA_EXC_001": "Empty catch block swallowing exceptions in {scope}",
    "JAVA_EQ_001": "String reference equality comparison (==) in {scope}",
    "JAVA_RES_001": "Unclosed resource outside try-with-resources in {scope}",
    "JAVA_LOOP_001": "Infinite while-loop without exit condition in {scope}",
}


class BugEnrichmentService:
    """
    Enriches candidate issues with comprehensive AST context, static analysis findings,
    ML classifications, similarity detection, evidence aggregation, and remediation advice.
    """

    def __init__(self, similarity_service: Optional[BugSimilarityService] = None) -> None:
        self._similarity_service = similarity_service

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def enrich_issue(
        self,
        issue: Union[Dict[str, Any], Any],
        ast_dict: Optional[Dict[str, Any]] = None,
        source_code: Optional[str] = None,
        repository_id: Optional[str] = None,
        repository_path: Optional[str] = None,
        classification: Optional[Dict[str, Any]] = None,
        similarity_info: Optional[Dict[str, Any]] = None,
        index: int = 1,
    ) -> EnrichedBugReport:
        """
        Enrich a single candidate issue into a complete Bug Report.
        """
        raw_issue = self._to_dict(issue)

        rule_id = str(raw_issue.get("rule_id", "UNKNOWN_RULE"))
        issue_type = str(raw_issue.get("issue_type", "general_issue"))
        message = str(raw_issue.get("message", "Potential issue detected"))
        file_path = str(raw_issue.get("file_path", ""))
        line_number = int(raw_issue.get("line_number", 1) or 1)
        column = int(raw_issue.get("column", 0) or 0)
        code_snippet = str(raw_issue.get("code_snippet", ""))
        evidence_dict = raw_issue.get("evidence", {})
        if not isinstance(evidence_dict, dict):
            evidence_dict = {}

        # 1. Determine Language
        language = detect_language(file_path)
        if language == "Unsupported" or not language:
            language = raw_issue.get("language", "Unknown")

        # 2. Extract AST context (Function, Class, Node coordinates)
        func_name, class_name, ast_location = self._extract_ast_context(
            ast_dict, line_number, column
        )

        # 3. Location Information
        location = LocationInfo(
            line=line_number,
            column=column,
            start_byte=ast_location.get("start_byte"),
            end_byte=ast_location.get("end_byte"),
            start_line=ast_location.get("start_line", line_number - 1),
            end_line=ast_location.get("end_line", line_number - 1),
        )

        # 4. Generate Stable Issue ID
        issue_id = self._generate_stable_id(
            repository_id or repository_path or "repo",
            file_path,
            line_number,
            rule_id,
            index,
        )

        # 5. Extract Scope and Title
        scope_str = self._format_scope(func_name, class_name, file_path)
        title = self._generate_title(rule_id, issue_type, scope_str, message)

        # 6. Preserve Static Analysis Finding
        static_finding = StaticAnalysisFinding(
            rule_id=rule_id,
            rule_name=rule_id,
            issue_type=issue_type,
            message=message,
            severity=str(raw_issue.get("severity", "medium")).lower(),
            evidence=evidence_dict,
            code_snippet=code_snippet,
        )

        # 7. Classification, Severity & Priority Resolution
        classif_result, final_severity, final_priority, confidence = self._resolve_classification(
            raw_issue, classification
        )
        priority_formatted = PRIORITY_DISPLAY_MAP.get(final_priority.lower(), f"{final_priority.upper()}")

        # 8. Similarity & Deduplication
        similarity_data = self._resolve_similarity(
            raw_issue, issue_id, repository_id, similarity_info
        )

        # 9. Code Snippet Context Window (for UI)
        surrounding_code = self._build_surrounding_code(
            source_code, line_number, code_snippet
        )

        # 10. Suggested Fix / Remediation
        suggested_fix = self._generate_suggested_fix(
            rule_id, issue_type, code_snippet, evidence_dict, language
        )

        # 11. Aggregate Structured Evidence Collection
        evidence_list = self._aggregate_evidence(
            static_finding=static_finding,
            file_path=file_path,
            line_number=line_number,
            column=column,
            code_snippet=code_snippet,
            ast_location=ast_location,
            func_name=func_name,
            class_name=class_name,
            classification=classif_result,
            similarity=similarity_data,
        )

        # 12. Synthesize 8-Criteria Human-Readable Explanation
        explanation = self._build_explanation(
            title=title,
            rule_id=rule_id,
            issue_type=issue_type,
            file_path=file_path,
            line_number=line_number,
            column=column,
            scope_str=scope_str,
            message=message,
            code_snippet=code_snippet,
            evidence_dict=evidence_dict,
            category=issue_type,
            severity=final_severity,
            priority=final_priority,
            priority_formatted=priority_formatted,
            similarity=similarity_data,
            suggested_fix=suggested_fix,
        )

        # 13. Repository metadata
        repo_meta = {
            "id": repository_id or "",
            "path": repository_path or "",
            "name": self._extract_repo_name(repository_path or repository_id or ""),
        }

        # Build complete EnrichedBugReport model
        report = EnrichedBugReport(
            id=issue_id,
            issue_id=issue_id,
            title=title,
            description=message,
            repository=repo_meta,
            file_path=file_path,
            file=file_path,
            line=line_number,
            location=location,
            language=language,
            function_name=func_name,
            class_name=class_name,
            category=issue_type,
            severity=final_severity,
            priority=final_priority,
            priority_formatted=priority_formatted,
            confidence=confidence,
            status="Open",
            static_analysis=static_finding,
            candidate_issue=raw_issue,
            classification=classif_result,
            evidence=evidence_list,
            similarity=similarity_data,
            similar_issues=[m.model_dump() for m in similarity_data.similar_issues],
            duplicate_of=similarity_data.duplicate_of,
            codeSnippet=surrounding_code,
            suggestedFix=suggested_fix,
            # Feature 2: ai_confidence mirrors the ML confidence; validation_status
            # starts UNVERIFIED — it's promoted to VERIFIED by the pipeline
            # coordinator after test_generation_service confirms FAIL→PASS.
            ai_confidence=confidence,
            validation_status=ValidationStatus.UNVERIFIED,
            test_harness_result=None,
            explanation=explanation,
            human_readable_explanation=explanation.full_text,
        )

        return report

    def enrich_issues_batch(
        self,
        issues: List[Union[Dict[str, Any], Any]],
        ast_for_repository: Optional[Dict[str, Any]] = None,
        source_files: Optional[Dict[str, str]] = None,
        repository_id: Optional[str] = None,
        repository_path: Optional[str] = None,
        classifications: Optional[List[Dict[str, Any]]] = None,
    ) -> List[EnrichedBugReport]:
        """
        Enrich a batch of candidate issues, resolving AST context and intra-batch duplicates.
        """
        if not issues:
            return []

        # Index ASTs by file path for fast lookup
        ast_map: Dict[str, Dict[str, Any]] = {}
        if ast_for_repository and "files_analyzed" in ast_for_repository:
            for file_entry in ast_for_repository["files_analyzed"]:
                if file_entry.get("success") and "file" in file_entry:
                    ast_map[file_entry["file"]] = file_entry.get("ast", {})

        reports: List[EnrichedBugReport] = []
        seen_keys: Dict[Tuple[str, int, str], str] = {}  # (file, line, rule) -> issue_id
        seen_rules: Dict[str, List[str]] = {}  # rule_id -> [issue_id, ...]

        for idx, issue in enumerate(issues, start=1):
            raw = self._to_dict(issue)
            file_path = raw.get("file_path", "")
            file_ast = ast_map.get(file_path)
            file_source = source_files.get(file_path) if source_files else None
            classif = classifications[idx - 1] if classifications and idx - 1 < len(classifications) else None

            report = self.enrich_issue(
                issue=raw,
                ast_dict=file_ast,
                source_code=file_source,
                repository_id=repository_id,
                repository_path=repository_path,
                classification=classif,
                index=idx,
            )

            # Intra-batch similarity / duplicate detection
            dup_key = (file_path, report.line, report.static_analysis.rule_id)
            if dup_key in seen_keys:
                primary_id = seen_keys[dup_key]
                report.similarity.is_duplicate = True
                report.similarity.duplicate_of = primary_id
                report.similarity.relationship_type = "duplicate"
                report.duplicate_of = primary_id
            else:
                seen_keys[dup_key] = report.id

            # Link similar issues with same rule across different locations
            rule_id = report.static_analysis.rule_id
            if rule_id in seen_rules:
                for prior_id in seen_rules[rule_id]:
                    if prior_id != report.id and not any(m.issue_id == prior_id for m in report.similarity.similar_issues):
                        match = SimilarBugMatch(
                            issue_id=prior_id,
                            repository_id=repository_id,
                            similarity=0.90,
                            issue_type=report.category,
                            message=f"Same rule ({rule_id}) detected in codebase",
                            file_path=file_path,
                            line_number=report.line,
                        )
                        report.similarity.similar_issues.append(match)
                        if report.similarity.relationship_type == "independent":
                            report.similarity.relationship_type = "similar"
                seen_rules[rule_id].append(report.id)
            else:
                seen_rules[rule_id] = [report.id]

            # Update similar_issues dict list
            report.similar_issues = [m.model_dump() for m in report.similarity.similar_issues]
            reports.append(report)

        return reports

    # =========================================================================
    # INTERNAL HELPERS
    # =========================================================================

    @staticmethod
    def _to_dict(issue: Any) -> Dict[str, Any]:
        if hasattr(issue, "to_dict"):
            return issue.to_dict()
        if isinstance(issue, dict):
            return dict(issue)
        return getattr(issue, "__dict__", {})

    @staticmethod
    def _generate_stable_id(repo: str, file_path: str, line: int, rule_id: str, index: int) -> str:
        content = f"{repo}:{file_path}:{line}:{rule_id}:{index}".encode("utf-8")
        hash_val = hashlib.sha256(content).hexdigest()[:4].upper()
        return f"BUG-2026-{index:04d}"

    @staticmethod
    def _extract_repo_name(path_or_id: str) -> str:
        if not path_or_id:
            return "Repository"
        clean = path_or_id.replace("\\", "/").rstrip("/")
        name = clean.split("/")[-1]
        return name if name else "Repository"

    @staticmethod
    def _format_scope(func: Optional[str], cls: Optional[str], file_path: str) -> str:
        if cls and func:
            return f"{cls}.{func}()"
        if func:
            return f"{func}()"
        if cls:
            return f"class {cls}"
        file_name = file_path.replace("\\", "/").split("/")[-1] if file_path else "module"
        return f"{file_name}"

    @classmethod
    def _generate_title(cls, rule_id: str, issue_type: str, scope: str, message: str) -> str:
        if rule_id in RULE_TITLE_TEMPLATES:
            return RULE_TITLE_TEMPLATES[rule_id].format(scope=scope)
        clean_type = issue_type.replace("_", " ").title()
        return f"{clean_type} in {scope}"

    # -------------------------------------------------------------------------
    # AST Context Extraction
    # -------------------------------------------------------------------------

    def _extract_ast_context(
        self,
        ast_dict: Optional[Dict[str, Any]],
        line: int,
        col: int,
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """
        Traverse AST to find enclosing function and class symbols, plus node coordinates.
        line is 1-based; tree-sitter lines are 0-based.
        """
        if not ast_dict or not isinstance(ast_dict, dict):
            return None, None, {}

        target_line_0 = line - 1
        found_func: Optional[str] = None
        found_class: Optional[str] = None
        node_coords: Dict[str, Any] = {}

        def _traverse(node: Dict[str, Any], current_func: Optional[str], current_class: Optional[str]):
            nonlocal found_func, found_class, node_coords
            start = node.get("start", {})
            end = node.get("end", {})
            start_l = start.get("line", -1)
            end_l = end.get("line", -1)

            if start_l <= target_line_0 <= end_l:
                node_type = node.get("type", "")

                # Check for class definition
                if node_type in ("class_definition", "class_declaration", "class"):
                    name = self._extract_identifier(node)
                    if name:
                        current_class = name

                # Check for function/method definition
                elif node_type in (
                    "function_definition",
                    "function_declaration",
                    "method_declaration",
                    "method_definition",
                    "arrow_function",
                ):
                    name = self._extract_identifier(node)
                    if name:
                        current_func = name

                # Record deepest matching node coordinates
                node_coords = {
                    "node_type": node_type,
                    "start_byte": start.get("byte"),
                    "end_byte": end.get("byte"),
                    "start_line": start_l,
                    "end_line": end_l,
                }
                found_func = current_func
                found_class = current_class

                for child in node.get("children", []):
                    _traverse(child, current_func, current_class)

        _traverse(ast_dict, None, None)
        return found_func, found_class, node_coords

    @staticmethod
    def _extract_identifier(node: Dict[str, Any]) -> Optional[str]:
        """Extract function or class name from AST node children."""
        for child in node.get("children", []):
            ctype = child.get("type", "")
            if ctype in ("identifier", "property_identifier", "name", "type_identifier"):
                text = child.get("text", "").strip()
                if text:
                    return text
        return None

    # -------------------------------------------------------------------------
    # Classification, Severity & Priority Resolution
    # -------------------------------------------------------------------------

    def _resolve_classification(
        self,
        raw_issue: Dict[str, Any],
        classification: Optional[Dict[str, Any]],
    ) -> Tuple[Optional[ClassificationResult], str, str, float]:
        """Extract or resolve ML predictions, severity, priority, and confidence."""
        classif_data = classification or raw_issue.get("classification")
        raw_severity = str(raw_issue.get("severity", "medium")).lower()

        if classif_data and isinstance(classif_data, dict):
            sev_block = classif_data.get("severity", {})
            prio_block = classif_data.get("priority", {})
            sev_label = str(sev_block.get("label", raw_severity)).lower()
            prio_label = str(prio_block.get("label", "p3")).lower()
            conf_s = float(sev_block.get("confidence", 0.90))
            conf_p = float(prio_block.get("confidence", 0.85))
            overall_conf = round((conf_s + conf_p) / 2.0, 4)
            needs_review = bool(classif_data.get("needs_review", False))

            result = ClassificationResult(
                category=str(raw_issue.get("issue_type", "general_issue")),
                confidence=overall_conf,
                severity_prediction=sev_block if isinstance(sev_block, dict) else {},
                priority_prediction=prio_block if isinstance(prio_block, dict) else {},
                needs_review=needs_review,
            )
            return result, sev_label, prio_label, overall_conf

        # Default mapping from static analysis severity
        default_priority_map = {
            "critical": "p1",
            "high": "p2",
            "medium": "p3",
            "low": "p4",
        }
        prio_label = default_priority_map.get(raw_severity, "p3")
        return None, raw_severity, prio_label, 1.0

    # -------------------------------------------------------------------------
    # Similarity Resolution
    # -------------------------------------------------------------------------

    def _resolve_similarity(
        self,
        raw_issue: Dict[str, Any],
        issue_id: str,
        repository_id: Optional[str],
        similarity_info: Optional[Dict[str, Any]],
    ) -> SimilarityInfo:
        """Resolve similarity results from service or attached metadata."""
        raw_sim = similarity_info or raw_issue.get("similarity")
        if isinstance(raw_sim, dict):
            is_dup = bool(raw_sim.get("duplicate", False))
            score = float(raw_sim.get("similarity", 0.0))
            raw_matches = raw_sim.get("similar_bugs", [])
            matches = []
            if isinstance(raw_matches, list):
                for m in raw_matches:
                    if isinstance(m, dict):
                        matches.append(SimilarBugMatch(
                            issue_id=str(m.get("issue_id", "")),
                            repository_id=str(m.get("repository_id", "")),
                            similarity=float(m.get("similarity", 0.0)),
                            issue_type=m.get("issue_type"),
                            message=m.get("message"),
                            file_path=m.get("file_path"),
                            line_number=int(m.get("line_number", 0)) if m.get("line_number") else None,
                        ))
            rel_type = "duplicate" if is_dup else ("similar" if score >= 0.70 else ("related" if score >= 0.40 else "independent"))
            return SimilarityInfo(
                is_duplicate=is_dup,
                duplicate_of=matches[0].issue_id if is_dup and matches else None,
                highest_similarity=score,
                relationship_type=rel_type,
                similar_issues=matches,
            )

        return SimilarityInfo(
            is_duplicate=False,
            duplicate_of=None,
            highest_similarity=0.0,
            relationship_type="independent",
            similar_issues=[],
        )

    # -------------------------------------------------------------------------
    # Surrounding Code Window
    # -------------------------------------------------------------------------

    @staticmethod
    def _build_surrounding_code(
        source_code: Optional[str],
        target_line: int,
        fallback_snippet: str,
    ) -> List[CodeLine]:
        """Format 3-5 line window around target line for UI inspection."""
        if not source_code:
            if fallback_snippet:
                return [CodeLine(num=target_line, text=fallback_snippet, isErr=True)]
            return []

        lines = source_code.splitlines()
        total = len(lines)
        if total == 0:
            return []

        start_idx = max(0, target_line - 3)
        end_idx = min(total, target_line + 2)

        result: List[CodeLine] = []
        for i in range(start_idx, end_idx):
            line_num = i + 1
            result.append(CodeLine(
                num=line_num,
                text=lines[i],
                isErr=(line_num == target_line),
            ))
        return result

    # -------------------------------------------------------------------------
    # Suggested Remediation
    # -------------------------------------------------------------------------

    @staticmethod
    def _generate_suggested_fix(
        rule_id: str,
        issue_type: str,
        snippet: str,
        evidence: Dict[str, Any],
        language: str,
    ) -> SuggestedFix:
        """Generate accurate, rule-specific remediation diff and advice."""
        if rule_id in ("PY_DIV_001", "JS_DIV_001", "JAVA_DIV_001"):
            divisor = evidence.get("right_operand", "divisor")
            return SuggestedFix(
                remove=f"- {snippet}" if snippet else None,
                add=f"+ if ({divisor} != 0):\n+     {snippet}" if snippet else None,
                note=f"Validate that divisor `{divisor}` is non-zero before performing division.",
            )

        if rule_id == "PY_RES_001":
            return SuggestedFix(
                remove=f"- {snippet}" if snippet else None,
                add=f"+ with {snippet} as f:\n+     content = f.read()" if snippet else None,
                note="Wrap file operations in a `with` statement to ensure deterministic file handle closure.",
            )

        if rule_id == "PY_EXC_001":
            return SuggestedFix(
                remove="- except:",
                add="+ except Exception as e:\n+     logger.error(f'Error occurred: {e}')",
                note="Avoid bare except clauses. Catch specific exception types or `Exception` and log the diagnostic error.",
            )

        if rule_id == "PY_ASS_001":
            return SuggestedFix(
                remove=f"- {snippet}" if snippet else "- assert condition",
                add="+ if not condition:\n+     raise ValueError('Invalid argument state')",
                note="Replace production assert statements with explicit condition checks and raised exceptions (asserts are stripped in optimized bytecode).",
            )

        if rule_id == "PY_MUT_001":
            param = evidence.get("param_name", "arg")
            return SuggestedFix(
                remove=f"- def func({param}=[]):",
                add=f"+ def func({param}=None):\n+     if {param} is None: {param} = []",
                note=f"Use `None` as default argument for `{param}` and initialize the mutable collection inside the function body.",
            )

        if rule_id == "JS_EQ_001":
            operator = evidence.get("operator", "==")
            strict_op = "===" if operator == "==" else "!=="
            fixed_snippet = snippet.replace(operator, strict_op) if snippet else None
            return SuggestedFix(
                remove=f"- {snippet}" if snippet else None,
                add=f"+ {fixed_snippet}" if fixed_snippet else None,
                note=f"Use strict equality (`{strict_op}`) to avoid implicit JavaScript type coercion bugs.",
            )

        if rule_id == "JS_AWA_001":
            return SuggestedFix(
                remove="- for (...) { await asyncOp(); }",
                add="+ await Promise.all(items.map(item => asyncOp(item)));",
                note="Execute asynchronous tasks concurrently with `Promise.all()` instead of sequentially awaiting in a loop.",
            )

        if rule_id == "JAVA_EXC_001":
            return SuggestedFix(
                remove="- } catch (Exception e) {}",
                add="+ } catch (Exception e) {\n+     logger.error(\"Operation failed\", e);\n+ }",
                note="Do not swallow exceptions silently. Log the stack trace or rethrow as an application-specific exception.",
            )

        if rule_id == "JAVA_EQ_001":
            left = evidence.get("left_operand", "str1")
            right = evidence.get("right_operand", "str2")
            return SuggestedFix(
                remove=f"- {left} == {right}",
                add=f"+ java.util.Objects.equals({left}, {right})",
                note="Use `.equals()` or `Objects.equals()` for string value equality instead of reference comparison `==`.",
            )

        if rule_id == "JAVA_RES_001":
            return SuggestedFix(
                remove=f"- {snippet}" if snippet else None,
                add=f"+ try ({snippet}) {{\n+     // use resource safely\n+ }}" if snippet else None,
                note="Use try-with-resources statement to guarantee automatic resource deallocation on completion or exception.",
            )

        if rule_id == "JAVA_LOOP_001":
            return SuggestedFix(
                remove="- while (true) { ... }",
                add="+ while (hasMoreElements() && !isTerminated()) { ... }",
                note="Ensure while loop has an explicit termination condition or internal `break` exit path.",
            )

        return SuggestedFix(
            remove=f"- {snippet}" if snippet else None,
            add=None,
            note=f"Review code construct at specified location according to {issue_type} guidelines.",
        )

    # -------------------------------------------------------------------------
    # Evidence Aggregation
    # -------------------------------------------------------------------------

    @staticmethod
    def _aggregate_evidence(
        static_finding: StaticAnalysisFinding,
        file_path: str,
        line_number: int,
        column: int,
        code_snippet: str,
        ast_location: Dict[str, Any],
        func_name: Optional[str],
        class_name: Optional[str],
        classification: Optional[ClassificationResult],
        similarity: SimilarityInfo,
    ) -> List[EvidenceItem]:
        """Aggregate all factual evidence produced across the pipeline."""
        items: List[EvidenceItem] = []

        # 1. Static Analysis Evidence
        items.append(EvidenceItem(
            type="static_analysis",
            description=f"Static analysis rule `{static_finding.rule_id}` triggered: {static_finding.message}",
            data={
                "rule_id": static_finding.rule_id,
                "issue_type": static_finding.issue_type,
                "analyzer_message": static_finding.message,
                "rule_severity": static_finding.severity,
                "rule_evidence": static_finding.evidence,
            },
        ))

        # 2. Source Code Evidence
        items.append(EvidenceItem(
            type="source",
            description=f"Source code location in `{file_path}` at line {line_number}, col {column}",
            data={
                "file_path": file_path,
                "line_number": line_number,
                "column": column,
                "code_snippet": code_snippet,
            },
        ))

        # 3. AST Evidence
        if ast_location or func_name or class_name:
            items.append(EvidenceItem(
                type="ast",
                description=f"AST node context: {ast_location.get('node_type', 'node')} inside {func_name or 'module'}",
                data={
                    "node_type": ast_location.get("node_type"),
                    "start_byte": ast_location.get("start_byte"),
                    "end_byte": ast_location.get("end_byte"),
                    "enclosing_function": func_name,
                    "enclosing_class": class_name,
                },
            ))

        # 4. ML Classification Evidence
        if classification:
            items.append(EvidenceItem(
                type="classification",
                description=f"ML Classifier prediction: category `{classification.category}` with {classification.confidence * 100:.1f}% confidence",
                data={
                    "category": classification.category,
                    "confidence": classification.confidence,
                    "severity_prediction": classification.severity_prediction,
                    "priority_prediction": classification.priority_prediction,
                    "needs_review": classification.needs_review,
                },
            ))

        # 5. Similarity Evidence
        if similarity.similar_issues or similarity.is_duplicate:
            dup_text = f"Duplicate of {similarity.duplicate_of}" if similarity.is_duplicate else f"{len(similarity.similar_issues)} similar occurrences found"
            items.append(EvidenceItem(
                type="similarity",
                description=f"Bug similarity analysis: {dup_text} (highest similarity {similarity.highest_similarity:.2f})",
                data={
                    "is_duplicate": similarity.is_duplicate,
                    "duplicate_of": similarity.duplicate_of,
                    "relationship_type": similarity.relationship_type,
                    "highest_similarity": similarity.highest_similarity,
                    "similar_count": len(similarity.similar_issues),
                },
            ))

        return items

    # -------------------------------------------------------------------------
    # Structured 8-Criteria Human-Readable Explanation
    # -------------------------------------------------------------------------

    @classmethod
    def _build_explanation(
        cls,
        title: str,
        rule_id: str,
        issue_type: str,
        file_path: str,
        line_number: int,
        column: int,
        scope_str: str,
        message: str,
        code_snippet: str,
        evidence_dict: Dict[str, Any],
        category: str,
        severity: str,
        priority: str,
        priority_formatted: str,
        similarity: SimilarityInfo,
        suggested_fix: SuggestedFix,
    ) -> BugExplanation:
        """
        Synthesize human-readable explanation strictly based on pipeline data,
        answering all 8 required criteria.
        """
        # 1. What is the issue?
        what = f"{title}. {message}"

        # 2. Where is it?
        where = f"Located in `{file_path}` at line {line_number} (column {column}) within `{scope_str}`."

        # 3. Why was it detected?
        why = f"Triggered static analysis rule `{rule_id}` because the AST pattern violates safe coding rules for `{issue_type}`."

        # 4. What evidence supports it?
        ev_details = ", ".join(f"{k}='{v}'" for k, v in evidence_dict.items()) if evidence_dict else "AST node pattern match"
        evidence_summary = (
            f"Code snippet `{code_snippet}` at line {line_number} exhibits target pattern. "
            f"Rule evidence extracted: {ev_details}."
        )

        # 5. What category does it belong to?
        cat_text = f"Classified under the `{category}` category ({issue_type.replace('_', ' ')})."

        # 6. How severe is it?
        sev_desc = SEVERITY_IMPACT_MAP.get(severity.lower(), "Standard severity impact.")
        severity_assessment = f"Severity is rated **{severity.upper()}**. {sev_desc}"

        # 7. How important is it to fix?
        prio_desc = PRIORITY_URGENCY_MAP.get(priority.lower(), "Standard triage priority.")
        importance_assessment = f"Priority is ranked as **{priority_formatted}**. {prio_desc}"

        # 8. Is it similar or duplicate to another issue?
        if similarity.is_duplicate:
            sim_text = f"This issue is a **duplicate** of `{similarity.duplicate_of}` (similarity score {similarity.highest_similarity:.2f})."
        elif similarity.similar_issues:
            sim_text = f"Identified as **similar** to {len(similarity.similar_issues)} other issue(s) in codebase (e.g. `{similarity.similar_issues[0].issue_id}`)."
        else:
            sim_text = "No duplicate or similar issues detected in current repository index (independent finding)."

        # Full synthesized text
        full_text = (
            f"### Issue Overview\n"
            f"**{what}**\n\n"
            f"- **Location**: {where}\n"
            f"- **Detection Logic**: {why}\n"
            f"- **Supporting Evidence**: {evidence_summary}\n"
            f"- **Category**: {cat_text}\n"
            f"- **Severity & Impact**: {severity_assessment}\n"
            f"- **Triage Priority**: {importance_assessment}\n"
            f"- **Relationship & Similarity**: {sim_text}\n\n"
            f"**Remediation Recommendation**: {suggested_fix.note}"
        )

        return BugExplanation(
            what=what,
            where=where,
            why=why,
            evidence_summary=evidence_summary,
            category=cat_text,
            severity_assessment=severity_assessment,
            importance_assessment=importance_assessment,
            similarity_or_duplicate=sim_text,
            full_text=full_text,
        )


# Global singleton instance
bug_enrichment_service = BugEnrichmentService()

"""
bug_enrichment_service.py
-------------------------
Bug Enrichment Service.
Combines Static Analysis findings, AST metadata, ML classification,
Severity/Priority predictions, and Similarity/Deduplication into complete
structured bug reports with actionable explanations.
"""
