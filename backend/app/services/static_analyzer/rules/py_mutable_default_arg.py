"""
PY_MUT_001 — Mutable default argument (Python)
-----------------------------------------------
Detects function definitions where a default parameter value is a
list literal `[]`, dict literal `{}`, or set literal `set()`.
Mutable defaults are shared across all calls to the function —
a classic Python footgun.

AST pattern (Python):
  function_definition
    └─ parameters
         └─ default_parameter
              └─ <default_value>  ← flagged when list/dict/set
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue

_MUTABLE_TYPES = {"list", "dictionary", "set"}


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

        for node in self._walk(ast):
            if node["type"] not in ("function_definition", "lambda"):
                continue

            params_node = next(
                (c for c in node.get("children", []) if c["type"] == "parameters"),
                None,
            )
            if params_node is None:
                continue

            for param in params_node.get("children", []):
                if param["type"] != "default_parameter":
                    continue

                # default_parameter children: identifier, "=", <default_value>
                default_nodes = [
                    c for c in param.get("children", [])
                    if c["type"] not in ("identifier", "=")
                ]
                if not default_nodes:
                    continue

                default_node = default_nodes[0]

                # Direct mutable literal
                if default_node["type"] in _MUTABLE_TYPES:
                    param_name = param.get("children", [{}])[0].get("text", "?")
                    yield self._make_issue(
                        node=default_node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=(
                            f"Mutable default argument `{default_node.get('text', '?')}` "
                            f"for parameter `{param_name}`.  "
                            f"Use `None` as default and create a new object inside the function."
                        ),
                        evidence={
                            "parameter": param_name,
                            "default_value": default_node.get("text", "?"),
                            "mutable_type": default_node["type"],
                        },
                    )

                # set() call (tree-sitter represents set literals as calls to 'set')
                elif default_node["type"] == "call":
                    call_children = default_node.get("children", [])
                    if call_children and call_children[0].get("text", "") == "set":
                        param_name = param.get("children", [{}])[0].get("text", "?")
                        yield self._make_issue(
                            node=default_node,
                            file_path=file_path,
                            source_lines=source_lines,
                            message=(
                                f"Mutable default argument `set()` for parameter `{param_name}`.  "
                                f"Use `None` as default and create a new set inside the function."
                            ),
                            evidence={
                                "parameter": param_name,
                                "default_value": "set()",
                                "mutable_type": "set",
                            },
                        )
