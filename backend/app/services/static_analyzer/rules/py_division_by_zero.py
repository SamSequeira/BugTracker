"""
PY_DIV_001 — Division by zero or potentially-zero divisor (Python)
-------------------------------------------------------------------
Detects `/` and `//` binary operations where the right-hand operand is
provably zero, or cannot be proven non-zero.

Classification of the right-hand operand
-----------------------------------------
DEFINITELY_ZERO      — literal `0`, `0.0`, `-0`, `+0`, `-0.0`, etc.
                       → always reported  (definite error)
DEFINITELY_NON_ZERO  — literal like `1`, `-1`, `2.5`, `True`; constant
                       arithmetic whose result is provably non-zero;
                       `x or 1` / `x or <non-zero>`;
                       `max(1, …)` with a provably-non-zero argument;
                       conditional where every branch is non-zero.
                       → never reported  (provably safe)
POTENTIALLY_ZERO     — anything else (variables, function calls, …)
                       → reported as a potential issue (warning)

Control-flow guards & branch-aware state tracking (Phase 5.6 & 5.7)
--------------------------------------------------------------------
A `POTENTIALLY_ZERO` divisor may be suppressed by a preceding guard of
one of these forms in the same lexical scope:

    if divisor != 0: ...
    if divisor:      ...
    assert divisor != 0
    assert divisor

The analysis tracks lexical scope boundaries (modules, functions, classes,
lambdas), sequential fact updates, branch forks and merges, loop states,
and assignment invalidations (kills).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Dict, Iterator, List, Optional, Set, Tuple

from ..base_rule import BaseRule
from ..models import CandidateIssue


# ---------------------------------------------------------------------------
# Classification enum
# ---------------------------------------------------------------------------

class _Z(Enum):
    DEFINITELY_ZERO     = auto()
    DEFINITELY_NON_ZERO = auto()
    POTENTIALLY_ZERO    = auto()


# Node types that introduce a new lexical scope for variable bindings
_SCOPE_NODES = {
    "function_definition",
    "async_function_definition",
    "lambda",
    "class_definition",
}


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

class PythonDivisionByZero(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_DIV_001"

    @property
    def issue_type(self) -> str:
        return "division_by_zero"

    @property
    def severity(self) -> str:
        return "high"

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        yield from self._analyze_scope(ast, {}, file_path, source_lines)

    # ------------------------------------------------------------------
    # Lexical Scope & Flow-Sensitive Analysis
    # ------------------------------------------------------------------

    def _analyze_scope(
        self,
        scope_node: dict,
        outer_facts: Dict[str, str],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        """
        Analyse a lexical scope with isolated variable facts, inheriting outer
        constants conservatively and binding formal parameters.
        """
        facts: Dict[str, str] = {}

        # 1. Inherit outer facts across function boundaries:
        # DEFINITELY_ZERO propagates down into closures; non-zero facts become POTENTIALLY_ZERO
        for k, v in outer_facts.items():
            if v == "DEFINITELY_ZERO":
                facts[k] = "DEFINITELY_ZERO"
            else:
                facts[k] = "POTENTIALLY_ZERO"

        # 2. Formal parameter bindings shadow outer scope as fresh dynamic variables
        ntype = scope_node.get("type", "")
        if ntype in ("function_definition", "async_function_definition", "lambda"):
            params_node = next(
                (c for c in scope_node.get("children", []) if c.get("type") == "parameters"),
                None,
            )
            if params_node:
                for p in params_node.get("children", []):
                    ptype = p.get("type", "")
                    if ptype == "identifier":
                        pname = (p.get("text") or "").strip()
                        if pname:
                            facts[pname] = "POTENTIALLY_ZERO"
                    elif ptype == "default_parameter":
                        pkids = p.get("children", [])
                        if pkids:
                            pname = (pkids[0].get("text") or "").strip()
                            if pname:
                                facts[pname] = "POTENTIALLY_ZERO"

        yield from self._analyze_block(scope_node, facts, file_path, source_lines, is_scope_root=True)

    def _analyze_block(
        self,
        node: dict,
        facts: Dict[str, str],
        file_path: str,
        source_lines: List[str],
        is_scope_root: bool = False,
    ) -> Iterator[CandidateIssue]:
        """
        Walk statements in `node` sequentially, updating `facts` in place
        and recursing into child branches, loops, and child scopes.
        """
        children = node.get("children", [])
        if not children and is_scope_root:
            return

        i = 0
        while i < len(children):
            child = children[i]
            ntype = child.get("type", "")

            # 1. Child scope boundary (function, lambda, class)
            if ntype in _SCOPE_NODES:
                yield from self._analyze_scope(child, facts, file_path, source_lines)
                i += 1
                continue

            # 2. Simple assignment: var = <rhs>
            if ntype == "assignment":
                yield from self._check_divisions(child, facts, file_path, source_lines)
                assign_kids = child.get("children", [])
                if len(assign_kids) >= 3:
                    lhs = assign_kids[0]
                    name = self._identifier_name(lhs)
                    if name:
                        rhs = assign_kids[-1]
                        cls = self._classify_assignment_rhs(rhs)
                        if cls == _Z.DEFINITELY_NON_ZERO:
                            facts[name] = "DEFINITELY_NON_ZERO"
                        elif cls == _Z.DEFINITELY_ZERO:
                            facts[name] = "DEFINITELY_ZERO"
                        else:
                            facts[name] = "POTENTIALLY_ZERO"
                i += 1
                continue

            # 3. Augmented assignment: var += 1, var -= 1 (dynamic value -> kill to POTENTIALLY_ZERO)
            if ntype == "augmented_assignment":
                yield from self._check_divisions(child, facts, file_path, source_lines)
                assign_kids = child.get("children", [])
                if assign_kids:
                    name = self._identifier_name(assign_kids[0])
                    if name:
                        facts[name] = "POTENTIALLY_ZERO"
                i += 1
                continue

            # 4. Assert guard: assert d != 0 / assert d
            if ntype == "assert_statement":
                yield from self._check_divisions(child, facts, file_path, source_lines)
                guard_name = self._guard_name_from_assert(child)
                if guard_name:
                    facts[guard_name] = "GUARDED"
                i += 1
                continue

            # 5. If statement (branching)
            if ntype == "if_statement":
                yield from self._analyze_if_statement(child, facts, file_path, source_lines)
                i += 1
                continue

            # 6. Loops (while / for) & Try blocks
            if ntype in ("while_statement", "for_statement", "try_statement"):
                yield from self._analyze_loop_or_try(child, facts, file_path, source_lines)
                i += 1
                continue

            # 7. Division in general expression / statement
            if ntype == "binary_operator" and child.get("children", [{}, {}])[1].get("text", "") in ("/", "//"):
                yield from self._eval_division_node(child, facts, file_path, source_lines)
                yield from self._check_divisions(child.get("children", [{}])[0], facts, file_path, source_lines)
                i += 1
                continue

            # 8. Expression statements & other nested blocks
            if ntype in ("expression_statement", "return_statement"):
                yield from self._check_divisions(child, facts, file_path, source_lines)
                i += 1
                continue

            if ntype in ("block", "with_statement", "else_clause", "elif_clause"):
                yield from self._analyze_block(child, facts, file_path, source_lines)
                i += 1
                continue

            # Default: check divisions and recurse into children
            yield from self._check_divisions(child, facts, file_path, source_lines)
            yield from self._analyze_block(child, facts, file_path, source_lines)
            i += 1

    def _analyze_if_statement(
        self,
        if_node: dict,
        facts: Dict[str, str],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        children = if_node.get("children", [])
        cond_node = self._if_condition(if_node)
        if cond_node:
            yield from self._check_divisions(cond_node, facts, file_path, source_lines)

        guard_name = self._cond_guard_name(cond_node) if cond_node else None

        # Find then-block, elif clauses, else clause
        then_block = next((c for c in children if c.get("type") == "block"), None)
        elif_clauses = [c for c in children if c.get("type") == "elif_clause"]
        else_clause = next((c for c in children if c.get("type") == "else_clause"), None)

        # 1. Then branch
        then_facts = dict(facts)
        if guard_name:
            then_facts[guard_name] = "GUARDED"
        if then_block:
            yield from self._analyze_block(then_block, then_facts, file_path, source_lines)

        # 2. Elif branches
        elif_facts_list = []
        for elif_c in elif_clauses:
            e_facts = dict(facts)
            yield from self._analyze_block(elif_c, e_facts, file_path, source_lines)
            elif_facts_list.append(e_facts)

        # 3. Else branch
        else_facts = None
        if else_clause:
            else_facts = dict(facts)
            yield from self._analyze_block(else_clause, else_facts, file_path, source_lines)

        # Merge facts:
        # Check if if_node was a top-level guard without an else (e.g. `if d != 0: pass` or empty block)
        then_children = then_block.get("children", []) if then_block else []
        is_empty_then = not then_children or (len(then_children) == 1 and then_children[0].get("type") == "pass_statement")
        if guard_name and not else_clause and not elif_clauses and is_empty_then:
            facts[guard_name] = "GUARDED"
            return

        all_branch_facts = [then_facts] + elif_facts_list
        if else_facts is not None:
            all_branch_facts.append(else_facts)

        modified_vars: Set[str] = set()
        for b_facts in all_branch_facts:
            for k, v in b_facts.items():
                if facts.get(k) != v:
                    modified_vars.add(k)

        # Merge each modified variable
        for v in modified_vars:
            branch_values = [b.get(v, facts.get(v, "POTENTIALLY_ZERO")) for b in all_branch_facts]
            if else_facts is None:
                branch_values.append(facts.get(v, "POTENTIALLY_ZERO"))

            if all(val == "DEFINITELY_ZERO" for val in branch_values):
                facts[v] = "DEFINITELY_ZERO"
            elif all(val == "DEFINITELY_NON_ZERO" for val in branch_values):
                facts[v] = "DEFINITELY_NON_ZERO"
            else:
                facts[v] = "POTENTIALLY_ZERO"

    def _analyze_loop_or_try(
        self,
        node: dict,
        facts: Dict[str, str],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        inner_facts = dict(facts)
        yield from self._analyze_block(node, inner_facts, file_path, source_lines)

        for k, v in inner_facts.items():
            if facts.get(k) != v:
                facts[k] = "POTENTIALLY_ZERO"

    def _check_divisions(
        self,
        node: dict,
        facts: Dict[str, str],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        ntype = node.get("type", "")
        if ntype in _SCOPE_NODES:
            return

        if ntype == "binary_operator":
            children = node.get("children", [])
            if len(children) >= 3 and children[1].get("text", "") in ("/", "//"):
                yield from self._eval_division_node(node, facts, file_path, source_lines)
                yield from self._check_divisions(children[0], facts, file_path, source_lines)
                return

        for child in node.get("children", []):
            yield from self._check_divisions(child, facts, file_path, source_lines)

    def _eval_division_node(
        self,
        binop_node: dict,
        facts: Dict[str, str],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        children = binop_node.get("children", [])
        if len(children) < 3:
            return
        op_text = children[1].get("text") or "/"
        right_node = children[2]
        right_text = right_node.get("text") or "?"
        right_type = right_node.get("type", "unknown")

        cls = self._classify(right_node)
        if cls == _Z.DEFINITELY_NON_ZERO:
            return

        if cls == _Z.DEFINITELY_ZERO:
            yield self._make_issue(
                node=binop_node,
                file_path=file_path,
                source_lines=source_lines,
                message=f"Division by zero: the divisor `{right_text}` is always zero.",
                evidence={
                    "operator": op_text,
                    "right_operand": right_text,
                    "right_node_type": right_type,
                    "classification": "definitely_zero",
                },
            )
            return

        # POTENTIALLY_ZERO: check if variable fact is known
        name = self._identifier_name(right_node)
        if name:
            fact = facts.get(name)
            if fact in ("GUARDED", "DEFINITELY_NON_ZERO"):
                return  # Safe
            if fact == "DEFINITELY_ZERO":
                yield self._make_issue(
                    node=binop_node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=f"Division by zero: the divisor `{right_text}` is always zero.",
                    evidence={
                        "operator": op_text,
                        "right_operand": right_text,
                        "right_node_type": right_type,
                        "classification": "definitely_zero",
                    },
                )
                return

        # General potentially-zero warning
        yield self._make_issue(
            node=binop_node,
            file_path=file_path,
            source_lines=source_lines,
            message=(
                f"Division by potentially zero value: the divisor "
                f"`{right_text}` may be zero at runtime.  "
                f"Add a zero-guard before dividing."
            ),
            evidence={
                "operator": op_text,
                "right_operand": right_text,
                "right_node_type": right_type,
                "classification": "potentially_zero",
            },
        )

    def _classify_assignment_rhs(self, rhs: Optional[dict]) -> _Z:
        if rhs is None:
            return _Z.POTENTIALLY_ZERO
        ntype = rhs.get("type", "")
        if ntype in ("integer", "float"):
            return self._classify_numeric_literal(rhs)
        if ntype in ("true", "false"):
            return _Z.DEFINITELY_NON_ZERO if (rhs.get("text") or "").lower() == "true" else _Z.DEFINITELY_ZERO
        if ntype == "unary_operator":
            return self._classify_unary(rhs)
        return _Z.POTENTIALLY_ZERO

    # ------------------------------------------------------------------
    # Divisor classification helpers
    # ------------------------------------------------------------------

    def _classify(self, node: dict) -> _Z:
        ntype = node.get("type", "")

        if ntype == "parenthesized_expression":
            inner = self._unwrap_parens(node)
            return self._classify(inner)

        if ntype in ("integer", "float"):
            return self._classify_numeric_literal(node)

        if ntype in ("true", "false"):
            text = (node.get("text") or "").strip().lower()
            if text == "true":
                return _Z.DEFINITELY_NON_ZERO
            if text == "false":
                return _Z.DEFINITELY_ZERO
            return _Z.POTENTIALLY_ZERO

        if ntype == "unary_operator":
            return self._classify_unary(node)

        if ntype == "conditional_expression":
            return self._classify_conditional(node)

        if ntype == "boolean_operator":
            return self._classify_boolean_op(node)

        if ntype == "binary_operator":
            return self._classify_constant_arithmetic(node)

        if ntype == "call":
            result = self._classify_safe_call(node)
            if result is not None:
                return result

        return _Z.POTENTIALLY_ZERO

    @staticmethod
    def _numeric_value(node: dict) -> Optional[float]:
        text = (node.get("text") or "").strip().replace("_", "")
        if not text:
            return None
        try:
            return float(int(text, 0))
        except (ValueError, TypeError):
            pass
        try:
            return float(text)
        except (ValueError, TypeError):
            return None

    def _classify_numeric_literal(self, node: dict) -> _Z:
        val = self._numeric_value(node)
        if val is None:
            return _Z.POTENTIALLY_ZERO
        return _Z.DEFINITELY_ZERO if val == 0.0 else _Z.DEFINITELY_NON_ZERO

    def _classify_unary(self, node: dict) -> _Z:
        children = node.get("children", [])
        if not children:
            return _Z.POTENTIALLY_ZERO
        op_text = (children[0].get("text") or "").strip()
        if op_text not in ("+", "-"):
            return _Z.POTENTIALLY_ZERO
        operand = children[-1]
        return self._classify(operand)

    def _classify_conditional(self, node: dict) -> _Z:
        children = node.get("children", [])
        non_kw = [c for c in children if (c.get("text") or "") not in ("if", "else")]
        if len(non_kw) < 3:
            return _Z.POTENTIALLY_ZERO
        cls_t = self._classify(non_kw[0])
        cls_f = self._classify(non_kw[2])
        if cls_t == _Z.DEFINITELY_NON_ZERO and cls_f == _Z.DEFINITELY_NON_ZERO:
            return _Z.DEFINITELY_NON_ZERO
        if cls_t == _Z.DEFINITELY_ZERO and cls_f == _Z.DEFINITELY_ZERO:
            return _Z.DEFINITELY_ZERO
        return _Z.POTENTIALLY_ZERO

    def _classify_boolean_op(self, node: dict) -> _Z:
        children = node.get("children", [])
        op_children = [c for c in children if (c.get("text") or "") not in ("or", "and")]
        kw_children = [c for c in children if (c.get("text") or "") in ("or", "and")]
        if not kw_children:
            return _Z.POTENTIALLY_ZERO
        op = kw_children[0].get("text", "")
        if op != "or" or len(op_children) < 2:
            return _Z.POTENTIALLY_ZERO
        right = op_children[-1]
        cls_r = self._classify(right)
        if cls_r == _Z.DEFINITELY_NON_ZERO:
            return _Z.DEFINITELY_NON_ZERO
        return _Z.POTENTIALLY_ZERO

    def _classify_constant_arithmetic(self, node: dict) -> _Z:
        val = self._try_eval_constant(node)
        if val is None:
            return _Z.POTENTIALLY_ZERO
        return _Z.DEFINITELY_ZERO if val == 0.0 else _Z.DEFINITELY_NON_ZERO

    def _try_eval_constant(self, node: dict) -> Optional[float]:
        ntype = node.get("type", "")
        if ntype == "parenthesized_expression":
            inner = self._unwrap_parens(node)
            return self._try_eval_constant(inner)
        if ntype in ("integer", "float"):
            return self._numeric_value(node)
        if ntype in ("true", "false"):
            return 1.0 if (node.get("text") or "").lower() == "true" else 0.0
        if ntype == "unary_operator":
            children = node.get("children", [])
            if not children:
                return None
            op = (children[0].get("text") or "").strip()
            val = self._try_eval_constant(children[-1])
            if val is None:
                return None
            if op == "-":
                return -val
            if op == "+":
                return val
            return None
        if ntype == "binary_operator":
            children = node.get("children", [])
            if len(children) < 3:
                return None
            op = (children[1].get("text") or "").strip()
            lv = self._try_eval_constant(children[0])
            rv = self._try_eval_constant(children[2])
            if lv is None or rv is None:
                return None
            try:
                if op == "+":
                    return lv + rv
                if op == "-":
                    return lv - rv
                if op == "*":
                    return lv * rv
                if op in ("/", "//"):
                    if rv == 0.0:
                        return None
                    return lv / rv if op == "/" else float(int(lv) // int(rv))
                if op == "**":
                    return float(lv ** rv)
            except (ZeroDivisionError, OverflowError, ValueError):
                return None
        return None

    def _classify_safe_call(self, node: dict) -> Optional[_Z]:
        children = node.get("children", [])
        if len(children) < 2:
            return None
        func_name = (children[0].get("text") or "").strip()
        args_node = children[1] if len(children) > 1 else None
        if args_node is None or args_node.get("type") != "argument_list":
            return None
        args = [
            c for c in args_node.get("children", [])
            if (c.get("text") or "") not in ("(", ")", ",")
            and c.get("type") not in ("(", ")", ",")
        ]
        if func_name == "max":
            if any(self._classify(a) == _Z.DEFINITELY_NON_ZERO for a in args):
                return _Z.DEFINITELY_NON_ZERO
        return None

    @staticmethod
    def _unwrap_parens(node: dict) -> dict:
        for child in node.get("children", []):
            if (child.get("text") or "") not in ("(", ")"):
                return child
        return node

    @staticmethod
    def _identifier_name(node: dict) -> Optional[str]:
        if node.get("type") == "identifier":
            return (node.get("text") or "").strip() or None
        return None

    @staticmethod
    def _if_condition(if_node: dict) -> Optional[dict]:
        children = if_node.get("children", [])
        for child in children:
            if (child.get("text") or "") not in ("if", "elif", ":", "else") \
                    and child.get("type") not in ("block", "else_clause", "elif_clause"):
                return child
        return None

    @staticmethod
    def _cond_guard_name(cond: dict) -> Optional[str]:
        ctype = cond.get("type", "")
        if ctype == "identifier":
            return (cond.get("text") or "").strip() or None

        if ctype == "parenthesized_expression":
            inner = cond
            for child in cond.get("children", []):
                if (child.get("text") or "") not in ("(", ")"):
                    inner = child
                    break
            return PythonDivisionByZero._cond_guard_name(inner)

        if ctype == "comparison_operator":
            children = cond.get("children", [])
            ops = [c.get("text") or "" for c in children]
            if "!=" not in ops:
                return None
            idx = ops.index("!=")
            left  = children[idx - 1] if idx > 0 else None
            right = children[idx + 1] if idx + 1 < len(children) else None

            def _is_id(n: Optional[dict]) -> Optional[str]:
                if n and n.get("type") == "identifier":
                    return (n.get("text") or "").strip() or None
                return None

            def _is_zero(n: Optional[dict]) -> bool:
                if n is None:
                    return False
                if n.get("type") in ("integer", "float"):
                    text = (n.get("text") or "").replace("_", "").strip()
                    try:
                        return float(text) == 0.0
                    except ValueError:
                        return False
                return False

            name_l = _is_id(left)
            name_r = _is_id(right)
            if name_l and _is_zero(right):
                return name_l
            if name_r and _is_zero(left):
                return name_r

        return None

    @staticmethod
    def _guard_name_from_assert(assert_node: dict) -> Optional[str]:
        children = assert_node.get("children", [])
        exprs = [c for c in children if (c.get("text") or "") not in ("assert", ",")]
        if exprs:
            return PythonDivisionByZero._cond_guard_name(exprs[0])
        return None
