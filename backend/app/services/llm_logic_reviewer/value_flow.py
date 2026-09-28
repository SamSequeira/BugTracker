"""
value_flow.py
-------------
Lightweight static value-flow analysis for the repository intelligence system.

GOAL
----
Extract structured evidence about how values move through Python code ΓÇö across
assignments, function calls, returns, attribute accesses, and data-structure
accesses ΓÇö and deliver it to the local LLM in a clearly labelled EXPLICIT /
INFERRED format.

SCOPE (what is tracked)
-----------------------
1.  Assignment sources     ΓÇö x = some_call()
2.  Return-value binding   ΓÇö result = fn()              (callee ΓåÆ variable ΓåÆ caller)
3.  Function arguments     ΓÇö fn(amount)                 (variable ΓåÆ fn param)
4.  Variable propagation   ΓÇö y = x
5.  Return values          ΓÇö return amount in a function
6.  Attribute access       ΓÇö obj.field
7.  Dictionary access      ΓÇö d["key"]
8.  Model fields           ΓÇö classes inheriting Base/Model
9.  API response fields    ΓÇö response["amount"] / data.get("amount")
10. Serializer/schema fields ΓÇö classes with a `fields` class attribute

EXPLICIT vs INFERRED
--------------------
Every fact is tagged with one of two evidence kinds:

    EXPLICIT ΓÇö grounded in concrete source: annotation, docstring, model-field
               name, constant, explicit conversion, or function name.
    INFERRED ΓÇö derived by name-pattern heuristics (e.g. `amount` ΓåÆ currency).

The LLM is always told which kind applies.

WHAT IS NOT DONE
----------------
- No full symbolic execution or type inference.
- No cross-file resolution without a RepositoryIndex.
- No fabrication of facts.
- No changes to existing static_analyzer rules or BaseRule subclasses.

PUBLIC API
----------
    extractor = ValueFlowExtractor(source_code, file_path, repo_index=None)
    graph     = extractor.extract()          # ValueFlowGraph
    text      = extractor.format_for_llm(graph)  # str ready for prompt injection
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evidence basis vocabulary (used in EvidenceTag.basis lists)
# ---------------------------------------------------------------------------
BASIS_ANNOTATION       = "annotation"
BASIS_DOCSTRING        = "docstring"
BASIS_VARIABLE_NAME    = "variable_name"
BASIS_FUNCTION_NAME    = "function_name"
BASIS_CONSTANT_NAME    = "constant_name"
BASIS_MODEL_FIELD      = "model_field"
BASIS_COMMENT          = "comment"
BASIS_API_SCHEMA       = "api_schema"
BASIS_EXPLICIT_CONV    = "explicit_conversion"

# Name-pattern heuristics for INFERRED tagging
_CURRENCY_HINTS   = re.compile(r"(price|amount|cost|fee|total|balance|charge|payment|dollars|cents|revenue|tax|discount)", re.I)
_TIMESTAMP_HINTS  = re.compile(r"(timestamp|ts|created_at|updated_at|expires?_at|time|date|epoch|utc)", re.I)
_IDENTIFIER_HINTS = re.compile(r"(id|uuid|pk|key|token|slug|ref|code)", re.I)
_BOOL_HINTS       = re.compile(r"(is_|has_|can_|should_|allow|valid|active|enabled)", re.I)
_COUNT_HINTS      = re.compile(r"(count|num|total|qty|quantity|length|size|limit|offset|page)", re.I)

# Model / ORM base class patterns (class-name heuristics)
_MODEL_BASE_NAMES = {"base", "model", "declarativebase", "document", "entity",
                     "abstractmodel", "basemodel", "mongoengine"}


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class EvidenceTag:
    """Tags a value-flow fact as explicit or inferred with a basis list."""
    kind: str               # "explicit" | "inferred"
    basis: List[str]        # one or more BASIS_* constants
    note: str               # human-readable note delivered to the LLM


@dataclass
class ValueNode:
    """
    Represents a variable and its semantic context.

    Fields map to the 'relationship' format described in the module docstring:

        variable:          name
        source:            source_expr   (e.g. "calculate_total()")
        source_contract:   source_contract  (e.g. "amount_cents")
        consumer:          consumer_expr  (e.g. "format_currency(amount)")
        consumer_contract: consumer_contract  (e.g. "dollars")
    """
    name: str
    annotation: Optional[str]
    source_expr: Optional[str]
    source_contract: Optional[str]
    consumer_expr: Optional[str]
    consumer_contract: Optional[str]
    file_path: str
    line_number: int
    evidence: EvidenceTag


@dataclass
class FlowEdge:
    """
    A directed value-flow relationship: producer ΓåÆ variable ΓåÆ consumer.

    kind values:
        "assignment"    ΓÇö x = expr
        "call_arg"      ΓÇö fn(x)  [x ΓåÆ fn's named param]
        "return"        ΓÇö return x  [function produces x]
        "attribute"     ΓÇö obj.field
        "dict_key"      ΓÇö d["key"]
        "model_field"   ΓÇö ORM model attribute
        "api_field"     ΓÇö response["field"] / data.get("field")
        "schema_field"  ΓÇö serializer / pydantic field declaration
    """
    kind: str
    producer: str
    variable: str
    consumer: str
    file_path: str
    line_number: int
    is_cross_file: bool
    evidence: EvidenceTag


@dataclass
class ValueFlowGraph:
    """Full value-flow result for a code unit."""
    nodes: List[ValueNode] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers: name-pattern inference
# ---------------------------------------------------------------------------

def _infer_semantic_hint(name: str) -> Optional[str]:
    """Return a human-readable semantic hint for a variable/field name, or None."""
    n = name.lower()
    if _CURRENCY_HINTS.search(n):
        return "likely represents a monetary/currency value"
    if _TIMESTAMP_HINTS.search(n):
        return "likely represents a timestamp or datetime"
    if _IDENTIFIER_HINTS.search(n):
        return "likely represents an identifier / key / reference"
    if _BOOL_HINTS.search(n):
        return "likely represents a boolean flag"
    if _COUNT_HINTS.search(n):
        return "likely represents a numeric count or quantity"
    return None


def _explicit_tag(basis: List[str], note: str) -> EvidenceTag:
    return EvidenceTag(kind="explicit", basis=basis, note=note)


def _inferred_tag(basis: List[str], note: str) -> EvidenceTag:
    return EvidenceTag(kind="inferred", basis=basis, note=note)


def _evidence_for_name(name: str, annotation: Optional[str] = None,
                        docstring: Optional[str] = None) -> EvidenceTag:
    """Choose explicit or inferred evidence for a name binding."""
    basis: List[str] = []
    notes: List[str] = []

    if annotation:
        basis.append(BASIS_ANNOTATION)
        notes.append(f"annotated as {annotation!r}")

    if docstring and name in docstring:
        basis.append(BASIS_DOCSTRING)
        notes.append("name appears in docstring")

    if basis:
        return _explicit_tag(basis or [BASIS_VARIABLE_NAME], "; ".join(notes))

    # Fall back to name-pattern inference
    hint = _infer_semantic_hint(name)
    if hint:
        return _inferred_tag([BASIS_VARIABLE_NAME], hint)

    return _inferred_tag([BASIS_VARIABLE_NAME], f"no annotation or docstring found for {name!r}")


# ---------------------------------------------------------------------------
# AST utilities
# ---------------------------------------------------------------------------

def _call_name(node: ast.Call) -> str:
    """Return a readable name for a Call node (e.g. 'fn' or 'obj.method')."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        obj = ast.unparse(func.value)
        return f"{obj}.{func.attr}"
    return ast.unparse(func)


def _annotation_str(ann_node: Optional[ast.expr]) -> Optional[str]:
    if ann_node is None:
        return None
    try:
        return ast.unparse(ann_node)
    except Exception:
        return None


def _is_model_class(node: ast.ClassDef) -> bool:
    """Heuristic: does this class inherit from a known ORM/model base?"""
    for base in node.bases:
        base_str = ast.unparse(base).lower()
        # Remove generic parameters e.g. "Base[T]" -> "base"
        base_name = re.split(r"[\[\(]", base_str)[0].split(".")[-1]
        if base_name in _MODEL_BASE_NAMES:
            return True
    return False


def _is_schema_class(node: ast.ClassDef) -> bool:
    """Heuristic: does this class look like a serializer/pydantic schema?"""
    for base in node.bases:
        base_str = ast.unparse(base).lower()
        if any(k in base_str for k in ("schema", "serializer", "basemodel", "form")):
            return True
    # Also check if it has a `fields` class attribute
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id == "fields":
                    return True
    return False


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

class ValueFlowExtractor:
    """
    Extracts value-flow facts from Python source code using ast.

    Parameters
    ----------
    source_code : str
        Raw Python source (function, class, or module level).
    file_path : str
        Logical path of the file (used in output and for cross-file detection).
    repo_index : optional RepositoryIndex
        When provided, used to resolve call arguments to named parameters and
        to detect cross-file flows.
    """

    def __init__(
        self,
        source_code: str,
        file_path: str,
        repo_index: Any = None,       # RepositoryIndex | None  (lazy import)
    ) -> None:
        self.source_code = source_code
        self.file_path = file_path
        self.repo_index = repo_index
        self._tree: Optional[ast.Module] = None
        self._parse()

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse(self) -> None:
        try:
            self._tree = ast.parse(self.source_code)
        except SyntaxError as exc:
            logger.debug("ValueFlowExtractor: parse error in %s: %s", self.file_path, exc)
            self._tree = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(self) -> ValueFlowGraph:
        """Walk the AST and return a populated ValueFlowGraph."""
        graph = ValueFlowGraph()
        if self._tree is None:
            return graph

        # Collect docstrings and annotations per function to help tagging
        self._func_docstrings: Dict[str, str] = {}
        self._func_annotations: Dict[str, Dict[str, str]] = {}  # fname -> {param: annotation}
        self._preindex_functions()

        for node in ast.walk(self._tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._extract_from_function(node, graph)
            elif isinstance(node, ast.ClassDef):
                self._extract_from_class(node, graph)

        # Module-level assignments (top-level variable flows)
        self._extract_module_level(graph)

        return graph

    def format_for_llm(self, graph: ValueFlowGraph) -> str:
        """
        Render a ValueFlowGraph as a structured text block for LLM prompt injection.

        Output sections:
            VALUE FLOW ANALYSIS:
            EXPLICIT: ...
            INFERRED: ...
            CROSS-FUNCTION FLOW: ...
            UNRESOLVED: ...
        """
        if not graph.nodes and not graph.edges and not graph.unresolved:
            return ""

        lines: List[str] = ["VALUE FLOW ANALYSIS:"]

        # ----- Explicit edges & nodes -----
        explicit_lines: List[str] = []
        for edge in graph.edges:
            if edge.evidence.kind == "explicit":
                explicit_lines.append(self._format_edge(edge))
        for node in graph.nodes:
            if node.evidence.kind == "explicit":
                explicit_lines.append(self._format_node(node))

        if explicit_lines:
            lines.append("")
            lines.append("EXPLICIT:")
            lines.extend(explicit_lines)

        # ----- Inferred edges & nodes -----
        inferred_lines: List[str] = []
        for edge in graph.edges:
            if edge.evidence.kind == "inferred":
                inferred_lines.append(self._format_edge(edge))
        for node in graph.nodes:
            if node.evidence.kind == "inferred":
                inferred_lines.append(self._format_node(node))

        if inferred_lines:
            lines.append("")
            lines.append("INFERRED:")
            lines.extend(inferred_lines)

        # ----- Cross-function flow -----
        cross_edges = [e for e in graph.edges if e.is_cross_file]
        call_arg_edges = [e for e in graph.edges if e.kind == "call_arg" and not e.is_cross_file]
        return_edges = [e for e in graph.edges if e.kind == "return"]

        if cross_edges or call_arg_edges or return_edges:
            lines.append("")
            lines.append("CROSS-FUNCTION FLOW:")

        if call_arg_edges or cross_edges:
            lines.append("  caller -> argument -> parameter")
            for edge in call_arg_edges + cross_edges:
                if edge.kind in ("call_arg", "assignment"):
                    ev_label = f"[{edge.evidence.kind.upper()}: {', '.join(edge.evidence.basis)}]"
                    lines.append(f"    {edge.producer}({edge.variable}) -> {edge.consumer}")
                    lines.append(f"    {ev_label}")

        if return_edges:
            lines.append("  callee -> return value -> caller variable")
            for edge in return_edges:
                ev_label = f"[{edge.evidence.kind.upper()}: {', '.join(edge.evidence.basis)}]"
                lines.append(f"    {edge.producer}() -> {edge.variable} -> {edge.consumer}")
                lines.append(f"    {ev_label}")

        # ----- Unresolved -----
        if graph.unresolved:
            lines.append("")
            lines.append("UNRESOLVED:")
            for sym in graph.unresolved:
                lines.append(f"  {sym} -- not found in repository index")

        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal: pre-index functions for annotation/docstring lookups
    # ------------------------------------------------------------------

    def _preindex_functions(self) -> None:
        if not self._tree:
            return
        self._local_functions: Set[str] = set()
        for node in ast.walk(self._tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._local_functions.add(node.name)
                # Docstring
                docstring = ast.get_docstring(node) or ""
                self._func_docstrings[node.name] = docstring

                # Parameter annotations
                ann_map: Dict[str, str] = {}
                for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
                    if arg.annotation:
                        ann_map[arg.arg] = _annotation_str(arg.annotation) or ""
                self._func_annotations[node.name] = ann_map

    def _is_builtin_or_local(self, name: str) -> bool:
        if hasattr(self, "_local_functions") and name in self._local_functions:
            return True
        import builtins
        return hasattr(builtins, name)

    # ------------------------------------------------------------------
    # Internal: function-level extraction
    # ------------------------------------------------------------------

    def _extract_from_function(
        self, func: ast.FunctionDef | ast.AsyncFunctionDef, graph: ValueFlowGraph
    ) -> None:
        """Extract all value-flow facts from a single function definition."""
        func_name = func.name
        docstring = self._func_docstrings.get(func_name, "")
        ann_map = self._func_annotations.get(func_name, {})
        return_ann = _annotation_str(func.returns)

        # Track locally assigned variables for propagation
        local_vars: Dict[str, str] = {}  # name -> source_expr

        for stmt in ast.walk(func):
            if isinstance(stmt, ast.Assign):
                self._process_assign(stmt, func_name, docstring, ann_map, local_vars, graph)

            elif isinstance(stmt, ast.AnnAssign):
                self._process_ann_assign(stmt, func_name, docstring, graph)

            elif isinstance(stmt, ast.AugAssign):
                self._process_aug_assign(stmt, func_name, graph)

            elif isinstance(stmt, ast.Return):
                self._process_return(stmt, func_name, return_ann, docstring, graph)

            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                # Standalone call  e.g.  do_something(amount)
                self._process_call_args(stmt.value, func_name, docstring, ann_map, graph)

        # Attribute accesses (load-context only)
        for node in ast.walk(func):
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                self._process_attribute(node, func_name, graph)

        # Dict subscript accesses
        for node in ast.walk(func):
            if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
                self._process_subscript(node, func_name, graph)

    # ------------------------------------------------------------------
    # Internal: class-level extraction
    # ------------------------------------------------------------------

    def _extract_from_class(self, cls: ast.ClassDef, graph: ValueFlowGraph) -> None:
        """Extract model fields and schema fields from class definitions."""
        if _is_model_class(cls):
            self._extract_model_fields(cls, graph)
        if _is_schema_class(cls):
            self._extract_schema_fields(cls, graph)

    def _extract_model_fields(self, cls: ast.ClassDef, graph: ValueFlowGraph) -> None:
        """Extract ORM/model field declarations (class body assignments)."""
        for stmt in cls.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name):
                        field_name = tgt.id
                        if field_name.startswith("_"):
                            continue
                        source_expr = ast.unparse(stmt.value)
                        ev = _explicit_tag([BASIS_MODEL_FIELD],
                                           f"field declared in model class {cls.name!r}")
                        graph.edges.append(FlowEdge(
                            kind="model_field",
                            producer=cls.name,
                            variable=field_name,
                            consumer="",
                            file_path=self.file_path,
                            line_number=stmt.lineno,
                            is_cross_file=False,
                            evidence=ev,
                        ))
                        hint = _infer_semantic_hint(field_name)
                        node_ev = (
                            _explicit_tag([BASIS_MODEL_FIELD, BASIS_VARIABLE_NAME],
                                          f"model field {field_name!r} in {cls.name!r}")
                            if not hint
                            else _inferred_tag([BASIS_MODEL_FIELD, BASIS_VARIABLE_NAME], hint)
                        )
                        graph.nodes.append(ValueNode(
                            name=field_name,
                            annotation=None,
                            source_expr=source_expr,
                            source_contract=cls.name,
                            consumer_expr=None,
                            consumer_contract=None,
                            file_path=self.file_path,
                            line_number=stmt.lineno,
                            evidence=node_ev,
                        ))

            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                field_name = stmt.target.id
                if field_name.startswith("_"):
                    continue
                annotation = _annotation_str(stmt.annotation)
                ev = _explicit_tag([BASIS_MODEL_FIELD, BASIS_ANNOTATION],
                                   f"annotated field in model class {cls.name!r}")
                graph.edges.append(FlowEdge(
                    kind="model_field",
                    producer=cls.name,
                    variable=field_name,
                    consumer="",
                    file_path=self.file_path,
                    line_number=stmt.lineno,
                    is_cross_file=False,
                    evidence=ev,
                ))
                graph.nodes.append(ValueNode(
                    name=field_name,
                    annotation=annotation,
                    source_expr=None,
                    source_contract=cls.name,
                    consumer_expr=None,
                    consumer_contract=None,
                    file_path=self.file_path,
                    line_number=stmt.lineno,
                    evidence=ev,
                ))

    def _extract_schema_fields(self, cls: ast.ClassDef, graph: ValueFlowGraph) -> None:
        """Extract serializer/pydantic/schema field declarations."""
        for stmt in cls.body:
            # AnnAssign: field: Type (pydantic style)
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                field_name = stmt.target.id
                if field_name.startswith("_"):
                    continue
                annotation = _annotation_str(stmt.annotation)
                ev = _explicit_tag([BASIS_API_SCHEMA, BASIS_ANNOTATION],
                                   f"schema field {field_name!r} in {cls.name!r}")
                graph.edges.append(FlowEdge(
                    kind="schema_field",
                    producer=cls.name,
                    variable=field_name,
                    consumer="",
                    file_path=self.file_path,
                    line_number=stmt.lineno,
                    is_cross_file=False,
                    evidence=ev,
                ))
                graph.nodes.append(ValueNode(
                    name=field_name,
                    annotation=annotation,
                    source_expr=None,
                    source_contract=cls.name,
                    consumer_expr=None,
                    consumer_contract=None,
                    file_path=self.file_path,
                    line_number=stmt.lineno,
                    evidence=ev,
                ))

            # Assign: fields = [...] / fields = {"field": ..., ...}
            elif isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id == "fields":
                        # The class declares a `fields` attribute; track it as schema evidence
                        ev = _explicit_tag([BASIS_API_SCHEMA],
                                           f"'fields' attribute declared in schema class {cls.name!r}")
                        graph.edges.append(FlowEdge(
                            kind="schema_field",
                            producer=cls.name,
                            variable="fields",
                            consumer="",
                            file_path=self.file_path,
                            line_number=stmt.lineno,
                            is_cross_file=False,
                            evidence=ev,
                        ))

    # ------------------------------------------------------------------
    # Internal: module-level extraction
    # ------------------------------------------------------------------

    def _extract_module_level(self, graph: ValueFlowGraph) -> None:
        """Extract top-level assignments (module constants / API calls)."""
        if not self._tree:
            return
        for stmt in self._tree.body:
            if isinstance(stmt, ast.Assign):
                for tgt in stmt.targets:
                    if isinstance(tgt, ast.Name) and tgt.id.isupper():
                        # Module-level constant
                        ev = _explicit_tag([BASIS_CONSTANT_NAME],
                                           f"module-level constant {tgt.id!r}")
                        graph.edges.append(FlowEdge(
                            kind="assignment",
                            producer=ast.unparse(stmt.value),
                            variable=tgt.id,
                            consumer="",
                            file_path=self.file_path,
                            line_number=stmt.lineno,
                            is_cross_file=False,
                            evidence=ev,
                        ))

    # ------------------------------------------------------------------
    # Internal: statement-level processors
    # ------------------------------------------------------------------

    def _process_assign(
        self,
        stmt: ast.Assign,
        func_name: str,
        docstring: str,
        ann_map: Dict[str, str],
        local_vars: Dict[str, str],
        graph: ValueFlowGraph,
    ) -> None:
        value_str = ast.unparse(stmt.value)
        lineno = stmt.lineno

        for tgt in stmt.targets:
            if not isinstance(tgt, ast.Name):
                continue
            var_name = tgt.id
            annotation = ann_map.get(var_name)
            local_vars[var_name] = value_str

            # Variable propagation: y = x
            if isinstance(stmt.value, ast.Name):
                src = stmt.value.id
                ev = _evidence_for_name(var_name, annotation, docstring)
                graph.edges.append(FlowEdge(
                    kind="assignment",
                    producer=src,
                    variable=var_name,
                    consumer=func_name,
                    file_path=self.file_path,
                    line_number=lineno,
                    is_cross_file=False,
                    evidence=ev,
                ))
                consumer_expr, consumer_contract = self._find_consumer(var_name, func_name)
                graph.nodes.append(ValueNode(
                    name=var_name,
                    annotation=annotation,
                    source_expr=src,
                    source_contract=None,
                    consumer_expr=consumer_expr,
                    consumer_contract=consumer_contract,
                    file_path=self.file_path,
                    line_number=lineno,
                    evidence=ev,
                ))

            # Return-value binding: result = fn()
            elif isinstance(stmt.value, ast.Call):
                call_name = _call_name(stmt.value)
                ev = _evidence_for_name(var_name, annotation, docstring)

                # Attempt to resolve what the callee returns (source_contract)
                source_contract = self._resolve_return_name(call_name)

                # Attempt to detect cross-file
                is_cross = self._is_cross_file_call(call_name, func_name)

                # Check if truly unresolved
                if self.repo_index and not self._is_builtin_or_local(call_name):
                    try:
                        if self.repo_index.find_function(call_name) is None:
                            if call_name not in graph.unresolved:
                                graph.unresolved.append(call_name)
                    except Exception:
                        pass

                graph.edges.append(FlowEdge(
                    kind="assignment",
                    producer=call_name,
                    variable=var_name,
                    consumer=func_name,
                    file_path=self.file_path,
                    line_number=lineno,
                    is_cross_file=is_cross,
                    evidence=ev,
                ))

                # Create a rich ValueNode
                consumer_expr, consumer_contract = self._find_consumer(var_name, func_name)
                graph.nodes.append(ValueNode(
                    name=var_name,
                    annotation=annotation,
                    source_expr=f"{call_name}()",
                    source_contract=source_contract,
                    consumer_expr=consumer_expr,
                    consumer_contract=consumer_contract,
                    file_path=self.file_path,
                    line_number=lineno,
                    evidence=ev,
                ))

                # Also track the call arguments for the callee
                self._process_call_args(stmt.value, func_name, docstring, ann_map, graph)

            # Any other RHS ΓÇö just track the assignment source
            else:
                ev = _evidence_for_name(var_name, annotation, docstring)
                graph.edges.append(FlowEdge(
                    kind="assignment",
                    producer=value_str,
                    variable=var_name,
                    consumer=func_name,
                    file_path=self.file_path,
                    line_number=lineno,
                    is_cross_file=False,
                    evidence=ev,
                ))
                consumer_expr, consumer_contract = self._find_consumer(var_name, func_name)
                graph.nodes.append(ValueNode(
                    name=var_name,
                    annotation=annotation,
                    source_expr=value_str,
                    source_contract=None,
                    consumer_expr=consumer_expr,
                    consumer_contract=consumer_contract,
                    file_path=self.file_path,
                    line_number=lineno,
                    evidence=ev,
                ))

    def _process_ann_assign(
        self,
        stmt: ast.AnnAssign,
        func_name: str,
        docstring: str,
        graph: ValueFlowGraph,
    ) -> None:
        if not isinstance(stmt.target, ast.Name):
            return
        var_name = stmt.target.id
        annotation = _annotation_str(stmt.annotation)
        ev = _explicit_tag([BASIS_ANNOTATION],
                           f"{var_name!r} annotated as {annotation!r}")

        source_expr: Optional[str] = None
        if stmt.value:
            source_expr = ast.unparse(stmt.value)

        graph.nodes.append(ValueNode(
            name=var_name,
            annotation=annotation,
            source_expr=source_expr,
            source_contract=None,
            consumer_expr=None,
            consumer_contract=None,
            file_path=self.file_path,
            line_number=stmt.lineno,
            evidence=ev,
        ))

    def _process_aug_assign(
        self,
        stmt: ast.AugAssign,
        func_name: str,
        graph: ValueFlowGraph,
    ) -> None:
        if not isinstance(stmt.target, ast.Name):
            return
        var_name = stmt.target.id
        ev = _inferred_tag([BASIS_VARIABLE_NAME], f"augmented assignment to {var_name!r}")
        graph.edges.append(FlowEdge(
            kind="assignment",
            producer=ast.unparse(stmt.value),
            variable=var_name,
            consumer=func_name,
            file_path=self.file_path,
            line_number=stmt.lineno,
            is_cross_file=False,
            evidence=ev,
        ))

    def _process_return(
        self,
        stmt: ast.Return,
        func_name: str,
        return_ann: Optional[str],
        docstring: str,
        graph: ValueFlowGraph,
    ) -> None:
        if stmt.value is None:
            return

        ret_str = ast.unparse(stmt.value)

        # Determine evidence
        if return_ann:
            ev = _explicit_tag([BASIS_ANNOTATION, BASIS_FUNCTION_NAME],
                               f"{func_name!r} return annotated as {return_ann!r}")
        else:
            hint = None
            if isinstance(stmt.value, ast.Name):
                hint = _infer_semantic_hint(stmt.value.id)
            ev = (
                _inferred_tag([BASIS_VARIABLE_NAME], hint or f"{func_name!r} returns {ret_str!r}")
            )

        # Resolve caller variable (what the caller binds this return to)
        caller_var = self._find_caller_variable(func_name)

        graph.edges.append(FlowEdge(
            kind="return",
            producer=func_name,
            variable=ret_str,
            consumer=caller_var or "(caller)",
            file_path=self.file_path,
            line_number=stmt.lineno,
            is_cross_file=False,
            evidence=ev,
        ))

    def _process_call_args(
        self,
        call: ast.Call,
        caller_name: str,
        docstring: str,
        ann_map: Dict[str, str],
        graph: ValueFlowGraph,
    ) -> None:
        """Track positional arguments passed to a call as call_arg edges."""
        callee_name = _call_name(call)
        callee_params = self._resolve_params(callee_name)

        for i, arg in enumerate(call.args):
            arg_str = ast.unparse(arg)
            # Match to callee parameter name if known
            param_name: Optional[str] = None
            if callee_params and i < len(callee_params):
                param_name = callee_params[i]

            # Determine is_cross_file
            is_cross = self._is_cross_file_call(callee_name, caller_name)

            # Choose evidence
            var_annotation = ann_map.get(arg_str) if isinstance(arg, ast.Name) else None
            if param_name and var_annotation:
                ev = _explicit_tag([BASIS_ANNOTATION, BASIS_VARIABLE_NAME],
                                   f"arg {arg_str!r} maps to param {param_name!r}")
            elif param_name:
                ev = _inferred_tag([BASIS_VARIABLE_NAME, BASIS_FUNCTION_NAME],
                                   f"positional arg {i} -> param {param_name!r}")
            else:
                ev = _inferred_tag([BASIS_VARIABLE_NAME],
                                   f"positional arg {i} to {callee_name!r}")

            graph.edges.append(FlowEdge(
                kind="call_arg",
                producer=caller_name,
                variable=arg_str,
                consumer=f"{callee_name}.{param_name}" if param_name else callee_name,
                file_path=self.file_path,
                line_number=call.lineno if hasattr(call, "lineno") else 0,
                is_cross_file=is_cross,
                evidence=ev,
            ))

        # Keyword arguments
        for kw in call.keywords:
            if kw.arg is None:
                continue  # **kwargs unpacking
            arg_str = ast.unparse(kw.value)
            is_cross = self._is_cross_file_call(callee_name, caller_name)
            ev = _explicit_tag([BASIS_VARIABLE_NAME, BASIS_FUNCTION_NAME],
                               f"keyword arg {kw.arg!r}={arg_str!r} to {callee_name!r}")
            graph.edges.append(FlowEdge(
                kind="call_arg",
                producer=caller_name,
                variable=arg_str,
                consumer=f"{callee_name}.{kw.arg}",
                file_path=self.file_path,
                line_number=call.lineno if hasattr(call, "lineno") else 0,
                is_cross_file=is_cross,
                evidence=ev,
            ))

    def _process_attribute(
        self,
        node: ast.Attribute,
        func_name: str,
        graph: ValueFlowGraph,
    ) -> None:
        """Track attribute accesses: obj.field."""
        obj_str = ast.unparse(node.value)
        attr = node.attr
        ev = _inferred_tag([BASIS_VARIABLE_NAME],
                           f"attribute access {obj_str!r}.{attr!r}")
        graph.edges.append(FlowEdge(
            kind="attribute",
            producer=obj_str,
            variable=attr,
            consumer=func_name,
            file_path=self.file_path,
            line_number=node.col_offset,   # lineno not always available in nested walk
            is_cross_file=False,
            evidence=ev,
        ))

    def _process_subscript(
        self,
        node: ast.Subscript,
        func_name: str,
        graph: ValueFlowGraph,
    ) -> None:
        """Track dict / list subscript accesses: d["key"] or response["amount"]."""
        container_str = ast.unparse(node.value)
        slice_node = node.slice

        # Only track string-literal keys (API field / dict key access)
        if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
            key = slice_node.value
            # Detect API-response patterns by naming
            is_api = any(k in container_str.lower() for k in
                         ("response", "data", "result", "payload", "json", "body"))
            kind = "api_field" if is_api else "dict_key"
            note = (f"API response field {key!r} from {container_str!r}"
                    if is_api else f"dict key {key!r} from {container_str!r}")
            ev = _explicit_tag([BASIS_API_SCHEMA if is_api else BASIS_VARIABLE_NAME,
                                BASIS_VARIABLE_NAME], note)
            graph.edges.append(FlowEdge(
                kind=kind,
                producer=container_str,
                variable=key,
                consumer=func_name,
                file_path=self.file_path,
                line_number=node.col_offset,
                is_cross_file=False,
                evidence=ev,
            ))

        # Also detect: data.get("key", default) patterns
        # These are already caught via ast.Call processing; no duplicate here.

    # ------------------------------------------------------------------
    # Internal: resolution helpers (use repo_index when available)
    # ------------------------------------------------------------------

    def _resolve_params(self, callee_name: str) -> List[str]:
        """Return parameter names for callee_name from repo index, or []."""
        if not self.repo_index:
            return []
        try:
            fn_entry = self.repo_index.find_function(callee_name)
            if fn_entry:
                return list(fn_entry.parameters)
        except Exception:
            pass
        return []

    def _resolve_return_name(self, callee_name: str) -> Optional[str]:
        """Return the most prominent return expression for callee from repo index."""
        if not self.repo_index:
            return None
        try:
            fn_entry = self.repo_index.find_function(callee_name)
            if fn_entry and fn_entry.returns:
                return fn_entry.returns[0]
        except Exception:
            pass
        return None

    def _is_cross_file_call(self, callee_name: str, caller_name: str) -> bool:
        """Detect whether callee lives in a different file from the current source."""
        if not self.repo_index:
            return False
        try:
            fn_entry = self.repo_index.find_function(callee_name)
            if fn_entry:
                callee_file = fn_entry.file_path.replace("\\", "/")
                current = self.file_path.replace("\\", "/")
                return callee_file != current
        except Exception:
            pass
        return False

    def _find_consumer(
        self, var_name: str, func_name: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Scan the function body to find the first call that uses var_name as an argument.
        Returns (consumer_call_expr, param_name_in_consumer).
        """
        if not self._tree:
            return None, None
        for node in ast.walk(self._tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        for i, arg in enumerate(sub.args):
                            if isinstance(arg, ast.Name) and arg.id == var_name:
                                callee = _call_name(sub)
                                params = self._resolve_params(callee)
                                param = params[i] if params and i < len(params) else None
                                return ast.unparse(sub), param
                        for kw in sub.keywords:
                            if isinstance(kw.value, ast.Name) and kw.value.id == var_name:
                                callee = _call_name(sub)
                                return ast.unparse(sub), kw.arg
        return None, None

    def _find_caller_variable(self, func_name: str) -> Optional[str]:
        """
        Find the variable name at the call site where func_name's return value
        is captured (e.g.  result = func_name()).
        Only looks within the same source unit.
        """
        if not self._tree:
            return None
        for node in ast.walk(self._tree):
            if isinstance(node, ast.Assign):
                if isinstance(node.value, ast.Call):
                    if _call_name(node.value) == func_name:
                        for tgt in node.targets:
                            if isinstance(tgt, ast.Name):
                                return tgt.id
        return None

    # ------------------------------------------------------------------
    # Internal: formatting helpers
    # ------------------------------------------------------------------

    def _format_edge(self, edge: FlowEdge) -> str:
        ev_label = f"[{', '.join(edge.evidence.basis)}]"
        kind_label = edge.kind.replace("_", " ")
        cross = " [cross-file]" if edge.is_cross_file else ""
        line_info = f" line {edge.line_number}" if edge.line_number else ""
        return (
            f"  {edge.producer} -> {edge.variable} -> {edge.consumer}"
            f" [{kind_label}{line_info}]{cross}\n"
            f"    {ev_label}: {edge.evidence.note}"
        )

    def _format_node(self, node: ValueNode) -> str:
        ev_label = f"[{', '.join(node.evidence.basis)}]"
        parts = [f"  variable: {node.name}"]
        if node.annotation:
            parts.append(f"    annotation: {node.annotation}")
        if node.source_expr:
            parts.append(f"    source: {node.source_expr}")
        if node.source_contract:
            parts.append(f"    source_contract: {node.source_contract}")
        if node.consumer_expr:
            parts.append(f"    consumer: {node.consumer_expr}")
        if node.consumer_contract:
            parts.append(f"    consumer_contract: {node.consumer_contract}")
        parts.append(f"    {ev_label}: {node.evidence.note}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Convenience function for integration with semantic_facts.py
# ---------------------------------------------------------------------------

def extract_value_flow_for_function(
    function_code: str,
    file_path: str = "",
    repo_index: Any = None,
) -> str:
    """
    Extract value-flow facts from a function and return the formatted LLM text.

    Returns empty string if no facts are found or if parsing fails.
    """
    try:
        extractor = ValueFlowExtractor(function_code, file_path, repo_index=repo_index)
        graph = extractor.extract()
        return extractor.format_for_llm(graph)
    except Exception as exc:
        logger.debug("extract_value_flow_for_function failed for %s: %s", file_path, exc)
        return ""
