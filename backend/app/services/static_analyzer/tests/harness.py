"""
harness.py — shared test infrastructure for rule audits.

All tests use hand-crafted AST dicts (no tree-sitter runtime required)
so they can run on any machine regardless of the tree-sitter version
installed in the project.

The AST shape matches what ASTGenerator._normalize_node produces:
  {
    "type": str,
    "text": str,
    "start": {"line": int, "column": int, "byte": int},
    "end":   {"line": int, "column": int, "byte": int},
    "children": [ ... ],
  }
"""

from __future__ import annotations
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Low-level AST builder helpers
# ---------------------------------------------------------------------------

def pos(line: int = 0, col: int = 0) -> dict:
    return {"line": line, "column": col, "byte": col}


def node(
    ntype: str,
    text: str = "",
    line: int = 0,
    col: int = 0,
    children: Optional[List[dict]] = None,
) -> dict:
    t = text or ""
    return {
        "type": ntype,
        "text": text,
        "start": pos(line, col),
        "end": pos(line, col + max(len(t), 1)),
        "children": children or [],
    }


def leaf(ntype: str, text: str, line: int = 0, col: int = 0) -> dict:
    return node(ntype, text, line, col)


# Convenience aliases
def ident(name: str, line: int = 0, col: int = 0) -> dict:
    return leaf("identifier", name, line, col)


def integer(value: str, line: int = 0, col: int = 0) -> dict:
    return leaf("integer", value, line, col)


def float_lit(value: str, line: int = 0, col: int = 0) -> dict:
    return leaf("float", value, line, col)


def number_lit(value: str, line: int = 0, col: int = 0) -> dict:
    """JavaScript number literal."""
    return leaf("number", value, line, col)


def true_lit(line: int = 0) -> dict:
    return leaf("true", "true", line)


def false_lit(line: int = 0) -> dict:
    return leaf("false", "false", line)


def null_lit(line: int = 0) -> dict:
    return leaf("null_literal", "null", line)


def string_lit(value: str, line: int = 0) -> dict:
    return leaf("string_literal", value, line)


def unary(op: str, operand: dict, line: int = 0) -> dict:
    return node(
        "unary_operator",
        f"{op}{operand['text']}",
        line,
        children=[leaf("operator", op, line), operand],
    )


def js_unary(op: str, operand: dict, line: int = 0) -> dict:
    return node(
        "unary_expression",
        f"{op}{operand['text']}",
        line,
        children=[leaf("operator", op, line), operand],
    )


def parens(inner: dict, line: int = 0) -> dict:
    return node(
        "parenthesized_expression",
        f"({inner['text']})",
        line,
        children=[leaf("(", "(", line), inner, leaf(")", ")", line)],
    )


def binop_node(left: dict, op: str, right: dict, line: int = 0) -> dict:
    """tree-sitter Python binary_operator."""
    return node(
        "binary_operator",
        f"{left['text']} {op} {right['text']}",
        line,
        children=[left, leaf("operator", op, line), right],
    )


def js_binop(left: dict, op: str, right: dict, line: int = 0) -> dict:
    """tree-sitter JavaScript binary_expression."""
    return node(
        "binary_expression",
        f"{left['text']} {op} {right['text']}",
        line,
        children=[left, leaf(op, op, line), right],
    )


def java_binop(left: dict, op: str, right: dict, line: int = 0) -> dict:
    """tree-sitter Java binary_expression."""
    return node(
        "binary_expression",
        f"{left['text']} {op} {right['text']}",
        line,
        children=[left, leaf(op, op, line), right],
    )


def cond_expr(true_val: dict, cond: dict, false_val: dict, line: int = 0) -> dict:
    return node(
        "conditional_expression",
        f"{true_val['text']} if {cond['text']} else {false_val['text']}",
        line,
        children=[
            true_val,
            leaf("if", "if", line),
            cond,
            leaf("else", "else", line),
            false_val,
        ],
    )


def bool_op(left: dict, op: str, right: dict, line: int = 0) -> dict:
    return node(
        "boolean_operator",
        f"{left['text']} {op} {right['text']}",
        line,
        children=[left, leaf(op, op, line), right],
    )


def arg_list(*args: dict, line: int = 0) -> dict:
    children: List[dict] = [leaf("(", "(", line)]
    for i, a in enumerate(args):
        if i:
            children.append(leaf(",", ",", line))
        children.append(a)
    children.append(leaf(")", ")", line))
    return node(
        "argument_list",
        f"({', '.join(a['text'] for a in args)})",
        line,
        children=children,
    )


def call_node(func_name: str, *args: dict, line: int = 0) -> dict:
    al = arg_list(*args, line=line)
    return node(
        "call",
        f"{func_name}({', '.join(a['text'] for a in args)})",
        line,
        children=[ident(func_name, line), al],
    )


def java_call(func_name: str, *args: dict, line: int = 0) -> dict:
    """Java method invocation node."""
    al = arg_list(*args, line=line)
    return node(
        "method_invocation",
        f"{func_name}({', '.join(a['text'] for a in args)})",
        line,
        children=[ident(func_name, line), al],
    )


def java_decimal_int(value: str, line: int = 0) -> dict:
    return leaf("decimal_integer_literal", value, line)


def java_decimal_float(value: str, line: int = 0) -> dict:
    return leaf("decimal_floating_point_literal", value, line)


def java_hex_int(value: str, line: int = 0) -> dict:
    return leaf("hex_integer_literal", value, line)


def module(*stmts: dict, line: int = 0) -> dict:
    return node(
        "module",
        "",
        0,
        children=list(stmts),
    )


def block(*stmts: dict, line: int = 0) -> dict:
    return node("block", "", line, children=list(stmts))


def if_stmt(cond: dict, body: dict, line: int = 0) -> dict:
    return node(
        "if_statement",
        f"if {cond['text']}:",
        line,
        children=[leaf("if", "if", line), cond, leaf(":", ":", line), body],
    )


def assert_stmt(expr: dict, line: int = 0) -> dict:
    return node(
        "assert_statement",
        f"assert {expr['text']}",
        line,
        children=[leaf("assert", "assert", line), expr],
    )


def comparison(left: dict, op: str, right: dict, line: int = 0) -> dict:
    return node(
        "comparison_operator",
        f"{left['text']} {op} {right['text']}",
        line,
        children=[left, leaf(op, op, line), right],
    )


def java_catch_clause(param_text: str = "Exception e", *body_stmts, line: int = 0) -> dict:
    param = node("catch_formal_parameter", param_text, line)
    body = node("block", "{}", line, children=list(body_stmts))
    return node(
        "catch_clause",
        f"catch ({param_text}) {{}}",
        line,
        children=[
            leaf("catch", "catch", line),
            param,
            body,
        ],
    )


def java_object_creation(class_name: str, line: int = 0) -> dict:
    type_id = leaf("type_identifier", class_name, line)
    return node(
        "object_creation_expression",
        f"new {class_name}()",
        line,
        children=[leaf("new", "new", line), type_id, leaf("(", "("), leaf(")", ")")],
    )


def try_with_resources(*body_stmts, line: int = 0) -> dict:
    body = block(*body_stmts, line=line)
    return node(
        "try_with_resources_statement",
        "try (...) {}",
        line,
        children=[leaf("try", "try", line), body],
    )


def with_stmt(inner: dict, line: int = 0) -> dict:
    """Python with statement."""
    return node(
        "with_statement",
        f"with ...: ...",
        line,
        children=[leaf("with", "with", line), inner],
    )


def java_while_true(*body_stmts, line: int = 0) -> dict:
    """while (true) { ... }"""
    cond = parens(true_lit(line), line)
    body = block(*body_stmts, line=line)
    return node(
        "while_statement",
        "while (true) {}",
        line,
        children=[
            leaf("while", "while", line),
            cond,
            body,
        ],
    )


def break_stmt(line: int = 0) -> dict:
    return leaf("break_statement", "break;", line)


def return_stmt(line: int = 0) -> dict:
    return leaf("return_statement", "return;", line)


def throw_stmt(line: int = 0) -> dict:
    return leaf("throw_statement", "throw e;", line)


def await_expr(inner: dict, line: int = 0) -> dict:
    return node(
        "await_expression",
        f"await {inner['text']}",
        line,
        children=[leaf("await", "await", line), inner],
    )


def for_loop(body: dict, line: int = 0) -> dict:
    return node(
        "for_statement",
        "for (...) {...}",
        line,
        children=[leaf("for", "for", line), body],
    )


def while_loop(cond: dict, body: dict, line: int = 0) -> dict:
    return node(
        "while_statement",
        "while (...) {...}",
        line,
        children=[leaf("while", "while", line), cond, body],
    )


def js_arrow_fn(body: dict, line: int = 0) -> dict:
    return node("arrow_function", "() => {...}", line, children=[body])


def js_fn(body: dict, line: int = 0) -> dict:
    return node("function_declaration", "function f() {...}", line, children=[body])


def js_async_fn(body: dict, line: int = 0) -> dict:
    return node("function_declaration", "async function f() {...}", line, children=[body])


def stmt_block(*stmts, line: int = 0) -> dict:
    """JavaScript statement_block."""
    return node("statement_block", "{...}", line, children=list(stmts))


def py_def(params_node: dict, body: dict, name: str = "f", line: int = 0) -> dict:
    return node(
        "function_definition",
        f"def {name}({params_node.get('text', '')}): ...",
        line,
        children=[
            leaf("def", "def", line),
            ident(name, line),
            params_node,
            leaf(":", ":", line),
            body,
        ],
    )


def py_params(*params: dict, line: int = 0) -> dict:
    return node("parameters", f"({', '.join(p['text'] for p in params)})", line, children=list(params))


def py_default_param(name: str, default: dict, line: int = 0) -> dict:
    return node(
        "default_parameter",
        f"{name}={default['text']}",
        line,
        children=[ident(name, line), leaf("=", "=", line), default],
    )


def py_list(line: int = 0) -> dict:
    return leaf("list", "[]", line)


def py_dict(line: int = 0) -> dict:
    return leaf("dictionary", "{}", line)


def py_set_call(line: int = 0) -> dict:
    """set() call as tree-sitter represents it."""
    return call_node("set", line=line)


def open_call(*args: dict, line: int = 0) -> dict:
    """Python open() call."""
    al = arg_list(*args, line=line)
    return node(
        "call",
        f"open({', '.join(a['text'] for a in args)})",
        line,
        children=[ident("open", line), al],
    )


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

class RuleTestRunner:
    """
    Minimal pytest-free test runner.
    Each test case is (description, rule, ast, expected_count, classification).
    """

    def __init__(self, rule_id: str):
        self.rule_id = rule_id
        self._cases: List[tuple] = []
        self._failures: List[str] = []
        self._passes: int = 0

    def must_flag(self, desc: str, rule: Any, ast: dict, min_count: int | str = 1, file_path: str = "f.py") -> None:
        """Register a case that MUST produce at least min_count issues."""
        if isinstance(min_count, str):
            file_path = min_count
            min_count = 1
        self._cases.append(("must_flag", desc, rule, ast, min_count, file_path))

    def must_not_flag(self, desc: str, rule: Any, ast: dict, file_path: str = "f.py") -> None:
        """Register a case that MUST produce zero issues."""
        self._cases.append(("must_not_flag", desc, rule, ast, 0, file_path))

    def run(self, verbose: bool = True) -> bool:
        if verbose:
            print(f"\n{'=' * 60}")
            print(f"  {self.rule_id}")
            print(f"{'=' * 60}")

        for case_type, desc, rule, ast_root, expected, file_path in self._cases:
            issues = []
            crash = None
            try:
                issues = list(rule.analyze(ast_root, file_path, []))
            except Exception as exc:
                crash = exc

            if crash is not None:
                self._failures.append(
                    f"  CRASH [{case_type}] {desc}: {type(crash).__name__}: {crash}"
                )
                continue

            count = len(issues)
            if case_type == "must_flag":
                if count >= expected:
                    self._passes += 1
                    if verbose:
                        cls_list = ", ".join(
                            i.evidence.get("classification", "?")
                            for i in issues
                            if hasattr(i, "evidence")
                        )
                        print(f"  OK  [flagged×{count}] {desc}")
                else:
                    self._failures.append(
                        f"  FAIL [false_negative] {desc} — expected ≥{expected} issue(s), got {count}"
                    )
            elif case_type == "must_not_flag":
                if count == 0:
                    self._passes += 1
                    if verbose:
                        print(f"  OK  [not_flagged  ] {desc}")
                else:
                    cls_list = [i.evidence.get("classification", "?") for i in issues
                                if hasattr(i, "evidence") and isinstance(i.evidence, dict)]
                    self._failures.append(
                        f"  FAIL [false_positive] {desc} — expected 0, got {count} {cls_list}"
                    )

        if verbose:
            print(f"\n  Passed: {self._passes}  Failed: {len(self._failures)}")
            if self._failures:
                for f in self._failures:
                    print(f)

        return len(self._failures) == 0

    @property
    def failures(self) -> List[str]:
        return self._failures

    @property
    def passes(self) -> int:
        return self._passes
