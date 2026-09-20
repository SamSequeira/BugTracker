"""
PY_EXC_001 — Problematic / Swallowed Exception Handling (Python)
-----------------------------------------------------------------
Detects dangerous exception handling patterns that swallow or suppress errors:
1. Bare `except:` with no exception type specified (catches everything, including SystemExit).
2. `except BaseException:` catching the root of the hierarchy.
3. Completely swallowed exceptions (`except Exception: pass`, empty body, or only `...`)
   where no logging, re-raising, or recovery action is performed.

Legitimate patterns exempted:
- Specific exception handling: `except ValueError: ...`
- Logging handlers: `except Exception as e: logger.error(e)`
- Rethrowing handlers: `except Exception: raise`
- Handlers returning fallback data or calling recovery routines.
"""

from __future__ import annotations

import re
from typing import Iterator, List, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_BROAD_EXCEPTIONS: Set[str] = {"BaseException", "Exception"}

_LOGGING_RE = re.compile(
    r'\b(?:logger|logging|log|print|sys\.stderr|traceback)\.(?:error|exception|warning|critical|info|warn|print_exc|format_exc|write)\b|\bprint\s*\(',
    re.IGNORECASE,
)


def _extract_exception_names(type_node: dict) -> List[str]:
    """Extract exception type names from AST node (identifier, as_pattern, or tuple)."""
    ntype = type_node.get("type", "")

    if ntype == "identifier":
        return [(type_node.get("text") or "").strip()]

    if ntype == "as_pattern":
        children = type_node.get("children", [])
        non_kw = [c for c in children if c.get("text", "") != "as"]
        if non_kw:
            return _extract_exception_names(non_kw[0])
        return []

    if ntype == "tuple":
        names = []
        for child in type_node.get("children", []):
            if child.get("text", "") in ("(", ")", ","):
                continue
            names.extend(_extract_exception_names(child))
        return names

    if ntype == "parenthesized_expression":
        children = [c for c in type_node.get("children", []) if c.get("text", "") not in ("(", ")")]
        if children:
            return _extract_exception_names(children[0])
        return []

    text = (type_node.get("text") or "").strip()
    return [text] if text else []


def _is_empty_or_pass_only(body_node: dict) -> bool:
    """Check if the block body contains only pass, ..., or no statements."""
    children = body_node.get("children", [])
    stmts = [
        c for c in children
        if c.get("type") not in (":", "comment") and (c.get("text") or "").strip() not in (":", "")
    ]
    if not stmts:
        return True
    if len(stmts) == 1:
        stype = stmts[0].get("type", "")
        stext = (stmts[0].get("text") or "").strip()
        if stype == "pass_statement" or stext in ("pass", "...", "pass;"):
            return True
    return False


def _has_meaningful_handling(body_node: dict) -> bool:
    """Check if the body has logging, re-raising, returning, or active recovery logic."""
    body_text = body_node.get("text") or ""

    # Check re-raising
    for node in BaseRule._walk(None, body_node):
        if node.get("type") == "raise_statement":
            return True
        if node.get("type") == "return_statement":
            return True

    # Check logging / error printing
    if _LOGGING_RE.search(body_text):
        return True

    return False


class PythonBareExcept(BaseRule):

    LANGUAGES = ["Python"]

    @property
    def rule_id(self) -> str:
        return "PY_EXC_001"

    @property
    def issue_type(self) -> str:
        return "problematic_exception_handling"

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
            if node.get("type") != "except_clause":
                continue

            children = node.get("children", [])
            keyword_children = [c for c in children if c.get("text", "") == "except"]
            if not keyword_children:
                continue

            # Find exception type node and block body (in tree-sitter, block might be sibling or child)
            non_trivial = [
                c for c in children
                if c.get("type") not in ("except", ":", "block")
                and c.get("text", "") not in ("except", ":")
            ]

            block = next((c for c in children if c.get("type") == "block"), None)

            # 1. Bare `except:`
            if not non_trivial:
                self.record_syntax_match()
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message="Bare `except:` clause catches all exceptions including SystemExit and KeyboardInterrupt.",
                    evidence={
                        "pattern": "bare_except",
                        "reason": "catches_all_exceptions",
                        "confidence": "high",
                    },
                    confidence="high",
                )
                continue

            # 2. Typed except: inspect exception types
            type_node = non_trivial[0]
            exc_names = _extract_exception_names(type_node)

            is_base_exc = "BaseException" in exc_names
            is_broad_exc = bool(set(exc_names) & _BROAD_EXCEPTIONS)

            if is_base_exc:
                self.record_syntax_match()
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message="`except BaseException` catches system-exiting exceptions; use `except Exception:` instead.",
                    evidence={
                        "pattern": "base_exception",
                        "exception_types": exc_names,
                        "confidence": "high",
                    },
                    confidence="high",
                )
                continue

            # 3. Check if broad exception (Exception) is completely swallowed
            if is_broad_exc and block is not None:
                if _is_empty_or_pass_only(block):
                    self.record_syntax_match()
                    yield self._make_issue(
                        node=node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=f"`except {', '.join(exc_names)}:` silently swallows errors with an empty/pass handler.",
                        evidence={
                            "pattern": "swallowed_broad_exception",
                            "exception_types": exc_names,
                            "reason": "empty_or_pass_body",
                            "confidence": "high",
                        },
                        confidence="high",
                    )
                    continue

                # Broad exception with no logging, re-raising, or return
                if not _has_meaningful_handling(block):
                    self.record_syntax_match()
                    yield self._make_issue(
                        node=node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=f"`except {', '.join(exc_names)}:` catches broad exception without logging or re-raising.",
                        evidence={
                            "pattern": "unhandled_broad_exception",
                            "exception_types": exc_names,
                            "reason": "no_logging_or_reraise",
                            "confidence": "medium",
                        },
                        confidence="medium",
                    )
                    continue

            self.record_suppression("meaningful_exception_handling")
