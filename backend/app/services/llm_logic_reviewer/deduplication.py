"""
deduplication.py
----------------
Deduplication engine to prevent LLM findings from duplicating rule-based findings.

Compares candidate LLM findings against existing deterministic rule findings
using 7 concrete criteria:
1. Compare against existing rule findings
2. Compare file (with cross-file awareness)
3. Compare line range
4. Compare symbol (variable, function, operator)
5. Compare normalized issue category
6. Compare root cause (same underlying mechanism vs novel semantic defect)
7. Compare code evidence (operands, expressions, AST evidence)

If the LLM candidate is essentially the same underlying issue as an existing
deterministic finding:
    DO NOT create a new issue (REJECT duplicate).

If it provides genuinely new semantic information:
    ALLOW the issue (ACCEPT unique finding).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# Canonical Issue Categories
# =============================================================================

CAT_ZERO_DIVISION = "ZERO_DIVISION"
CAT_RESOURCE_LIFECYCLE = "RESOURCE_LIFECYCLE"
CAT_EXCEPTION_HANDLING = "EXCEPTION_HANDLING"
CAT_COMPARISON_LOGIC = "COMPARISON_LOGIC"
CAT_MUTABLE_STATE = "MUTABLE_STATE"
CAT_DATA_FLOW_UNIT = "DATA_FLOW_UNIT"
CAT_STATE_TRANSITION = "STATE_TRANSITION"
CAT_OPERATION_ORDER = "OPERATION_ORDER"
CAT_CROSS_FUNCTION = "CROSS_FUNCTION"
CAT_SECURITY_VULNERABILITY = "SECURITY_VULNERABILITY"
CAT_VALIDATION = "VALIDATION"
CAT_OTHER = "OTHER"


def normalize_category(cat_or_id: str, text: str = "") -> str:
    """Normalize rule ID, issue type, or LLM category into canonical bucket."""
    c = (cat_or_id or "").lower().strip()
    t = (text or "").lower()

    # 1. Zero Division
    if any(k in c for k in ("div", "zero_division", "division_by_zero")) or "division by zero" in t or "divide by zero" in t:
        return CAT_ZERO_DIVISION

    # 2. Resource Lifecycle
    if any(k in c for k in ("res", "unclosed_resource", "resource_leak", "resource_lifecycle", "unclosed_filereader")):
        return CAT_RESOURCE_LIFECYCLE

    # 3. Exception Handling
    if any(k in c for k in ("exc", "cat", "bare_except", "empty_catch", "swallowed_exception", "error_handling")):
        return CAT_EXCEPTION_HANDLING

    # 4. Comparison Logic
    if any(k in c for k in ("eq", "comparison", "inverted_condition", "loose_equality", "wrong_comparison", "wrong_condition")):
        return CAT_COMPARISON_LOGIC

    # 5. Mutable State
    if any(k in c for k in ("mut", "mutable_default", "mutable_state")):
        return CAT_MUTABLE_STATE

    # 6. Unit Mismatch / Data Flow
    if any(k in c for k in ("unit_mismatch", "currency_mismatch", "unit", "cents", "dollars")) or "cents" in t or "dollars" in t or "unit mismatch" in t:
        return CAT_DATA_FLOW_UNIT

    # 7. State Transition
    if any(k in c for k in ("state", "state_error", "wrong_state_transition", "state_transition")):
        return CAT_STATE_TRANSITION

    # 8. Operation Order
    if any(k in c for k in ("order", "ordering_violation", "wrong_operation_order")):
        return CAT_OPERATION_ORDER

    # 9. Cross Function Contract
    if any(k in c for k in ("cross_function", "contract_mismatch")):
        return CAT_CROSS_FUNCTION

    # 10. Security / Vulnerability (path traversal, sql injection)
    if any(k in c for k in ("security", "injection", "traversal", "unauthorized")) or "path traversal" in t or "sql injection" in t:
        return CAT_SECURITY_VULNERABILITY

    # 11. General Validation
    if any(k in c for k in ("validation", "missing_validation", "validation_inconsistency")):
        return CAT_VALIDATION

    # Fallback to general data flow
    if "data_flow" in c or "flow_error" in c:
        return CAT_DATA_FLOW_UNIT

    return CAT_OTHER


# =============================================================================
# Deduplication Result
# =============================================================================

@dataclass
class DeduplicationResult:
    """Detailed verdict from the 7-point deduplication check."""

    is_duplicate: bool
    matching_rule: Optional[Dict[str, Any]] = None
    reason: str = ""
    decision: str = "ALLOW"  # "REJECT" | "ALLOW"


# =============================================================================
# Deduplication Engine
# =============================================================================

class DeduplicationEngine:
    """
    Evaluates LLM findings against deterministic rule findings across 7 criteria:
    1. Rule finding index
    2. File match (handling cross-file findings)
    3. Line range / proximity
    4. Symbol comparison
    5. Normalized category comparison
    6. Root cause analysis
    7. Code evidence comparison
    """

    LINE_PROXIMITY_THRESHOLD = 15
    TITLE_SIMILARITY_THRESHOLD = 0.65

    # Categories that can overlap between rule and LLM
    CATEGORY_EQUIVALENCE = {
        "comparison_issue": {"wrong_condition", "wrong_comparison"},
        "logic_error": {"wrong_condition", "wrong_data_flow", "wrong_operation_order"},
        "state_error": {"wrong_state_transition"},
        "flow_error": {"wrong_data_flow", "wrong_operation_order"},
        "call_error": {"cross_function", "wrong_operation_order"},
        "return_error": {"wrong_data_flow", "cross_function"},
    }

    def __init__(
        self,
        line_proximity_threshold: int = 15,
        title_similarity_threshold: float = 0.65,
    ):
        self.LINE_PROXIMITY_THRESHOLD = line_proximity_threshold
        self.TITLE_SIMILARITY_THRESHOLD = title_similarity_threshold

    def evaluate(
        self,
        llm_finding: Dict[str, Any],
        rule_findings: List[Dict[str, Any]],
    ) -> DeduplicationResult:
        """
        Run the full 7-point deduplication analysis on an LLM candidate.
        Returns DeduplicationResult.
        """
        # 1. Compare against existing rule findings
        if not rule_findings:
            return DeduplicationResult(
                is_duplicate=False,
                decision="ALLOW",
                reason="No existing rule findings in context",
            )

        # Extract LLM attributes
        llm_file = self._normalize_file(llm_finding.get("file_path", ""))
        llm_line = llm_finding.get("line") or llm_finding.get("line_number")
        llm_symbol = self._extract_symbol(llm_finding)
        llm_cat = normalize_category(
            llm_finding.get("category", "") or llm_finding.get("bug_type", ""),
            llm_finding.get("title", "") + " " + llm_finding.get("description", "") + " " + llm_finding.get("root_cause", "")
        )
        llm_root_cause = self._extract_root_cause(llm_finding)
        is_cross_file = llm_finding.get("cross_file", False) or self._is_cross_file_evidence(llm_finding)
        is_cross_function = llm_finding.get("cross_function", False) or (llm_cat == CAT_CROSS_FUNCTION)

        for rule in rule_findings:
            rule_file = self._normalize_file(rule.get("file_path", ""))
            rule_line = rule.get("line_number") or rule.get("line")
            rule_symbol = self._extract_symbol(rule)
            rule_cat = normalize_category(
                rule.get("issue_type", "") or rule.get("rule_id", ""),
                rule.get("title", "") + " " + rule.get("message", "")
            )
            rule_root_cause = self._extract_root_cause(rule)

            # -------------------------------------------------------------
            # 2. Compare file
            # -------------------------------------------------------------
            # Cross-file finding check: if LLM finding genuinely spans across files,
            # a local single-file rule finding in one file is not a duplicate.
            if is_cross_file:
                # LLM finding is a cross-file contract bug -> preserve novelty
                continue

            if llm_file and rule_file and llm_file != rule_file:
                # Different files for single-file issue -> distinct
                continue

            # -------------------------------------------------------------
            # Cross-function finding check
            # -------------------------------------------------------------
            if is_cross_function and rule_cat != CAT_CROSS_FUNCTION:
                # LLM finding is a cross-function contract mismatch (e.g. caller/callee contract)
                # while rule is a local function AST check -> preserve novelty
                continue

            # -------------------------------------------------------------
            # 5. Compare normalized issue category
            # -------------------------------------------------------------
            categories_orthogonal = self._are_categories_orthogonal(llm_cat, rule_cat)

            # -------------------------------------------------------------
            # 6. Compare root cause
            # -------------------------------------------------------------
            same_root_cause = self._is_same_root_cause(llm_root_cause, rule_root_cause, llm_cat, rule_cat)

            # -------------------------------------------------------------
            # 4. Compare symbol
            # -------------------------------------------------------------
            symbols_match = bool(llm_symbol and rule_symbol and llm_symbol == rule_symbol)

            # -------------------------------------------------------------
            # 3. Compare line range
            # -------------------------------------------------------------
            lines_close = self._lines_nearby(llm_line, rule_line)
            same_line = (llm_line is not None and rule_line is not None and llm_line == rule_line)

            # -------------------------------------------------------------
            # Decision Logic:
            # -------------------------------------------------------------
            is_novel_semantic = (
                categories_orthogonal
                or (llm_cat in (CAT_CROSS_FUNCTION, CAT_SECURITY_VULNERABILITY) and rule_cat not in (CAT_CROSS_FUNCTION, CAT_SECURITY_VULNERABILITY))
                or ("cents" in llm_root_cause and "cents" not in rule_root_cause)
                or ("dollars" in llm_root_cause and "dollars" not in rule_root_cause)
                or ("unit mismatch" in llm_root_cause and "unit mismatch" not in rule_root_cause)
                or ("path traversal" in llm_root_cause and "path traversal" not in rule_root_cause)
            )

            # Scenario A: Same line, but genuinely NOVEL semantic root cause / orthogonal domain
            # e.g., Line 42: Rule is unclosed file (resource leak), LLM is path traversal (security).
            # Or Rule is missing validation, LLM is currency unit mismatch.
            if same_line and is_novel_semantic:
                logger.debug("Deduplication: Same line %s, but novel semantic root cause -> ALLOW", llm_line)
                continue

            # Scenario B: Duplicate rejection - same root cause, matching category, nearby or same line
            if same_root_cause and not categories_orthogonal and not is_novel_semantic:
                if lines_close or symbols_match:
                    return DeduplicationResult(
                        is_duplicate=True,
                        matching_rule=rule,
                        decision="REJECT",
                        reason=f"Duplicate: Same underlying root cause '{llm_cat}' on symbol '{llm_symbol or rule_symbol or 'code'}' (lines {llm_line} and {rule_line})",
                    )

            # Scenario C: Different lines, but SAME underlying root cause and symbol
            # e.g., variable divisor = 0 at line 15, division at line 35.
            if same_root_cause and symbols_match and not categories_orthogonal and not is_novel_semantic:
                return DeduplicationResult(
                    is_duplicate=True,
                    matching_rule=rule,
                    decision="REJECT",
                    reason=f"Duplicate across lines {llm_line} and {rule_line}: Same underlying root cause '{llm_cat}' on symbol '{llm_symbol}'",
                )

            # Scenario D: Equivalent category mapping on same/nearby lines
            raw_llm_cat = (llm_finding.get("category") or llm_finding.get("bug_type") or "").lower()
            raw_rule_cat = (rule.get("issue_type") or rule.get("rule_id") or "").lower()
            if lines_close and self._categories_equivalent(raw_llm_cat, raw_rule_cat) and not is_novel_semantic:
                return DeduplicationResult(
                    is_duplicate=True,
                    matching_rule=rule,
                    decision="REJECT",
                    reason=f"Duplicate: Equivalent categories '{raw_llm_cat}' and '{raw_rule_cat}' on nearby lines {llm_line} and {rule_line}",
                )

            # Scenario E: Title / description semantic overlap on nearby lines
            if lines_close and not categories_orthogonal and not is_novel_semantic:
                llm_title = llm_finding.get("title", "")
                rule_title = rule.get("title", "") or rule.get("message", "")
                if self._titles_similar(llm_title, rule_title):
                    return DeduplicationResult(
                        is_duplicate=True,
                        matching_rule=rule,
                        decision="REJECT",
                        reason=f"Duplicate: Semantic title overlap on nearby lines {llm_line} and {rule_line}",
                    )

        return DeduplicationResult(
            is_duplicate=False,
            decision="ALLOW",
            reason="Novel semantic finding: distinct root cause, cross-boundary scope, or novel category",
        )

    def is_duplicate(
        self,
        llm_finding: Dict[str, Any],
        rule_findings: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Public API: Check if LLM finding duplicates any rule finding.
        Returns matching rule finding dict if duplicate, None if novel/unique.
        """
        result = self.evaluate(llm_finding, rule_findings)
        return result.matching_rule if result.is_duplicate else None

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _categories_equivalent(self, llm_cat: str, rule_cat: str) -> bool:
        if not llm_cat or not rule_cat:
            return False
        if llm_cat == rule_cat:
            return True
        for rule_key, llm_values in self.CATEGORY_EQUIVALENCE.items():
            if rule_cat == rule_key and llm_cat in llm_values:
                return True
        return False

    def _normalize_file(self, file_path: str) -> str:
        if not file_path:
            return ""
        return Path(file_path).as_posix().lower()

    def _lines_nearby(self, llm_line: Optional[int], rule_line: Optional[int]) -> bool:
        if llm_line is None or rule_line is None:
            return True
        return abs(llm_line - rule_line) <= self.LINE_PROXIMITY_THRESHOLD

    def _extract_symbol(self, finding: Dict[str, Any]) -> str:
        """Extract symbol (variable name, function name, operand) from finding."""
        # Check direct symbol field
        if finding.get("symbol"):
            return str(finding["symbol"]).lower().strip()

        # Check evidence dict
        ev = finding.get("evidence", {})
        if isinstance(ev, dict):
            if ev.get("right_operand"):
                return str(ev["right_operand"]).lower().strip()
            if ev.get("variable"):
                return str(ev["variable"]).lower().strip()
            if ev.get("symbol"):
                return str(ev["symbol"]).lower().strip()
        elif isinstance(ev, list) and ev:
            first = ev[0]
            if isinstance(first, dict) and first.get("symbol"):
                return str(first["symbol"]).lower().strip()

        # Regex search in title or description e.g. "on variable 'x'" or "because x may be zero"
        text = finding.get("title", "") + " " + finding.get("description", "") + " " + finding.get("message", "")
        match = re.search(r"""(?:variable|symbol|parameter|divisor|value|argument)\s*['"]?([a-zA-Z0-9_]+)['"]?""", text, re.I)
        if match:
            return match.group(1).lower().strip()

        return ""

    def _extract_root_cause(self, finding: Dict[str, Any]) -> str:
        """Extract canonical root cause text."""
        parts = [
            finding.get("root_cause", ""),
            finding.get("hypothesis", ""),
            finding.get("description", ""),
            finding.get("title", ""),
            finding.get("message", ""),
        ]
        return " ".join(p for p in parts if p).lower()

    def _are_categories_orthogonal(self, cat1: str, cat2: str) -> bool:
        """Check if two categories represent fundamentally different problem domains."""
        if cat1 == cat2:
            return False

        # Incompatible domain pairs
        orthogonal_pairs = {
            (CAT_ZERO_DIVISION, CAT_RESOURCE_LIFECYCLE),
            (CAT_ZERO_DIVISION, CAT_DATA_FLOW_UNIT),
            (CAT_ZERO_DIVISION, CAT_SECURITY_VULNERABILITY),
            (CAT_RESOURCE_LIFECYCLE, CAT_SECURITY_VULNERABILITY),
            (CAT_RESOURCE_LIFECYCLE, CAT_DATA_FLOW_UNIT),
            (CAT_RESOURCE_LIFECYCLE, CAT_COMPARISON_LOGIC),
            (CAT_VALIDATION, CAT_DATA_FLOW_UNIT),
            (CAT_VALIDATION, CAT_ZERO_DIVISION),
            (CAT_EXCEPTION_HANDLING, CAT_DATA_FLOW_UNIT),
        }

        pair = (cat1, cat2)
        rev_pair = (cat2, cat1)
        return pair in orthogonal_pairs or rev_pair in orthogonal_pairs

    def _is_same_root_cause(self, cause1: str, cause2: str, cat1: str, cat2: str) -> bool:
        """Determine if two findings describe the same underlying defect mechanism."""
        # 1. Zero division matching
        if cat1 == CAT_ZERO_DIVISION and cat2 == CAT_ZERO_DIVISION:
            return True
        if ("division by zero" in cause1 or "divide by zero" in cause1) and ("division by zero" in cause2 or "divide by zero" in cause2):
            return True

        # 2. Resource leak matching
        if cat1 == CAT_RESOURCE_LIFECYCLE and cat2 == CAT_RESOURCE_LIFECYCLE:
            return True

        # 3. State transition matching
        if cat1 == CAT_STATE_TRANSITION and cat2 == CAT_STATE_TRANSITION:
            return True

        # 4. Inverted comparison matching
        if cat1 == CAT_COMPARISON_LOGIC and cat2 == CAT_COMPARISON_LOGIC:
            return True

        # Check keyword similarity ratio
        ratio = SequenceMatcher(None, cause1, cause2).ratio()
        return ratio >= self.TITLE_SIMILARITY_THRESHOLD

    def _is_cross_file_evidence(self, finding: Dict[str, Any]) -> bool:
        """Check if finding evidence references more than one file."""
        ev = finding.get("evidence")
        if isinstance(ev, list) and len(ev) > 1:
            files = {item.get("file") for item in ev if isinstance(item, dict) and item.get("file")}
            if len(files) > 1:
                return True

        # Check description for cross-file references
        desc = finding.get("description", "") + " " + finding.get("root_cause", "")
        if "cross-file" in desc.lower() or "different file" in desc.lower():
            return True

        return False

    def _titles_similar(self, title1: str, title2: str) -> bool:
        if not title1 or not title2:
            return False

        t1 = title1.lower().strip()
        t2 = title2.lower().strip()

        if t1 == t2 or t1 in t2 or t2 in t1:
            return True

        return SequenceMatcher(None, t1, t2).ratio() >= self.TITLE_SIMILARITY_THRESHOLD


_dedup_engine = DeduplicationEngine()


def get_dedup_engine() -> DeduplicationEngine:
    return _dedup_engine
