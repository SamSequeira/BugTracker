"""
PY_MUT_001 — Mutable default argument (Python)
-----------------------------------------------
Detects function/lambda definitions where a default parameter value is a
mutable object that is shared across every call to the function.

Detected patterns
-----------------
Literal forms (AST node type):
  []      → "list"
  {}      → "dictionary"
  {1, 2}  → "set"

Constructor-call forms (call node whose function name is in the set):
  list()       ← mutable, detectable
  dict()       ← mutable, detectable
  set()        ← mutable (tree-sitter emits this as a call node)
  bytearray()  ← mutable bytes buffer

Identifier forms (resolved to preceding mutable assignment in scope):
  GLOBAL_LIST = []; def f(x=GLOBAL_LIST)  ← resolved to mutable

NOT flagged (intentionally):
  frozenset()  — immutable
  tuple()      — immutable
  None         — canonical safe default
"""

from typing import Iterator, List, Optional, Dict

from ..base_rule import BaseRule
from ..models import CandidateIssue

# AST node types that are directly mutable literals
_MUTABLE_LITERAL_TYPES = {"list", "dictionary", "set"}

# Constructor call names that produce mutable objects
_MUTABLE_CALL_NAMES = {"set", "list", "dict", "bytearray"}


class PythonMutableDefaultArg(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_MUT_001"

    @property
    def issue_type(self) -> str:
        return "mutable_default_argument"

    @property
    def severity(self) -> str:
        return "medium"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        yield from self._analyze_scope(ast, {}, file_path, source_lines)

    def _analyze_scope(
        self,
        node: dict,
        outer_mutability: Dict[str, Optional[str]],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        """
        Analyze a lexical scope with its own forked mutability environment,
        ensuring local assignments inside inner functions do not bleed into
        outer or sibling scopes.
        """
        mutability = dict(outer_mutability)

        for child in node.get("children", []):
            ntype = child.get("type", "")

            # Track assignments: var = <value>
            if ntype == "assignment":
                children = child.get("children", [])
                if len(children) >= 3 and children[0].get("type") == "identifier":
                    var_name = (children[0].get("text") or "").strip()
                    rhs = children[-1]
                    rhs_type = rhs.get("type", "")

                    if rhs_type in _MUTABLE_LITERAL_TYPES:
                        mutability[var_name] = rhs_type
                    elif rhs_type == "call":
                        call_kids = rhs.get("children", [])
                        func_name = (call_kids[0].get("text") or "").strip() if call_kids else ""
                        if func_name in _MUTABLE_CALL_NAMES:
                            mutability[var_name] = func_name
                        else:
                            mutability[var_name] = None
                    elif rhs_type == "identifier":
                        rhs_id = (rhs.get("text") or "").strip()
                        mutability[var_name] = mutability.get(rhs_id)
                    else:
                        mutability[var_name] = None
                continue

            # Function / Lambda definition: check default parameters, then recurse into body
            if ntype in ("function_definition", "lambda"):
                params_node = next(
                    (c for c in child.get("children", []) if c.get("type") == "parameters"),
                    None,
                )
                if params_node:
                    for param in params_node.get("children", []):
                        if param.get("type") != "default_parameter":
                            continue

                        self.record_syntax_match()

                        param_children = param.get("children", [])
                        if len(param_children) < 3:
                            continue

                        param_name = (param_children[0].get("text") or "?").strip()
                        default_node = param_children[-1]
                        dtype = default_node.get("type", "")

                        # --- Direct mutable literal: [], {}, set-display ---
                        if dtype in _MUTABLE_LITERAL_TYPES:
                            yield self._make_issue(
                                node=param,  # Capture the full parameter e.g. globals={}
                                file_path=file_path,
                                source_lines=source_lines,
                                message=(
                                    f"Mutable default argument `{default_node.get('text') or '?'}` "
                                    f"for parameter `{param_name}`. Use `None` as default and initialize inside function."
                                ),
                                evidence={
                                    "parameter": param_name,
                                    "default_value": default_node.get("text") or "?",
                                    "mutable_type": dtype,
                                    "confidence": "high",
                                    "reason": f"Parameter `{param_name}` has direct mutable literal default `{default_node.get('text')}`.",
                                },
                                confidence="high",
                            )
                            continue

                        # --- Mutable constructor call: list(), dict(), set(), bytearray() ---
                        if dtype == "call":
                            call_children = default_node.get("children", [])
                            if call_children:
                                func_name = (call_children[0].get("text") or "").strip()
                                if func_name in _MUTABLE_CALL_NAMES:
                                    display = f"{func_name}()"
                                    yield self._make_issue(
                                        node=param,
                                        file_path=file_path,
                                        source_lines=source_lines,
                                        message=(
                                            f"Mutable default argument `{display}` "
                                            f"for parameter `{param_name}`. Use `None` as default and create new "
                                            f"{func_name} inside the function."
                                        ),
                                        evidence={
                                            "parameter": param_name,
                                            "default_value": display,
                                            "mutable_type": func_name,
                                            "confidence": "high",
                                            "reason": f"Parameter `{param_name}` default calls mutable constructor `{display}`.",
                                        },
                                        confidence="high",
                                    )
                                    continue

                        # --- Resolved mutable identifier default: e.g. x=GLOBAL_LIST ---
                        if dtype == "identifier":
                            ident_name = (default_node.get("text") or "").strip()
                            resolved_mut = mutability.get(ident_name)
                            if resolved_mut:
                                yield self._make_issue(
                                    node=param,
                                    file_path=file_path,
                                    source_lines=source_lines,
                                    message=(
                                        f"Mutable default argument `{ident_name}` (resolved to mutable "
                                        f"{resolved_mut}) for parameter `{param_name}`."
                                    ),
                                    evidence={
                                        "parameter": param_name,
                                        "default_value": ident_name,
                                        "mutable_type": resolved_mut,
                                        "confidence": "medium",
                                        "reason": f"Identifier `{ident_name}` was previously initialized to mutable `{resolved_mut}` in scope.",
                                    },
                                    confidence="medium",
                                )
                                continue

                # Recurse into function body with a child scope
                body_node = next((c for c in child.get("children", []) if c.get("type") == "block"), child)
                yield from self._analyze_scope(body_node, mutability, file_path, source_lines)
                continue

            # Class or other block: recurse into children
            if ntype in ("class_definition", "block", "if_statement", "for_statement", "while_statement", "try_statement"):
                yield from self._analyze_scope(child, mutability, file_path, source_lines)
                continue
