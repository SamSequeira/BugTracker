"""
JAVA_LOOP_001 — Infinite Loop Detection (Java)
-----------------------------------------------
Detects loops with constant true conditions (`while (true)`, `for (;;)`)
that have no reachable exit path (break, return, throw).

High-confidence detection criteria:
- Constant condition loops with no break/return/throw statements.
- Loops where all exit breaks are guarded by statically false conditions (`if (false) break;`).
- Loops where counter variables diverge away from the exit threshold (`int x = 0; while (true) { if (x > 10) break; x--; }`).

Suppression criteria (provably terminating / reachable):
- Unconditional `break`, `return`, `throw`, `System.exit()`.
- Conditional breaks with reachable dynamic conditions (`if (cond) break;`).
- Monotonically progressing counter variables that reach the exit threshold (`x++` towards `x >= 10`).
"""

from __future__ import annotations

from typing import Iterator, List, Optional

from ..analysis.loop_analyzer import LoopAnalyzer, LoopExitStatus
from ..base_rule import BaseRule
from ..models import CandidateIssue


class JavaInfiniteLoop(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_LOOP_001"

    @property
    def issue_type(self) -> str:
        return "infinite_loop"

    @property
    def severity(self) -> str:
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        for node in self._walk(ast):
            ntype = node.get("type", "")
            if ntype not in ("while_statement", "for_statement", "do_statement"):
                continue

            if not LoopAnalyzer.is_infinite_loop_candidate(node):
                continue

            status, explanation = LoopAnalyzer.analyze_loop_exits(node)

            if status in (LoopExitStatus.NO_EXIT, LoopExitStatus.UNREACHABLE_EXIT, LoopExitStatus.DIVERGING_COUNTER):
                self.record_syntax_match()
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=f"Infinite loop detected: loop condition is constantly true and {explanation.lower()}",
                    evidence={
                        "loop_type": ntype,
                        "exit_status": status.name.lower(),
                        "reason": explanation,
                        "confidence": "high",
                    },
                    confidence="high",
                )
            else:
                self.record_suppression(f"reachable_exit_{status.name.lower()}")
"""
JAVA_LOOP_001 â€” Infinite loop detection (Java)
-----------------------------------------------
Detects infinite loops that have no reachable exit:
  - while (true) { ... }
  - for (;;) { ... }
  - do { ... } while (true);

Exit conditions that make a loop safe:
  - return_statement (unconditional or conditionally reachable)
  - throw_statement (unconditional or conditionally reachable)
  - break_statement (unconditional or conditionally reachable)
      * unlabeled break directly in this loop
      * labeled break targeting an enclosing ancestor label
  - System.exit(...) call

Constant evaluation (FN-4)
--------------------------
The rule evaluates constant boolean conditions in `if_statement`:
  - `if (false) break;`        â†’ unreachable exit â†’ loop is infinite
  - `if (true) break;`         â†’ definitely reachable â†’ loop is not infinite
  - `if (1 == 2) break;`       â†’ unreachable exit â†’ loop is infinite
  - `if (!false) break;`       â†’ reachable exit â†’ loop is not infinite
  - `if (cond) break;`         â†’ dynamic condition â†’ conservative: treated reachable

Nested loop & switch awareness (FN-5 & Phase 5.7)
-------------------------------------------------
Unlabeled `break;` inside a nested loop or switch statement terminates the
inner loop / switch only, and does NOT exit the outer loop.
A labeled break `break outer;` terminates the loop iff `outer` matches an
enclosing ancestor label of the loop being analyzed.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_EXIT_STMT_TYPES = {"return_statement", "throw_statement"}

# Node types that form a new scope boundary for return/throw search.
_METHOD_SCOPE_BOUNDARIES = {
    "lambda_expression",
    "method_declaration",
    "constructor_declaration",
}

# Node types that are nested break targets â€” an unlabeled break inside these
# exits the inner construct, NOT the outer loop being checked.
_NESTED_BREAK_TARGETS = {
    "for_statement",
    "while_statement",
    "do_statement",
    "enhanced_for_statement",
    "switch_statement",
    "switch_expression",
    "switch_block",
}


# ---------------------------------------------------------------------------
# Minimal constant boolean evaluator (FN-4)
# ---------------------------------------------------------------------------

def _eval_const_bool(node: dict) -> Optional[bool]:
    """
    Attempt to evaluate a constant boolean expression.
    Returns True, False, or None (unknown / not constant).
    """
    ntype = node.get("type", "")
    ntext = (node.get("text") or "").strip()

    # Boolean literals
    if ntype == "true" or ntext == "true":
        return True
    if ntype == "false" or ntext == "false":
        return False

    # Parenthesized expression
    if ntype == "parenthesized_expression":
        inner = _unwrap_parens(node)
        return _eval_const_bool(inner)

    # Unary negation: !expr
    if ntype == "unary_expression":
        children = node.get("children", [])
        if children and (children[0].get("text") or "") == "!":
            inner_val = _eval_const_bool(children[-1])
            if inner_val is not None:
                return not inner_val
        return None

    # Binary comparison or logical expression
    if ntype == "binary_expression":
        children = node.get("children", [])
        if len(children) < 3:
            return None
        op = children[1].get("text") or ""

        # Logical boolean operators
        if op in ("&&", "and"):
            lv = _eval_const_bool(children[0])
            rv = _eval_const_bool(children[2])
            if lv is False or rv is False:
                return False
            if lv is True and rv is True:
                return True
            if lv is True and rv is not None:
                return rv
            if rv is True and lv is not None:
                return lv
            return None

        if op in ("||", "or"):
            lv = _eval_const_bool(children[0])
            rv = _eval_const_bool(children[2])
            if lv is True or rv is True:
                return True
            if lv is False and rv is False:
                return False
            if lv is False and rv is not None:
                return rv
            if rv is False and lv is not None:
                return lv
            return None

        # Numeric comparisons
        lv = _eval_numeric(children[0])
        rv = _eval_numeric(children[2])
        if lv is None or rv is None:
            return None
        if op == "==":
            return lv == rv
        if op == "!=":
            return lv != rv
        if op == "<":
            return lv < rv
        if op == "<=":
            return lv <= rv
        if op == ">":
            return lv > rv
        if op == ">=":
            return lv >= rv

    return None


def _eval_numeric(node: dict) -> Optional[float]:
    """Try to extract a numeric value from a simple integer/float literal."""
    ntype = node.get("type", "")
    if ntype in (
        "decimal_integer_literal", "integer_literal",
        "decimal_floating_point_literal", "floating_point_literal",
    ):
        text = (node.get("text") or "").replace("_", "").rstrip("lLfFdD")
        try:
            return float(text)
        except (ValueError, TypeError):
            return None
    return None


def _unwrap_parens(node: dict) -> dict:
    for child in node.get("children", []):
        if (child.get("text") or "") not in ("(", ")"):
            return child
    return node


# ---------------------------------------------------------------------------
# Label extraction helpers (FN-5)
# ---------------------------------------------------------------------------

def _label_of(node: dict) -> Optional[str]:
    if node.get("type") != "labeled_statement":
        return None
    children = node.get("children", [])
    for child in children:
        if child.get("type") == "identifier":
            return (child.get("text") or "").strip() or None
    return None


def _break_label(break_node: dict) -> Optional[str]:
    text = (break_node.get("text") or "").strip()
    if text == "break;" or text == "break" or not text:
        return None  # unlabeled
    parts = text.rstrip(";").split()
    if len(parts) >= 2:
        return parts[1]
    for child in break_node.get("children", []):
        if child.get("type") == "identifier":
            return (child.get("text") or "").strip() or None
    return None


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

class JavaInfiniteLoop(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_LOOP_001"

    @property
    def issue_type(self) -> str:
        return "infinite_loop"

    @property
    def severity(self) -> str:
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            ntype = node.get("type", "")

            # Pattern 1: while (true)
            if ntype == "while_statement":
                if self._is_while_true(node):
                    body = self._body_block(node)
                    valid_labels = self._ancestor_labels(node, parent_map)
                    if body is not None and not self._has_exit(body, valid_labels):
                        yield self._make_loop_issue(node, body, file_path, source_lines)

            # Pattern 2: for (;;)
            elif ntype == "for_statement":
                if self._is_for_ever(node):
                    body = self._body_block(node)
                    valid_labels = self._ancestor_labels(node, parent_map)
                    if body is not None and not self._has_exit(body, valid_labels):
                        yield self._make_loop_issue(node, body, file_path, source_lines)

            # Pattern 3: do { } while (true)
            elif ntype == "do_statement":
                if self._is_do_while_true(node):
                    body = self._body_block(node)
                    valid_labels = self._ancestor_labels(node, parent_map)
                    if body is not None and not self._has_exit(body, valid_labels):
                        yield self._make_loop_issue(node, body, file_path, source_lines)

    # ------------------------------------------------------------------
    # Loop-pattern detectors
    # ------------------------------------------------------------------

    @staticmethod
    def _is_while_true(node: dict) -> bool:
        for child in node.get("children", []):
            if child.get("type") == "parenthesized_expression":
                inner = [c for c in child.get("children", [])
                         if (c.get("text") or "") not in ("(", ")")]
                return len(inner) == 1 and inner[0].get("type") == "true"
        return False

    @staticmethod
    def _is_for_ever(node: dict) -> bool:
        children = node.get("children", [])
        texts = [(c.get("text") or "") for c in children]
        semi_indices = [i for i, t in enumerate(texts) if t == ";"]
        if len(semi_indices) >= 2:
            first_semi, second_semi = semi_indices[0], semi_indices[1]
            between = children[first_semi + 1:second_semi]
            return len(between) == 0
        return False

    @staticmethod
    def _is_do_while_true(node: dict) -> bool:
        children = node.get("children", [])
        found_while = False
        for child in children:
            if (child.get("text") or "") == "while":
                found_while = True
                continue
            if found_while and child.get("type") == "parenthesized_expression":
                inner = [c for c in child.get("children", [])
                         if (c.get("text") or "") not in ("(", ")")]
                return len(inner) == 1 and inner[0].get("type") == "true"
        return False

    @staticmethod
    def _body_block(node: dict) -> Optional[dict]:
        for child in node.get("children", []):
            if child.get("type") in ("block", "statement_block"):
                return child
        children = node.get("children", [])
        if len(children) >= 3:
            return children[-1]
        return None

    # ------------------------------------------------------------------
    # Label helpers (FN-5)
    # ------------------------------------------------------------------

    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    @staticmethod
    def _ancestor_labels(loop_node: dict, parent_map: dict) -> Set[str]:
        labels: Set[str] = set()
        curr = parent_map.get(id(loop_node))
        while curr is not None:
            lbl = _label_of(curr)
            if lbl:
                labels.add(lbl)
            curr = parent_map.get(id(curr))
        return labels

    # ------------------------------------------------------------------
    # Exit-path detection (FN-4 + FN-5)
    # ------------------------------------------------------------------

    def _has_exit(self, node: dict, valid_labels: Set[str]) -> bool:
        return self._search_exit(node, valid_labels, in_nested_loop=False)

    def _search_exit(
        self,
        node: dict,
        valid_labels: Set[str],
        in_nested_loop: bool,
    ) -> bool:
        ntype = node.get("type", "")

        # return/throw always exit the method â†’ definitely exit this loop
        if ntype in _EXIT_STMT_TYPES:
            return True

        # System.exit(...)
        if self._is_system_exit(node):
            return True

        # break_statement
        if ntype == "break_statement":
            label = _break_label(node)
            if in_nested_loop:
                if label is None:
                    return False
                return label in valid_labels
            else:
                return (label is None) or (label in valid_labels)

        # Don't cross method / lambda boundaries for return/throw
        if ntype in _METHOD_SCOPE_BOUNDARIES:
            return False

        # Cross into nested loops or switch constructs with in_nested_loop=True
        if ntype in _NESTED_BREAK_TARGETS:
            return any(
                self._search_exit(c, valid_labels, in_nested_loop=True)
                for c in node.get("children", [])
            )

        # if_statement: check constant condition (FN-4)
        if ntype == "if_statement":
            return self._exit_in_if(node, valid_labels, in_nested_loop)

        # Recurse into all other nodes
        return any(
            self._search_exit(c, valid_labels, in_nested_loop)
            for c in node.get("children", [])
        )

    def _exit_in_if(
        self,
        if_node: dict,
        valid_labels: Set[str],
        in_nested_loop: bool,
    ) -> bool:
        children = if_node.get("children", [])
        cond_node = None
        then_branch = None
        else_branch = None

        found_if = False
        then_idx = 0
        for i, child in enumerate(children):
            text = child.get("text") or ""
            if text == "if" and not found_if:
                found_if = True
                continue
            if found_if and cond_node is None:
                cond_node = child
                then_idx = i + 1
                break

        past_else = False
        for i in range(then_idx, len(children)):
            child = children[i]
            ctext = (child.get("text") or "").strip()
            ctype = child.get("type", "")
            if ctext == "else" or ctype == "else":
                past_else = True
                continue
            if ctext in (":", ";", "(", ")", "{", "}") or ctype in (":", ";", "(", ")"):
                continue
            if not past_else and then_branch is None:
                then_branch = child
            elif past_else and else_branch is None:
                else_branch = child

        cond_val: Optional[bool] = None
        if cond_node is not None:
            inner = _unwrap_parens(cond_node)
            cond_val = _eval_const_bool(inner)

        # Evaluate reachability:
        if cond_val is False:
            if else_branch is not None:
                return self._search_exit(else_branch, valid_labels, in_nested_loop)
            return False
        elif cond_val is True:
            if then_branch is not None:
                return self._search_exit(then_branch, valid_labels, in_nested_loop)
            return False
        else:
            then_has = (then_branch is not None and
                        self._search_exit(then_branch, valid_labels, in_nested_loop))
            else_has = (else_branch is not None and
                        self._search_exit(else_branch, valid_labels, in_nested_loop))
            return then_has or else_has

    @staticmethod
    def _is_system_exit(node: dict) -> bool:
        if node.get("type") not in ("method_invocation", "expression_statement"):
            return False
        text = (node.get("text") or "").replace(" ", "")
        return "System.exit(" in text

    def _make_loop_issue(
        self,
        loop_node: dict,
        body_node: dict,
        file_path: str,
        source_lines: List[str],
    ) -> CandidateIssue:
        return self._make_issue(
            node=loop_node,
            file_path=file_path,
            source_lines=source_lines,
            message=(
                "Infinite loop detected: this loop condition is unconditionally "
                "`true` and its body contains no reachable `break`, `return`, "
                "or exception-throwing statement."
            ),
            evidence={
                "loop_type": loop_node.get("type", "while_statement"),
                "has_body": body_node is not None,
                "confidence": "high",
            },
            confidence="high",
        )
