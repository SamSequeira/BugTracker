"""
Lightweight semantic fact extractor for LLM bug detection.

Extracts concrete facts about function behavior using AST analysis.
Goal: Give LLM authoritative information to reason about bugs.

Does NOT attempt:
- Complete data-flow analysis
- Symbolic execution
- Cross-function analysis
- Type inference

Extracts only:
- Parameters
- Assignments (local & attribute)
- Returns
- Conditions (if/comparisons)
- Function calls
- Simple data flow (variable -> assignment -> return relationships)
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass

from app.services.llm_logic_reviewer.value_flow import extract_value_flow_for_function

logger = logging.getLogger(__name__)


@dataclass
class SemanticFact:
    """A concrete fact about function behavior."""

    file_role: str
    imports: List[str]
    symbol_types: List[str]
    operator_semantics: List[str]
    parameters: List[str]  # param names
    assignments: List[str]  # "var = expression" or "obj.attr = expression"
    returns: List[str]  # what's returned (expressions/variable names)
    conditions: List[str]  # "if X:", "X == Y", "not X", etc.
    calls: List[str]  # "func(args)", "obj.method(args)"
    data_flows: List[str]  # "var1 -> var2", "param -> return", etc.
    value_flow_summary: str = ""


def classify_file_role(file_path: str, code: str = "") -> str:
    """Classify the role of a file based on path and contents."""
    if not file_path:
        return "UNKNOWN"

    norm_path = file_path.replace("\\", "/").lower()
    file_name = Path(norm_path).name

    if file_name in ("settings.py", "config.py", "configuration.py") or "settings" in norm_path or "config" in norm_path:
        return "FRAMEWORK_CONFIGURATION" if ("django" in code.lower() or "flask" in code.lower() or "fastapi" in code.lower()) else "CONFIGURATION"
    if "test" in norm_path or file_name.startswith("test_") or file_name.endswith("_test.py"):
        return "TEST"
    if "migration" in norm_path or "alembic" in norm_path:
        return "MIGRATION"
    if "model" in norm_path or "entities" in norm_path:
        return "MODEL"
    if "api" in norm_path or "route" in norm_path or "endpoint" in norm_path or "controller" in norm_path or "views.py" in file_name:
        return "API_OR_CONTROLLER"
    if "service" in norm_path or "logic" in norm_path:
        return "BUSINESS_LOGIC"
    if "util" in norm_path or "helper" in norm_path:
        return "UTILITY"

    return "APPLICATION_LOGIC"


class SemanticAnalyzer:
    """Extracts semantic facts from a function using AST."""

    def __init__(
        self,
        function_code: str,
        function_name: str,
        file_path: str = "",
        frameworks: Optional[List[str]] = None,
        repo_index: Optional[Any] = None,
    ):
        self.function_code = function_code
        self.function_name = function_name
        self.file_path = file_path
        self.frameworks = frameworks or []
        self.repo_index = repo_index
        self.tree = None
        self.func_node = None
        self._parse()

    def _parse(self) -> None:
        """Parse function code."""
        try:
            self.tree = ast.parse(self.function_code)
            for node in ast.walk(self.tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.func_node = node
                    break
        except SyntaxError:
            logger.debug("Could not parse %s", self.function_name)

    def extract_facts(self) -> SemanticFact:
        """Extract all semantic facts from the function."""
        vf_summary = extract_value_flow_for_function(
            self.function_code, file_path=self.file_path, repo_index=self.repo_index
        )
        if not self.func_node and not self.tree:
            return SemanticFact(
                file_role=classify_file_role(self.file_path, self.function_code),
                imports=[],
                symbol_types=[],
                operator_semantics=[],
                parameters=[],
                assignments=[],
                returns=[],
                conditions=[],
                calls=[],
                data_flows=[],
                value_flow_summary=vf_summary,
            )

        return SemanticFact(
            file_role=classify_file_role(self.file_path, self.function_code),
            imports=self._extract_imports(),
            symbol_types=self._extract_symbol_types(),
            operator_semantics=self._extract_operator_semantics(),
            parameters=self._extract_parameters(),
            assignments=self._extract_assignments(),
            returns=self._extract_returns(),
            conditions=self._extract_conditions(),
            calls=self._extract_calls(),
            data_flows=self._extract_data_flows(),
            value_flow_summary=vf_summary,
        )

    def _extract_imports(self) -> List[str]:
        """Extract import statements from code tree if present."""
        if not self.tree:
            return []
        imports = []
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append(f"{mod}.{alias.name}" if mod else alias.name)
        return imports

    def _extract_symbol_types(self) -> List[str]:
        """Extract lightweight symbol type facts from assignments/annotations."""
        if not self.func_node and not self.tree:
            return []
        target_root = self.func_node or self.tree
        symbol_facts = []

        for node in ast.walk(target_root):
            if isinstance(node, ast.Assign):
                expr_unparsed = ast.unparse(node.value)
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        var_name = target.id
                        if "Path(" in expr_unparsed or "pathlib" in expr_unparsed or var_name.endswith("_DIR") or var_name.endswith("_PATH"):
                            symbol_facts.append(f"{var_name} -> pathlib.Path")
                        elif expr_unparsed.isdigit():
                            symbol_facts.append(f"{var_name} -> int")
                        elif expr_unparsed.startswith('"') or expr_unparsed.startswith("'"):
                            symbol_facts.append(f"{var_name} -> str")
                        elif expr_unparsed in ("True", "False"):
                            symbol_facts.append(f"{var_name} -> bool")
                        elif expr_unparsed.startswith("[") or expr_unparsed.startswith("{"):
                            symbol_facts.append(f"{var_name} -> container/config")

            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name):
                    symbol_facts.append(f"{node.target.id} -> {ast.unparse(node.annotation)}")

        return list(set(symbol_facts))

    def _is_path_like(self, expr_str: str) -> bool:
        """Return True if expression string looks like a filesystem path variable."""
        path_indicators = (
            "DIR", "PATH", "path", "Path", "dir", "root", "base",
            "templates", "static", "media", "assets", "uploads", "files",
        )
        return any(ind in expr_str for ind in path_indicators)

    def _extract_operator_semantics(self) -> List[str]:
        """Identify binary operators and clarify overloaded vs primitive semantics.

        Handles chained pathlib slash operators correctly:
          base_dir / 'static' / 'assets'
        Both the inner (base_dir / 'static') and outer BinOp nodes are detected
        as Path construction since the left operand is a nested BinOp with string RHS.
        """
        if not self.func_node and not self.tree:
            return []
        target_root = self.func_node or self.tree
        op_facts = []

        for node in ast.walk(target_root):
            if isinstance(node, ast.BinOp):
                left_str = ast.unparse(node.left)
                right_str = ast.unparse(node.right)

                if isinstance(node.op, ast.Div):
                    # Check if the left operand is itself a BinOp Div (chained path join)
                    left_is_path_chain = isinstance(node.left, ast.BinOp) and isinstance(node.left.op, ast.Div)
                    # Right side is a string literal
                    right_is_string = isinstance(node.right, ast.Constant) and isinstance(node.right.value, str)

                    if (
                        self._is_path_like(left_str)
                        or self._is_path_like(right_str)
                        or left_is_path_chain
                        or right_is_string  # path / 'subdir' is almost always a path join
                        or "/" in self.file_path
                    ):
                        full_expr = ast.unparse(node)
                        op_facts.append(f"'{full_expr}' is Path construction (pathlib.Path / string), NOT numeric division")
                    else:
                        op_facts.append(f"'{left_str} / {right_str}' is numeric division operation")

                elif isinstance(node.op, ast.Add):
                    if right_str.startswith('"') or right_str.startswith("'") or left_str.startswith('"') or left_str.startswith("'"):
                        op_facts.append(f"'{left_str} + {right_str}' is string concatenation, NOT arithmetic addition")

        return list(set(op_facts))

    def _extract_parameters(self) -> List[str]:
        """Extract function parameter names."""
        if not self.func_node or not self.func_node.args:
            return []

        params = []
        for arg in self.func_node.args.args:
            params.append(arg.arg)
        return params

    def _extract_assignments(self) -> List[str]:
        """Extract assignments: 'var = expr' and 'obj.attr = expr'."""
        if not self.func_node:
            return []
        assignments = []

        for node in ast.walk(self.func_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        expr = ast.unparse(node.value)
                        assignments.append(f"{target.id} = {expr}")
                    elif isinstance(target, ast.Attribute):
                        obj_name = ast.unparse(target.value)
                        expr = ast.unparse(node.value)
                        assignments.append(f"{obj_name}.{target.attr} = {expr}")

            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name):
                    op_name = node.op.__class__.__name__
                    expr = ast.unparse(node.value)
                    assignments.append(f"{node.target.id} {op_name} {expr}")

            elif isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.value:
                    expr = ast.unparse(node.value)
                    assignments.append(f"{node.target.id} = {expr}")

        return assignments

    def _extract_returns(self) -> List[str]:
        """Extract return statements: what's being returned."""
        if not self.func_node:
            return []
        returns = []

        for node in ast.walk(self.func_node):
            if isinstance(node, ast.Return):
                if node.value:
                    ret_expr = ast.unparse(node.value)
                    returns.append(ret_expr)
                else:
                    returns.append("None")

        return returns

    def _extract_conditions(self) -> List[str]:
        """Extract if conditions and comparisons."""
        if not self.func_node:
            return []
        conditions = []

        for node in ast.walk(self.func_node):
            if isinstance(node, ast.If):
                cond_expr = ast.unparse(node.test)
                conditions.append(f"if {cond_expr}:")

            elif isinstance(node, ast.Compare):
                comp_expr = ast.unparse(node)
                if comp_expr not in conditions:
                    conditions.append(comp_expr)
                    comp_lower = comp_expr.lower()
                    if any(k in comp_lower for k in ("expire", "expiry", "expiration")):
                        if ">" in comp_expr:
                            conditions.append(f"  Note: '{comp_expr}' evaluates True when time is PAST expiration (token/session is EXPIRED)")
                        elif "<" in comp_expr:
                            conditions.append(f"  Note: '{comp_expr}' evaluates True when time is BEFORE expiration (token/session is VALID)")

            elif isinstance(node, ast.BoolOp):
                bool_expr = ast.unparse(node)
                if bool_expr not in conditions:
                    conditions.append(bool_expr)

        return conditions

    def _extract_calls(self) -> List[str]:
        """Extract function calls."""
        if not self.func_node:
            return []
        calls = []

        for node in ast.walk(self.func_node):
            if isinstance(node, ast.Call):
                call_expr = ast.unparse(node)
                if len(call_expr) > 100:
                    call_expr = call_expr[:97] + "..."
                calls.append(call_expr)

        return calls

    def _extract_data_flows(self) -> List[str]:
        """Extract simple data flow relationships."""
        if not self.func_node:
            return []
        flows = []
        dependencies: Dict[str, Set[str]] = {}

        for node in ast.walk(self.func_node):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        deps = self._extract_names_from_expr(node.value)
                        if deps:
                            dependencies[target.id] = deps

            elif isinstance(node, ast.AugAssign):
                if isinstance(node.target, ast.Name):
                    deps = self._extract_names_from_expr(node.value)
                    deps.add(node.target.id)
                    if deps:
                        dependencies[node.target.id] = deps

        params = set(self._extract_parameters())
        returns_names = self._extract_return_names()

        for ret_name in returns_names:
            if ret_name in params:
                flows.append(f"{ret_name} -> return")

        for var_name, deps in dependencies.items():
            for dep in deps:
                if dep in params:
                    flows.append(f"{dep} -> {var_name}")

        for ret_name in returns_names:
            if ret_name in dependencies:
                flows.append(f"{ret_name} -> return")

        for var_name, deps in dependencies.items():
            for dep in deps:
                if dep in dependencies:
                    flows.append(f"{dep} -> {var_name}")

        return list(set(flows))

    def _extract_names_from_expr(self, node: ast.expr) -> Set[str]:
        """Extract variable names used in an expression."""
        names = set()
        for sub_node in ast.walk(node):
            if isinstance(sub_node, ast.Name):
                names.add(sub_node.id)
        return names

    def _extract_return_names(self) -> Set[str]:
        """Extract variable names that are returned."""
        names = set()
        if not self.func_node:
            return names

        for node in ast.walk(self.func_node):
            if isinstance(node, ast.Return) and node.value:
                if isinstance(node.value, ast.Name):
                    names.add(node.value.id)
                elif isinstance(node.value, (ast.Tuple, ast.List)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Name):
                            names.add(elt.id)

        return names


def extract_semantic_facts(
    function_code: str,
    function_name: str,
    file_path: str = "",
    frameworks: Optional[List[str]] = None,
    repo_index: Optional[Any] = None,
) -> str:
    """
    Extract semantic facts and format as text for LLM.

    Returns formatted fact string.
    """
    analyzer = SemanticAnalyzer(
        function_code,
        function_name,
        file_path=file_path,
        frameworks=frameworks,
        repo_index=repo_index,
    )
    facts = analyzer.extract_facts()

    lines = []
    lines.append(f"FUNCTION: {function_name}")
    lines.append(f"FILE ROLE: {facts.file_role}")
    if frameworks:
        lines.append(f"DETECTED FRAMEWORKS: {', '.join(frameworks)}")
    lines.append("")

    if facts.imports:
        lines.append("IMPORTS:")
        for imp in facts.imports:
            lines.append(f"  {imp}")
        lines.append("")

    if facts.symbol_types:
        lines.append("SYMBOL TYPES & FACTS:")
        for st in facts.symbol_types:
            lines.append(f"  {st}")
        lines.append("")

    if facts.operator_semantics:
        lines.append("OPERATOR SEMANTICS:")
        for op in facts.operator_semantics:
            lines.append(f"  {op}")
        lines.append("")

    if facts.parameters:
        lines.append("PARAMETERS:")
        for param in facts.parameters:
            lines.append(f"  {param}")
        lines.append("")

    if facts.assignments:
        lines.append("ASSIGNMENTS:")
        for assign in facts.assignments:
            lines.append(f"  {assign}")
        lines.append("")

    if facts.returns:
        lines.append("RETURNS:")
        for ret in facts.returns:
            lines.append(f"  {ret}")
        lines.append("")

    if facts.conditions:
        lines.append("CONDITIONS:")
        for cond in facts.conditions:
            lines.append(f"  {cond}")
        lines.append("")

    if facts.calls:
        lines.append("CALLS:")
        for call in facts.calls:
            lines.append(f"  {call}")
        lines.append("")

    if facts.data_flows:
        lines.append("DATA FLOW:")
        for flow in facts.data_flows:
            lines.append(f"  {flow}")
        lines.append("")

    if facts.value_flow_summary:
        lines.append(facts.value_flow_summary)
        lines.append("")

    return "\n".join(lines)

