"""
Extracts individual function definitions (with source code and line numbers)
from a Python file, so each one can be sent to the local LLM independently.
"""

import ast
import logging
from pathlib import Path
from typing import NamedTuple, Optional

from app.services.llm_logic_reviewer import config

logger = logging.getLogger(__name__)

# Functions with these semantic keywords in their name are high-value targets
# for business logic analysis and must NEVER be skipped as trivial getters.
SEMANTIC_KEYWORDS = {
    "amount", "balance", "cache", "transaction", "delete", "summary",
    "wallet", "transfer", "payment", "pay", "order", "withdraw", "deposit",
    "calculate", "reconcile", "credit", "debit", "refund", "auth",
}


class ExtractedFunction(NamedTuple):
    name: str
    code: str
    start_line: int
    end_line: int
    file_path: str
    qualified_name: str = ""


def _is_test_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    Heuristically identify test functions that are pure assertions with no logic.
    Returns True if the function should be SKIPPED (not sent to LLM).
    """
    if not node.name.startswith("test_"):
        return False

    allowed_node_types = (
        ast.Expr, ast.Assert, ast.Call, ast.Return, ast.Pass,
        ast.Assign, ast.AugAssign, ast.AnnAssign
    )

    for stmt in node.body:
        if isinstance(stmt, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
            return False
        if not isinstance(stmt, allowed_node_types):
            return False

    return True


def _is_trivial_getter(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    Identify trivial getter/setter/property functions: single return or assignment.
    Returns True if the function should be SKIPPED (not sent to LLM).

    Never skips functions containing critical semantic keywords.
    Only skips if body has exactly 1 statement returning/setting a simple value.
    """
    name_lower = node.name.lower()
    if any(k in name_lower for k in SEMANTIC_KEYWORDS):
        return False

    looks_like_getter_setter = (
        node.name.startswith(("get_", "set_", "is_"))
        or any(
            (isinstance(dec, ast.Name) and dec.id == "property")
            or (isinstance(dec, ast.Attribute) and dec.attr == "property")
            for dec in node.decorator_list
        )
    )
    if not looks_like_getter_setter:
        return False

    # Only skip if the body has exactly 1 statement that is a pure Return or Assign
    if len(node.body) == 1:
        stmt = node.body[0]
        if isinstance(stmt, ast.Return):
            if stmt.value is None or isinstance(stmt.value, (ast.Constant, ast.Name, ast.Attribute)):
                return True
        elif isinstance(stmt, ast.Assign):
            if isinstance(stmt.value, (ast.Constant, ast.Name, ast.Attribute)):
                return True

    return False


def _should_skip_function(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """
    Determine if a function should be skipped (not sent to LLM for review).
    Returns True if the function is low-value and should be filtered out.
    """
    name_lower = node.name.lower()
    if any(k in name_lower for k in SEMANTIC_KEYWORDS):
        return False
    return _is_test_function(node) or _is_trivial_getter(node)


def extract_functions_from_file(file_path: str) -> list[ExtractedFunction]:
    """
    Parses a single .py file and returns every top-level and class-method
    function definition as an ExtractedFunction, skipping ones that are
    too short (LLM_MIN_FUNCTION_LINES) or too long (LLM_MAX_FUNCTION_CHARS),
    and also skipping test functions and trivial getters that would generate
    high false-positive rates from the LLM.
    """
    path = Path(file_path)
    if path.suffix != ".py":
        return []

    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        logger.warning("Could not read %s: %s", file_path, e)
        return []

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as e:
        logger.warning("Could not parse %s: %s", file_path, e)
        return []

    source_lines = source.splitlines()
    results: list[ExtractedFunction] = []
    norm_path = file_path.replace("\\", "/")

    class FunctionCollector(ast.NodeVisitor):
        def __init__(self):
            self.current_class: Optional[str] = None
            self.collected: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, Optional[str]]] = []

        def visit_ClassDef(self, node: ast.ClassDef):
            prev_class = self.current_class
            self.current_class = node.name
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.collected.append((item, self.current_class))
                elif isinstance(item, ast.ClassDef):
                    self.visit(item)
            self.current_class = prev_class

        def visit_FunctionDef(self, node: ast.FunctionDef):
            self.collected.append((node, self.current_class))

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
            self.collected.append((node, self.current_class))

    collector = FunctionCollector()
    # Iterate top level nodes to preserve order
    for top_node in ast.iter_child_nodes(tree):
        if isinstance(top_node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            collector.visit(top_node)

    for node, enclosing_class in collector.collected:
        # Skip low-value functions before checking length constraints
        if _should_skip_function(node):
            logger.debug(
                "Skipping low-value function %s in %s (test or trivial getter)",
                node.name, file_path
            )
            continue

        start_line = node.lineno
        end_line = getattr(node, "end_lineno", None)
        if end_line is None:
            continue

        num_lines = end_line - start_line + 1
        if num_lines < config.LLM_MIN_FUNCTION_LINES:
            continue

        code = "\n".join(source_lines[start_line - 1:end_line])

        if len(code) > config.LLM_MAX_FUNCTION_CHARS:
            code = code[: config.LLM_MAX_FUNCTION_CHARS] + "\n# ...(truncated)"

        qualname = f"{norm_path}::{enclosing_class}.{node.name}" if enclosing_class else f"{norm_path}::{node.name}"

        results.append(
            ExtractedFunction(
                name=node.name,
                code=code,
                start_line=start_line,
                end_line=end_line,
                file_path=file_path,
                qualified_name=qualname,
            )
        )

    return results
