"""
PY_MUT_001 — Mutable default argument (Python)
-----------------------------------------------
Detects function and lambda definitions where a default parameter value
is a mutable object (list, dictionary, set, bytearray) that is shared across calls.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from ..base_rule import BaseRule
from ..models import CandidateIssue

_MUTABLE_LITERAL_TYPES = {"list", "dictionary", "set"}
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
        mutability = dict(outer_mutability)

        for child in node.get("children", []):
            ntype = child.get("type", "")

            # Unwrap expression_statement for assignments
            actual_node = child
            if ntype == "expression_statement":
                inner_kids = child.get("children", [])
                if inner_kids and inner_kids[0].get("type") in ("assignment", "augmented_assignment"):
                    actual_node = inner_kids[0]
                    ntype = actual_node.get("type", "")

            # Track variable assignments in current scope
            if ntype == "assignment":
                children = actual_node.get("children", [])
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

            # Check function definitions and lambdas
            if ntype in ("function_definition", "async_function_definition", "lambda"):
                params = next((c for c in child.get("children", []) if c.get("type") in ("parameters", "lambda_parameters")), None)
                if params:
                    for p in params.get("children", []):
                        if p.get("type") in ("default_parameter", "typed_default_parameter"):
                            kids = p.get("children", [])
                            if len(kids) >= 3:
                                param_name = (kids[0].get("text") or "").strip()
                                default_val_node = kids[-1]
                                default_type = default_val_node.get("type", "")

                                is_mutable = False
                                reason = ""

                                if default_type in _MUTABLE_LITERAL_TYPES:
                                    is_mutable = True
                                    reason = f"literal {default_type}"
                                elif default_type == "call":
                                    call_kids = default_val_node.get("children", [])
                                    func_name = (call_kids[0].get("text") or "").strip() if call_kids else ""
                                    if func_name in _MUTABLE_CALL_NAMES:
                                        is_mutable = True
                                        reason = f"constructor `{func_name}()`"
                                elif default_type == "identifier":
                                    id_name = (default_val_node.get("text") or "").strip()
                                    if mutability.get(id_name):
                                        is_mutable = True
                                        reason = f"mutable variable `{id_name}`"

                                if is_mutable:
                                    self.record_syntax_match()
                                    yield self._make_issue(
                                        node=p,
                                        file_path=file_path,
                                        source_lines=source_lines,
                                        message=(
                                            f"Default parameter `{param_name}` uses a mutable {reason}. "
                                            f"Use `None` as default and initialize inside the function."
                                        ),
                                        evidence={
                                            "parameter": param_name,
                                            "mutable_reason": reason,
                                            "confidence": "high",
                                        },
                                        confidence="high",
                                    )

                # Recurse into nested scope
                yield from self._analyze_scope(child, mutability, file_path, source_lines)
            else:
                yield from self._analyze_scope(child, mutability, file_path, source_lines)
