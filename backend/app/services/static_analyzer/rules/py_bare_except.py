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
"""
PY_EXC_001 — Bare or over-broad except clause (Python)
-------------------------------------------------------
Detects three patterns:

1. `except:` — a completely bare clause with no exception type.
   This catches *everything* including KeyboardInterrupt and SystemExit,
   making programs impossible to kill and hiding real errors.

2. `except BaseException:` — technically typed, but semantically identical
   to bare `except` because BaseException is the root of the entire hierarchy.
   Using it is almost always a mistake in production code.

3. `except (IOError, BaseException):` — BaseException inside a tuple  (W09)
   The tuple makes the except over-broad even though other types are listed.

4. `except BaseException as e:` — aliased BaseException  (W10)
   The `as` binding does not change the catch scope.

AST pattern (Python, tree-sitter):
  except_clause
    ├─ "except"
    ├─ (optional) <ExceptionType>   ← absent ⇒ bare
    │     ExceptionType may be:
    │       identifier              → direct name
    │       as_pattern              → Name as alias
    │       tuple                   → (Name1, Name2, ...)
    └─ ":"

Root-cause notes
----------------
* F-01: Empty except_clause (zero children) was a false positive.
        Fix: require the "except" keyword child.
* F-24: except BaseException: was a false negative.
        Fix: check identifier text == "BaseException".
* W09:  except (IOError, BaseException): was a false negative.
        Root cause: the rule checked the tuple node's text directly
        ("(IOError, BaseException)") instead of recursing into children.
        Fix: _extract_exception_names() recurses into tuple children.
* W10:  except BaseException as e: was a false negative.
        Root cause: the rule checked as_pattern text ("BaseException as e")
        instead of the first child (the actual exception type).
        Fix: _extract_exception_names() unwraps as_pattern to its first child.
"""

from typing import Iterator, List, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

# Exception type names that are semantically equivalent to a bare except.
_OVER_BROAD_EXCEPTIONS: Set[str] = {"BaseException"}


def _extract_exception_names(type_node: dict) -> List[str]:
    """
    Extract the bare exception type name(s) from an exception-type AST node.

    Handles:
      identifier            → ["ValueError"]
      as_pattern            → name of the first child, e.g. "BaseException as e" → ["BaseException"]
      tuple                 → recurse into each child, e.g. "(IOError, BaseException)" → ["IOError", "BaseException"]

    Returns a flat list of string names.  Unknown node shapes return [].
    """
    ntype = type_node["type"]

    # Direct identifier: except ValueError:
    if ntype == "identifier":
        return [type_node.get("text", "").strip()]

    # Aliased: except BaseException as e:
    # as_pattern children: [exception_type, "as", identifier]
    if ntype == "as_pattern":
        children = type_node.get("children", [])
        non_kw = [c for c in children if c.get("text", "") != "as"]
        if non_kw:
            return _extract_exception_names(non_kw[0])
        return []

    # Tuple: except (IOError, BaseException):
    if ntype == "tuple":
        names: List[str] = []
        for child in type_node.get("children", []):
            # Skip punctuation: (, ), ,
            if child.get("text", "") in ("(", ")", ",") or child["type"] in ("(", ")", ","):
                continue
            names.extend(_extract_exception_names(child))
        return names

    # Parenthesized expression wrapping a tuple or identifier
    if ntype == "parenthesized_expression":
        children = type_node.get("children", [])
        inner = [c for c in children if c.get("text", "") not in ("(", ")")]
        if inner:
            return _extract_exception_names(inner[0])
        return []

    # Any other node: return its text as a best-effort guess
    text = type_node.get("text", "").strip()
    return [text] if text else []


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

            # Guard: must have at least the "except" keyword child.
            # A node with zero children is a parser artifact — do not flag it.
            keyword_children = [c for c in children if c.get("text", "") == "except"]
            if not keyword_children:
                continue

            # Collect non-trivial children (everything except keywords, ":", and blocks)
            non_trivial = [
                c for c in children
                if c["type"] not in ("except", ":", "block")
                and c.get("text", "") not in ("except", ":")
            ]

            if not non_trivial:
                # Bare `except:`
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=(
                        "Bare `except:` clause catches all exceptions including "
                        "KeyboardInterrupt and SystemExit.  Specify the exception "
                        "type(s) you expect, e.g. `except ValueError:`."
                    ),
                    evidence={"clause_text": node.get("text", "except:"),
                              "kind": "bare"},
                )
                continue

            # Typed except — extract all exception names from possibly nested
            # structures (tuples, as-patterns) and check for over-broad types.
            for type_node in non_trivial:
                names = _extract_exception_names(type_node)
                over_broad = [n for n in names if n in _OVER_BROAD_EXCEPTIONS]
                if over_broad:
                    name = over_broad[0]
                    yield self._make_issue(
                        node=node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=(
                            f"`except` clause catches `{name}`, which covers every "
                            "exception including KeyboardInterrupt and SystemExit — "
                            "effectively the same as a bare `except:`.  "
                            "Specify a narrower exception type."
                        ),
                        evidence={
                            "clause_text": node.get("text", "except ..."),
                            "kind": "over_broad",
                            "exception_type": name,
                        },
                    )
                    break  # one issue per clause is enough

"""
PY_EXC_001 — Bare or over-broad except clause (Python)
-------------------------------------------------------
Detects three patterns:

1. `except:` — a completely bare clause with no exception type.
   This catches *everything* including KeyboardInterrupt and SystemExit,
   making programs impossible to kill and hiding real errors.

2. `except BaseException:` — technically typed, but semantically identical
   to bare `except` because BaseException is the root of the entire hierarchy.
   Using it is almost always a mistake in production code.

3. `except (IOError, BaseException):` — BaseException inside a tuple  (W09)
   The tuple makes the except over-broad even though other types are listed.

4. `except BaseException as e:` — aliased BaseException  (W10)
   The `as` binding does not change the catch scope.

AST pattern (Python, tree-sitter):
  except_clause
    ├─ "except"
    ├─ (optional) <ExceptionType>   ← absent ⇒ bare
    │     ExceptionType may be:
    │       identifier              → direct name
    │       as_pattern              → Name as alias
    │       tuple                   → (Name1, Name2, ...)
    └─ ":"

Root-cause notes
----------------
* F-01: Empty except_clause (zero children) was a false positive.
        Fix: require the "except" keyword child.
* F-24: except BaseException: was a false negative.
        Fix: check identifier text == "BaseException".
* W09:  except (IOError, BaseException): was a false negative.
        Root cause: the rule checked the tuple node's text directly
        ("(IOError, BaseException)") instead of recursing into children.
        Fix: _extract_exception_names() recurses into tuple children.
* W10:  except BaseException as e: was a false negative.
        Root cause: the rule checked as_pattern text ("BaseException as e")
        instead of the first child (the actual exception type).
        Fix: _extract_exception_names() unwraps as_pattern to its first child.
"""

from typing import Iterator, List, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

# Exception type names that are semantically equivalent to a bare except.
_OVER_BROAD_EXCEPTIONS: Set[str] = {"BaseException"}


def _extract_exception_names(type_node: dict) -> List[str]:
    """
    Extract the bare exception type name(s) from an exception-type AST node.

    Handles:
      identifier            → ["ValueError"]
      as_pattern            → name of the first child, e.g. "BaseException as e" → ["BaseException"]
      tuple                 → recurse into each child, e.g. "(IOError, BaseException)" → ["IOError", "BaseException"]

    Returns a flat list of string names.  Unknown node shapes return [].
    """
    ntype = type_node["type"]

    # Direct identifier: except ValueError:
    if ntype == "identifier":
        return [type_node.get("text", "").strip()]

    # Aliased: except BaseException as e:
    # as_pattern children: [exception_type, "as", identifier]
    if ntype == "as_pattern":
        children = type_node.get("children", [])
        non_kw = [c for c in children if c.get("text", "") != "as"]
        if non_kw:
            return _extract_exception_names(non_kw[0])
        return []

    # Tuple: except (IOError, BaseException):
    if ntype == "tuple":
        names: List[str] = []
        for child in type_node.get("children", []):
            # Skip punctuation: (, ), ,
            if child.get("text", "") in ("(", ")", ",") or child["type"] in ("(", ")", ","):
                continue
            names.extend(_extract_exception_names(child))
        return names

    # Parenthesized expression wrapping a tuple or identifier
    if ntype == "parenthesized_expression":
        children = type_node.get("children", [])
        inner = [c for c in children if c.get("text", "") not in ("(", ")")]
        if inner:
            return _extract_exception_names(inner[0])
        return []

    # Any other node: return its text as a best-effort guess
    text = type_node.get("text", "").strip()
    return [text] if text else []


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

        is_test = self._is_test_file(file_path)

        for node in self._walk(ast):
            if node.get("type") != "except_clause":
                continue

            children = node.get("children", [])

            # Guard: must have at least the "except" keyword child.
            keyword_children = [c for c in children if (c.get("text") or "").strip() == "except"]
            if not keyword_children:
                continue

            self.record_syntax_match()

            # Collect non-trivial children (everything except keywords, ":", and blocks)
            non_trivial = [
                c for c in children
                if c.get("type") not in ("except", ":", "block")
                and (c.get("text") or "").strip() not in ("except", ":")
            ]

            if not non_trivial:
                # Bare `except:`
                confidence = "low" if is_test else "high"
                yield self._make_issue(
                    node=node,
                    file_path=file_path,
                    source_lines=source_lines,
                    message=(
                        "Bare `except:` clause catches all exceptions including KeyboardInterrupt and "
                        "SystemExit. Specify the expected exception type(s) (e.g. `except ValueError:`)."
                    ),
                    evidence={
                        "clause_text": node.get("text", "except:").strip(),
                        "kind": "bare",
                        "confidence": confidence,
                        "reason": "Bare `except:` catches KeyboardInterrupt/SystemExit without restriction.",
                    },
                    confidence=confidence,
                )
                continue

            # Typed except — extract all exception names from possibly nested structures
            found_over_broad = False
            for type_node in non_trivial:
                names = _extract_exception_names(type_node)
                over_broad = [n for n in names if n in _OVER_BROAD_EXCEPTIONS]
                if over_broad:
                    name = over_broad[0]
                    found_over_broad = True
                    confidence = "low" if is_test else "high"
                    yield self._make_issue(
                        node=node,
                        file_path=file_path,
                        source_lines=source_lines,
                        message=(
                            f"`except` clause catches `{name}`, which covers every exception including "
                            f"KeyboardInterrupt and SystemExit. Specify a narrower exception type."
                        ),
                        evidence={
                            "clause_text": node.get("text", "except ...").strip(),
                            "kind": "over_broad",
                            "exception_type": name,
                            "confidence": confidence,
                            "reason": f"`except {name}` catches root base exceptions.",
                        },
                        confidence=confidence,
                    )
                    break

            if not found_over_broad:
                self.record_suppression("specifically_typed_exception_clause")

