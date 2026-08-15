"""
PY_EXC_001 — Bare except clause (Python)
-----------------------------------------
Detects `except:` with no exception type specified.
A bare except catches BaseException including KeyboardInterrupt and
SystemExit, which makes programs hard to kill and hides real errors.

AST pattern (Python):
  except_clause
    ├─ "except"
    └─ ":"        ← immediately after "except", no type node
"""

from typing import Iterator, List

from ..base_rule import BaseRule
from ..models import CandidateIssue


class PythonBareExcept(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_EXC_001"

    @property
    def issue_type(self) -> str:
        return "bare_except"

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
            if node["type"] != "except_clause":
                continue

            children = node.get("children", [])
            # A bare `except:` clause has: "except", ":", "block"
            # A typed clause has: "except", <ExceptionType>, ":", "block"
            # Bare = no children other than "except", ":", and "block"
            non_trivial = [
                c for c in children
                if c["type"] not in ("except", ":", "block")
            ]
            if non_trivial:
                continue

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    "Bare `except:` clause catches all exceptions including "
                    "KeyboardInterrupt and SystemExit.  Specify the exception "
                    "type(s) you expect, e.g. `except ValueError:`."
                ),
                evidence={"clause_text": node.get("text", "except:")},
            )
