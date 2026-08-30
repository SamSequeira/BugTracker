"""
JAVA_LOOP_001 — Infinite loop detection (Java)
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
  - `if (false) break;`        → unreachable exit → loop is infinite
  - `if (true) break;`         → definitely reachable → loop is not infinite
  - `if (1 == 2) break;`       → unreachable exit → loop is infinite
  - `if (!false) break;`       → reachable exit → loop is not infinite
  - `if (cond) break;`         → dynamic condition → conservative: treated reachable

Nested loop & switch awareness (FN-5)
---------------------------------------
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

# Node types that are nested break targets — an unlabeled break inside these
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
                    self.record_syntax_match()
                    body = self._body_block(node)
                    valid_labels = self._ancestor_labels(node, parent_map)
                    if body is not None and not self._has_exit(body, valid_labels):
                        yield self._make_loop_issue(node, body, file_path, source_lines)
                    else:
                        self.record_suppression("loop_has_reachable_exit")

            # Pattern 2: for (;;)
            elif ntype == "for_statement":
                if self._is_for_ever(node):
                    self.record_syntax_match()
                    body = self._body_block(node)
                    valid_labels = self._ancestor_labels(node, parent_map)
                    if body is not None and not self._has_exit(body, valid_labels):
                        yield self._make_loop_issue(node, body, file_path, source_lines)
                    else:
                        self.record_suppression("loop_has_reachable_exit")

            # Pattern 3: do { } while (true)
            elif ntype == "do_statement":
                if self._is_do_while_true(node):
                    self.record_syntax_match()
                    body = self._body_block(node)
                    valid_labels = self._ancestor_labels(node, parent_map)
                    if body is not None and not self._has_exit(body, valid_labels):
                        yield self._make_loop_issue(node, body, file_path, source_lines)
                    else:
                        self.record_suppression("loop_has_reachable_exit")

    # ------------------------------------------------------------------
    # Loop-pattern detectors
    # ------------------------------------------------------------------

    @staticmethod
    def _is_while_true(node: dict) -> bool:
        cond = next(
            (c for c in node.get("children", []) if c.get("type") == "parenthesized_expression"),
            None,
        )
        if cond is None:
            return False
        return JavaInfiniteLoop._eval_bool_const(cond) is True

    @staticmethod
    def _is_do_while_true(node: dict) -> bool:
        cond = next(
            (c for c in node.get("children", []) if c.get("type") == "parenthesized_expression"),
            None,
        )
        if cond is None:
            return False
        return JavaInfiniteLoop._eval_bool_const(cond) is True

    @staticmethod
    def _is_for_ever(node: dict) -> bool:
        children = node.get("children", [])
        sc_indices = [i for i, c in enumerate(children) if (c.get("text") or "").strip() == ";"]
        if len(sc_indices) >= 2:
            start_idx, end_idx = sc_indices[0], sc_indices[1]
            cond_children = [
                c for c in children[start_idx + 1: end_idx]
                if c.get("type") not in ("line_comment", "block_comment")
                and (c.get("text") or "").strip()
            ]
            if not cond_children:
                return True
            if len(cond_children) == 1:
                return JavaInfiniteLoop._eval_bool_const(cond_children[0]) is True
        return False

    @staticmethod
    def _body_block(node: dict) -> Optional[dict]:
        children = node.get("children", [])
        for c in reversed(children):
            if c.get("type") in ("block", "statement", "expression_statement", "return_statement"):
                return c
        return None

    def _ancestor_labels(self, node: dict, parent_map: dict) -> Set[str]:
        labels: Set[str] = set()
        curr = parent_map.get(id(node))
        while curr is not None:
            if curr.get("type") == "labeled_statement":
                ident = next((c for c in curr.get("children", []) if c.get("type") == "identifier"), None)
                if ident:
                    text = (ident.get("text") or "").strip()
                    if text:
                        labels.add(text)
            if curr.get("type") in _METHOD_SCOPE_BOUNDARIES:
                break
            curr = parent_map.get(id(curr))
        return labels

    # ------------------------------------------------------------------
    # Exit-path detection
    # ------------------------------------------------------------------

    def _has_exit(self, body_node: dict, valid_labels: Set[str]) -> bool:
        return self._search_exit(body_node, valid_labels, in_nested_loop=False)

    def _search_exit(self, node: dict, valid_labels: Set[str], in_nested_loop: bool) -> bool:
        ntype = node.get("type", "")

        if ntype in _EXIT_STMT_TYPES:
            return True

        if self._is_system_exit(node):
            return True

        if ntype == "break_statement":
            label = self._break_label(node)
            if label is None:
                if not in_nested_loop:
                    return True
            else:
                if label in valid_labels:
                    return True
            return False

        if ntype in _METHOD_SCOPE_BOUNDARIES:
            return False

        if ntype == "if_statement":
            return self._search_if_exit(node, valid_labels, in_nested_loop)

        new_nested = in_nested_loop or (ntype in _NESTED_BREAK_TARGETS)

        for child in node.get("children", []):
            if self._search_exit(child, valid_labels, new_nested):
                return True

        return False

    @staticmethod
    def _break_label(break_node: dict) -> Optional[str]:
        for c in break_node.get("children", []):
            if c.get("type") == "identifier":
                t = (c.get("text") or "").strip()
                if t and t != "break":
                    return t
        return None

    def _search_if_exit(self, if_node: dict, valid_labels: Set[str], in_nested_loop: bool) -> bool:
        children = if_node.get("children", [])
        cond = next((c for c in children if c.get("type") == "parenthesized_expression"), None)
        then_branch = next((c for c in children if c.get("type") in ("block", "expression_statement", "return_statement", "throw_statement", "break_statement")), None)
        else_branch = next((c for c in children if c.get("type") == "else_clause"), None)

        const_cond = self._eval_bool_const(cond) if cond is not None else None
        if const_cond is True:
            return then_branch is not None and self._search_exit(then_branch, valid_labels, in_nested_loop)
        elif const_cond is False:
            return else_branch is not None and self._search_exit(else_branch, valid_labels, in_nested_loop)
        else:
            then_has = (then_branch is not None and self._search_exit(then_branch, valid_labels, in_nested_loop))
            else_has = (else_branch is not None and self._search_exit(else_branch, valid_labels, in_nested_loop))
            return then_has or else_has

    @staticmethod
    def _is_system_exit(node: dict) -> bool:
        if node.get("type") not in ("method_invocation", "expression_statement"):
            return False
        text = (node.get("text") or "").replace(" ", "")
        return "System.exit(" in text

    @staticmethod
    def _eval_bool_const(node: dict) -> Optional[bool]:
        text = (node.get("text") or "").strip().replace("(", "").replace(")", "").strip()
        if text == "true":
            return True
        if text == "false":
            return False
        return None

    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

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
                "Infinite loop detected: loop condition is unconditionally `true` "
                "and body contains no reachable exit statement."
            ),
            evidence={
                "loop_type": loop_node.get("type", "while_statement"),
                "has_body": body_node is not None,
                "confidence": "high",
                "reason": "Unconditional infinite loop condition without any reachable break/return/throw exit.",
            },
            confidence="high",
        )
