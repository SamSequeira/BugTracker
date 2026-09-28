"""
Bounded, evidence-first semantic review helpers.

Pipeline responsibilities:

1. Discover executable Python source files.
2. Extract functions and methods using Python AST.
3. Build bounded single-file context.
4. Construct a strong semantic-review prompt.
5. Parse the LLM response.
6. Validate the finding against the actual source.

Design goals:
- Focus on REAL semantic bugs.
- Focus on SINGLE-FILE bugs for this phase.
- Keep repository code local.
- Keep prompts bounded for local models such as Qwen.
- Prefer correctness over generating large numbers of findings.
- Do not rely on rule-based detection for semantic decisions.
- Do not reject legitimate findings because of weak textual heuristics.
"""

from __future__ import annotations

import ast
import json
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


# =============================================================================
# Repository selection configuration
# =============================================================================

APPLICATION_HINTS = frozenset(
    {
        "service",
        "services",
        "core",
        "logic",
        "domain",
        "business",
        "usecase",
        "usecases",
        "use_case",
        "use_cases",
        "controller",
        "controllers",
        "handler",
        "handlers",
        "api",
        "routes",
        "views",
        "repository",
        "repositories",
        "manager",
        "managers",
        "processor",
        "processors",
        "worker",
        "workers",
        "module",
        "modules",
    }
)


EXCLUDED_PARTS = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "env",
        "__pycache__",
        "dist",
        "build",
        "coverage",
        "vendor",
        "migrations",
        "alembic",
        "docs",
        "site-packages",
        ".pytest_cache",
    }
)


SOURCE_SUFFIXES = {
    ".py": "python",
}


# =============================================================================
# Configuration
# =============================================================================

@dataclass(frozen=True)
class SemanticReviewConfig:
    """
    Bounds for the semantic review pipeline.

    These values are intentionally moderate for local LLM usage.

    max_files:
        Maximum number of source files selected.

    max_source_chars:
        Maximum total source characters selected.

    max_functions:
        Maximum number of functions reviewed.

    max_context_chars:
        Maximum context supplied to the LLM for one function.

    max_context_depth:
        0 = target only
        1 = target + direct local callees.

    min_confidence:
        Minimum confidence accepted by validation.
    """

    max_files: int = int(
        os.getenv(
            "SEMANTIC_MAX_FILES",
            "20",
        )
    )

    max_source_chars: int = int(
        os.getenv(
            "SEMANTIC_MAX_SOURCE_CHARS",
            "500000",
        )
    )

    max_functions: int = int(
        os.getenv(
            "SEMANTIC_MAX_FUNCTIONS",
            "50",
        )
    )

    max_context_chars: int = int(
        os.getenv(
            "SEMANTIC_MAX_CONTEXT_CHARS",
            "12000",
        )
    )

    max_context_depth: int = int(
        os.getenv(
            "SEMANTIC_MAX_CONTEXT_DEPTH",
            "1",
        )
    )

    min_confidence: float = float(
        os.getenv(
            "SEMANTIC_MIN_CONFIDENCE",
            "0.70",
        )
    )


# =============================================================================
# Data structures
# =============================================================================

@dataclass(frozen=True)
class SelectedFile:
    path: Path
    relative_path: str
    language: str
    source_chars: int
    selection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class ExtractedFunction:
    file_path: str
    language: str
    name: str
    class_name: str | None
    qualified_name: str
    start_line: int
    end_line: int
    source: str
    parameters: tuple[str, ...]
    is_async: bool
    decorators: tuple[str, ...]
    called_names: tuple[str, ...]
    imports: tuple[str, ...]
    class_source: str | None = None
    # (kind, name, source) for module-level variables/classes this function
    # references, e.g. ("variable", "summary_cache", "summary_cache = {}").
    module_definitions: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class ContextPackage:
    text: str
    included: tuple[str, ...]
    truncated: bool


# =============================================================================
# Component 1 — Source file discovery
# =============================================================================

def discover_source_files(
    root: str | Path,
    config: SemanticReviewConfig | None = None,
) -> list[SelectedFile]:
    """
    Deterministically select bounded executable Python source.

    The selector avoids:
    - tests
    - migrations
    - virtual environments
    - generated/build directories
    - documentation
    - dependencies

    Application-oriented directories receive priority, but executable
    Python files from unfamiliar layouts are still considered.
    """

    config = config or SemanticReviewConfig()

    root_path = Path(root).resolve()

    if not root_path.exists() or not root_path.is_dir():
        return []

    candidates: list[SelectedFile] = []

    for path in sorted(
        root_path.rglob("*"),
        key=lambda item: item.as_posix().lower(),
    ):
        if not path.is_file():
            continue

        suffix = path.suffix.lower()

        if suffix not in SOURCE_SUFFIXES:
            continue

        relative = path.relative_to(root_path)

        parts = {
            part.lower()
            for part in relative.parts
        }

        lower_name = path.name.lower()

        # -------------------------------------------------------------
        # Excluded directories
        # -------------------------------------------------------------

        if parts & EXCLUDED_PARTS:
            continue

        # -------------------------------------------------------------
        # Test files
        # -------------------------------------------------------------

        if lower_name.startswith("test_"):
            continue

        if lower_name.endswith("_test.py"):
            continue

        # -------------------------------------------------------------
        # File size
        # -------------------------------------------------------------

        try:
            file_size = path.stat().st_size
        except OSError:
            continue

        if file_size == 0:
            continue

        if file_size > config.max_source_chars:
            continue

        # -------------------------------------------------------------
        # Read source
        # -------------------------------------------------------------

        try:
            source = path.read_text(
                encoding="utf-8",
                errors="strict",
            )
        except (
            OSError,
            UnicodeError,
        ):
            continue

        # -------------------------------------------------------------
        # Syntax validation
        # -------------------------------------------------------------

        try:
            tree = ast.parse(
                source,
                filename=str(path),
            )
        except SyntaxError:
            continue

        reasons: list[str] = []

        # -------------------------------------------------------------
        # Application directory signal
        # -------------------------------------------------------------

        if parts & APPLICATION_HINTS:
            reasons.append(
                "application-directory hint"
            )

        # -------------------------------------------------------------
        # Application entry points
        # -------------------------------------------------------------

        if path.stem.lower() in {
            "main",
            "app",
            "server",
            "manage",
            "wsgi",
            "asgi",
        }:
            reasons.append(
                "application-entry hint"
            )

        # -------------------------------------------------------------
        # Executable definitions
        # -------------------------------------------------------------

        if any(
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            )
            for node in ast.walk(tree)
        ):
            reasons.append(
                "executable definitions"
            )

        if not reasons:
            continue

        candidates.append(
            SelectedFile(
                path=path,
                relative_path=relative.as_posix(),
                language=SOURCE_SUFFIXES[suffix],
                source_chars=len(source),
                selection_reasons=tuple(reasons),
            )
        )

    # -------------------------------------------------------------
    # Deterministic ordering
    # -------------------------------------------------------------

    candidates.sort(
        key=lambda item: (
            "application-directory hint"
            not in item.selection_reasons,
            item.relative_path.lower(),
        )
    )

    selected: list[SelectedFile] = []

    total_chars = 0

    for candidate in candidates:

        if len(selected) >= config.max_files:
            break

        if (
            total_chars + candidate.source_chars
            > config.max_source_chars
        ):
            break

        selected.append(candidate)

        total_chars += candidate.source_chars

    return selected


# =============================================================================
# AST helpers
# =============================================================================

def _node_source(
    lines: list[str],
    node: ast.AST,
) -> str:
    """
    Return exact source represented by an AST node.
    """

    start = getattr(
        node,
        "lineno",
        None,
    )

    end = getattr(
        node,
        "end_lineno",
        None,
    )

    if start is None or end is None:
        return ""

    return "\n".join(
        lines[start - 1 : end]
    )


def _calls(
    node: ast.AST,
) -> tuple[str, ...]:
    """
    Extract syntactic function/method call names.

    This does not attempt full symbol resolution.
    """

    names: set[str] = set()

    for item in ast.walk(node):

        if not isinstance(
            item,
            ast.Call,
        ):
            continue

        if isinstance(
            item.func,
            ast.Name,
        ):
            names.add(
                item.func.id
            )

        elif isinstance(
            item.func,
            ast.Attribute,
        ):
            names.add(
                item.func.attr
            )

    return tuple(
        sorted(names)
    )


def _iter_nested_bodies(
    node: ast.AST,
) -> Iterable[list[ast.stmt]]:
    """
    Yield nested statement bodies that may contain functions.

    Ownership is kept explicit instead of recursively walking arbitrary AST
    nodes.
    """

    for child in ast.iter_child_nodes(node):

        if not isinstance(
            child,
            ast.stmt,
        ):
            continue

        body = getattr(
            child,
            "body",
            None,
        )

        if isinstance(
            body,
            list,
        ):
            yield body

        for attribute in (
            "orelse",
            "finalbody",
            "handlers",
            "cases",
        ):
            value = getattr(
                child,
                attribute,
                None,
            )

            if not value:
                continue

            if not isinstance(
                value,
                list,
            ):
                continue

            for item in value:

                if isinstance(
                    item,
                    ast.ExceptHandler,
                ):
                    handler_body = getattr(
                        item,
                        "body",
                        None,
                    )

                    if isinstance(
                        handler_body,
                        list,
                    ):
                        yield handler_body

                elif isinstance(
                    item,
                    ast.match_case,
                ):
                    case_body = getattr(
                        item,
                        "body",
                        None,
                    )

                    if isinstance(
                        case_body,
                        list,
                    ):
                        yield case_body


# =============================================================================
# Component 2 — Function extraction
# =============================================================================

def _target_names(target: ast.AST) -> list[str]:
    """Names bound by an assignment target (handles a, b = ...)."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_target_names(element))
        return names
    return []


def _module_level_definitions(
    tree: ast.Module,
    lines: list[str],
) -> list[tuple[str, str, str]]:
    """
    Module-level variables and classes, in file order, as (kind, name, source).

    Functions are excluded on purpose: called functions are added by the
    direct-callee mechanism in build_context().
    """
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            if node.name not in seen:
                seen.add(node.name)
                found.append(("class", node.name, _node_source(lines, node)))
            continue

        names: list[str] = []
        if isinstance(node, ast.Assign):
            for target in node.targets:
                names.extend(_target_names(target))
        elif isinstance(node, ast.AnnAssign):
            names.extend(_target_names(node.target))

        for name in names:
            if name in seen or name == "__all__":
                continue
            seen.add(name)
            found.append(("variable", name, _node_source(lines, node)))

    return found


def _referenced_module_names(node: ast.AST) -> set[str]:
    """
    Names a function reads from module scope.

    A name that is only assigned inside the function is a local variable,
    unless the function declares it `global`.
    """
    loaded: set[str] = set()
    stored: set[str] = set()
    declared_global: set[str] = set()

    for item in ast.walk(node):
        if isinstance(item, ast.Name):
            if isinstance(item.ctx, ast.Load):
                loaded.add(item.id)
            else:
                stored.add(item.id)
        elif isinstance(item, ast.Global):
            declared_global.update(item.names)

    return (loaded - (stored - declared_global)) | (stored & declared_global)


def extract_functions(
    selected_file: SelectedFile,
) -> list[ExtractedFunction]:
    """
    Extract:

    - module-level functions
    - async functions
    - class methods
    - nested functions

    No semantic filtering is performed here.
    """

    source = selected_file.path.read_text(
        encoding="utf-8"
    )

    lines = source.splitlines()

    tree = ast.parse(
        source,
        filename=str(
            selected_file.path
        ),
    )

    imports = tuple(
        ast.unparse(node)
        for node in tree.body
        if isinstance(
            node,
            (
                ast.Import,
                ast.ImportFrom,
            ),
        )
    )

    module_defs = _module_level_definitions(tree, lines)

    results: list[ExtractedFunction] = []

    def visit(
        body: Iterable[ast.stmt],
        class_name: str | None = None,
        class_source: str | None = None,
    ) -> None:

        for node in body:

            # ---------------------------------------------------------
            # Class
            # ---------------------------------------------------------

            if isinstance(
                node,
                ast.ClassDef,
            ):
                visit(
                    node.body,
                    class_name=node.name,
                    class_source=_node_source(
                        lines,
                        node,
                    ),
                )
                continue

            # ---------------------------------------------------------
            # Function / async function
            # ---------------------------------------------------------

            if isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):

                decorators = tuple(
                    ast.unparse(
                        decorator
                    )
                    for decorator in node.decorator_list
                )

                positional_args = (
                    list(
                        node.args.posonlyargs
                    )
                    + list(
                        node.args.args
                    )
                )

                params = tuple(
                    argument.arg
                    for argument in positional_args
                )

                params += tuple(
                    argument.arg
                    for argument in node.args.kwonlyargs
                )

                if node.args.vararg:
                    params += (
                        "*" + node.args.vararg.arg,
                    )

                if node.args.kwarg:
                    params += (
                        "**" + node.args.kwarg.arg,
                    )

                qualified_name = (
                    f"{class_name}.{node.name}"
                    if class_name
                    else node.name
                )

                referenced_names = (
                    _referenced_module_names(node)
                    - set(params)
                )

                results.append(
                    ExtractedFunction(
                        file_path=selected_file.relative_path,
                        language=selected_file.language,
                        name=node.name,
                        class_name=class_name,
                        qualified_name=qualified_name,
                        start_line=node.lineno,
                        end_line=node.end_lineno,
                        source=_node_source(
                            lines,
                            node,
                        ),
                        parameters=params,
                        is_async=isinstance(
                            node,
                            ast.AsyncFunctionDef,
                        ),
                        decorators=decorators,
                        called_names=_calls(node),
                        imports=imports,
                        class_source=class_source,
                        module_definitions=tuple(
                            (kind, def_name, def_source)
                            for kind, def_name, def_source in module_defs
                            if def_name in referenced_names
                            and not (
                                kind == "class"
                                and def_name == class_name
                            )
                        ),
                    )
                )

                # -----------------------------------------------------
                # Nested functions
                # -----------------------------------------------------

                visit(
                    node.body,
                    class_name=class_name,
                    class_source=class_source,
                )

                continue

            # ---------------------------------------------------------
            # Functions nested inside control flow
            # ---------------------------------------------------------

            if isinstance(
                node,
                (
                    ast.If,
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                    ast.Try,
                    ast.With,
                    ast.AsyncWith,
                ),
            ):

                for nested_body in _iter_nested_bodies(
                    node
                ):
                    visit(
                        nested_body,
                        class_name=class_name,
                        class_source=class_source,
                    )

    visit(tree.body)

    results.sort(
        key=lambda function: (
            function.file_path.lower(),
            function.start_line,
            function.qualified_name.lower(),
        )
    )

    return results


# =============================================================================
# Component 3 — Context construction
# =============================================================================

def build_context(
    target: ExtractedFunction,
    all_functions: Iterable[ExtractedFunction],
    config: SemanticReviewConfig | None = None,
) -> ContextPackage:
    """
    Build bounded local context.

    Priority:

        1. target function
        2. imports
        3. containing class
        4. direct local callees

    The target function is always preserved completely.

    Cross-file dependencies are intentionally excluded.
    """

    config = config or SemanticReviewConfig()

    target_header = (
        f"TARGET FUNCTION "
        f"{target.qualified_name} "
        f"({target.file_path}:"
        f"{target.start_line}-"
        f"{target.end_line})"
    )

    sections = [
        target_header
        + "\n"
        + target.source
    ]

    included = [
        "target_function"
    ]

    used = len(
        sections[0]
    )

    # -----------------------------------------------------------------
    # Module-level definitions used by the target (globals, caches,
    # constants, model classes defined in the same file)
    # -----------------------------------------------------------------

    skipped_module_definition = False

    for kind, def_name, def_source in target.module_definitions:

        block = (
            f"MODULE-LEVEL {kind.upper()} USED BY TARGET: {def_name}\n"
            + def_source
        )

        if (
            used
            + len(block)
            + 2
            <= config.max_context_chars
        ):
            sections.append(block)

            included.append(
                "module_def:"
                + def_name
            )

            used += (
                len(block)
                + 2
            )
        else:
            skipped_module_definition = True

    # -----------------------------------------------------------------
    # Imports
    # -----------------------------------------------------------------

    if target.imports:

        imports_text = "\n".join(
            target.imports
        )

        block = (
            "RELEVANT IMPORTS\n"
            + imports_text
        )

        if (
            used
            + len(block)
            + 2
            <= config.max_context_chars
        ):
            sections.append(block)

            included.append(
                "imports"
            )

            used += (
                len(block)
                + 2
            )

    # -----------------------------------------------------------------
    # Containing class
    # -----------------------------------------------------------------

    if target.class_source:

        block = (
            "CONTAINING CLASS\n"
            + target.class_source
        )

        if (
            used
            + len(block)
            + 2
            <= config.max_context_chars
        ):
            sections.append(block)

            included.append(
                "containing_class"
            )

            used += (
                len(block)
                + 2
            )

    # -----------------------------------------------------------------
    # Direct local callees
    # -----------------------------------------------------------------

    if config.max_context_depth >= 1:

        local_functions = {
            function.name: function
            for function in all_functions
            if (
                function.file_path
                == target.file_path
                and function.qualified_name
                != target.qualified_name
            )
        }

        added_callees: set[str] = set()

        for called_name in target.called_names:

            dependency = local_functions.get(
                called_name
            )

            if dependency is None:
                continue

            if (
                dependency.qualified_name
                in added_callees
            ):
                continue

            block = (
                f"DIRECT LOCAL CALLEE "
                f"{dependency.qualified_name} "
                f"({dependency.start_line}-"
                f"{dependency.end_line})\n"
                f"{dependency.source}"
            )

            if (
                used
                + len(block)
                + 2
                > config.max_context_chars
            ):
                return ContextPackage(
                    text="\n\n".join(
                        sections
                    ),
                    included=tuple(
                        included
                    ),
                    truncated=True,
                )

            sections.append(block)

            included.append(
                "direct_callee:"
                + dependency.qualified_name
            )

            added_callees.add(
                dependency.qualified_name
            )

            used += (
                len(block)
                + 2
            )

    return ContextPackage(
        text="\n\n".join(
            sections
        ),
        included=tuple(
            included
        ),
        truncated=skipped_module_definition,
    )


# =============================================================================
# Component 5 — LLM semantic detection prompt
# =============================================================================

def _build_compact_prompt(
    target: ExtractedFunction,
    context: ContextPackage,
) -> str:
    """
    Short prompt for small local models (SEMANTIC_PROMPT_MODE=compact).

    Design for a 3B model:
    - code first, short instructions, no long essay
    - target lines are numbered so start_line/end_line can be exact
    - the model first writes a short trace ("reasoning") and only then decides
    - a concrete checklist of common bug patterns (generic, not app-specific)
    - explicit "not a bug" rules to reduce false alarms
    - relevant_code must be ONE line copied exactly, so Component 7 can match it
    Output keys are identical to the full prompt, so the parser and
    validate_finding() work unchanged.
    """

    numbered = "\n".join(
        f"{number}: {line}"
        for number, line in enumerate(
            target.source.splitlines(),
            start=target.start_line,
        )
    )

    index = context.text.find(target.source)

    if index >= 0:
        other = context.text[index + len(target.source):].strip()
    else:
        other = context.text

    decorators = (
        "\n".join("@" + d for d in target.decorators)
        if target.decorators
        else "(none)"
    )

    other_block = (
        f"""
CONTEXT FROM THE SAME FILE (read it to understand the target; never report a bug that is only in this context):
{other}
"""
        if other
        else ""
    )

    return f"""You are a careful Python code reviewer. Decide if ONE function contains a real bug.

FILE: {target.file_path}
FUNCTION: {target.qualified_name}  (lines {target.start_line}-{target.end_line})
DECORATORS:
{decorators}

TARGET FUNCTION (each line starts with its line number and a colon; the number is NOT part of the code):
{numbered}
{other_block}
HOW TO REVIEW
1. From the function name and code, say in one sentence what it should do.
2. Trace it with a normal input, then with an empty, zero or missing input.
3. Compare the code against these common bug patterns:
- a sign, operator or comparison that does the opposite of what the function's purpose needs (adds where it should subtract, > instead of <, and instead of or)
- steps in the wrong order (for example limiting, slicing or paginating BEFORE filtering)
- division, len(), [0] or max()/min() on a value that can be 0 or empty, with no guard
- a mutable default argument (=[] or ={{}}) that the function changes or returns
- a shared module-level dict/list/cache that is read or filled here but never cleared or refreshed when the data changes
- a bare "except:" or an except block that hides the error and carries on as if it worked
- the wrong variable used or returned, a missing await, a resource not closed
4. Report a bug ONLY if you can point to one exact line of the TARGET FUNCTION and give a concrete input for which the result is wrong.

NOT A BUG (answer bug_found=false):
- code that already guards the case (an if/else, "or", max(1, x), a try/except that handles the error properly)
- style, naming, missing docs, missing features, missing tests, performance
- anything you cannot see in the code above; never invent fields, functions or behaviour
- normal framework code (dependency injection, generators that yield and then close, routers, app setup)

Reply with ONE JSON object and nothing else (no markdown, no code fences).
Use exactly these keys, in this order:
"reasoning": 2-3 short sentences: what the function should do, what the code does for a normal and for an empty/zero input, and your verdict. Write this first.
"bug_found": true or false
"bug_type": short category, or "" if no bug
"title": short title, or "" if no bug
"description": what is wrong, or "" if no bug
"file": "{target.file_path}"
"start_line": the line number shown before the first buggy line, or 0 if no bug
"end_line": the line number shown before the last buggy line, or 0 if no bug
"evidence": the ONE buggy line copied exactly from the code, without its line number, or "" if no bug
"expected_behavior": what should happen, or "" if no bug
"actual_behavior": what happens instead, or "" if no bug
"confidence": number from 0.0 to 1.0, or 0 if no bug
"relevant_code": the same ONE buggy line copied exactly, without its line number, or "" if no bug
""".strip()


def build_detection_prompt(
    target: ExtractedFunction,
    context: ContextPackage,
) -> str:
    """
    Build a strong semantic-review prompt for the local LLM.

    The prompt is optimized for a smaller coding model such as Qwen.

    Important strategy:

    The model is not asked to simply "look for bugs".

    Instead it is instructed to:
        1. understand the function's behavior,
        2. trace important values,
        3. inspect conditions,
        4. inspect calculations,
        5. inspect mutations,
        6. inspect returns,
        7. identify concrete contradictions,
        8. then decide whether a bug exists.

    This reduces the tendency of smaller models to immediately answer
    bug_found=false without actually reasoning through the code.
    """

    if os.getenv("SEMANTIC_PROMPT_MODE", "compact").strip().lower() == "compact":
        return _build_compact_prompt(target, context)

    return f"""
You are a precise semantic bug detector for Python source code.

Your job is to find REAL bugs in the TARGET FUNCTION.

The code has already passed deterministic/static analysis.
Your purpose is to detect semantic or behavioral defects that ordinary
AST/rule checks may miss.

You are NOT a style checker.

You are NOT a code-quality advisor.

You are NOT a requirements generator.

You are NOT allowed to invent application behavior that is not supported
by the supplied code.

============================================================
PRIMARY OBJECTIVE
============================================================

Determine whether the TARGET FUNCTION contains at least one concrete
behavioral defect.

A bug means:

    There exists a realistic input or execution path supported by the
    supplied code where the function behaves incorrectly.

Before deciding bug_found=false, you MUST mentally inspect:

1. Inputs and parameters
2. Variables and their values
3. Conditions and branches
4. Arithmetic/calculations
5. Loops and collection operations
6. State mutations
7. Function calls
8. Exception paths
9. Return values
10. Async behavior
11. Default/mutable arguments
12. Resource lifecycle
13. Validation/business logic
14. Security-sensitive operations visible in the target

Do not immediately answer "no bug".

============================================================
VERY IMPORTANT DECISION RULE
============================================================

If your reasoning identifies a concrete mismatch between:

    EXPECTED BEHAVIOR
        and
    ACTUAL BEHAVIOR

caused by a specific statement in the target function,

then:

    bug_found MUST be true.

Do NOT describe a concrete defect in your reasoning and then output
bug_found=false.

For example, this is INVALID:

    bug_found=false

    reasoning:
    "The function adds every transaction including income, so the
     balance is incorrect."

If the reasoning demonstrates a concrete behavioral defect, the correct
decision is:

    bug_found=true

============================================================
WHAT COUNTS AS A REAL BUG
============================================================

Look for defects such as:

------------------------------------------------------------
A. WRONG CONDITIONS
------------------------------------------------------------

Examples:

    if amount > 0:
        ...
    else:
        ...

where the later behavior demonstrates that the condition is reversed.

Look for:

- inverted comparisons
- wrong variable in condition
- wrong comparison operator
- unreachable valid branch
- mutually exclusive conditions handled incorrectly
- condition checking stale state

------------------------------------------------------------
B. WRONG ARITHMETIC
------------------------------------------------------------

Look for:

- wrong operand
- wrong variable
- wrong sign
- incorrect formula
- incorrect percentage
- incorrect aggregation
- off-by-one calculation
- incorrect ordering of arithmetic
- accumulating the wrong values

Do not assume an arbitrary formula is wrong.

Only report it when the code itself provides evidence.

------------------------------------------------------------
C. WRONG DATA FLOW
------------------------------------------------------------

Trace important variables.

Look for:

    input
      ↓
    transformation
      ↓
    state update
      ↓
    return

A bug exists when the wrong value enters this chain.

Examples:

- variable overwritten too early
- stale value used
- calculated value ignored
- wrong variable returned
- one branch fails to update required state
- accumulator initialized incorrectly

------------------------------------------------------------
D. COLLECTION BUGS
------------------------------------------------------------

Inspect:

- filtering
- iteration
- append/remove
- indexing
- slicing
- aggregation
- first/last element behavior
- duplicate processing
- skipped elements

Ask:

    Which elements actually reach the final result?

------------------------------------------------------------
E. RETURN-VALUE BUGS
------------------------------------------------------------

Check whether the function returns what its own implementation calculates.

Examples:

- calculated value is ignored
- wrong variable returned
- success path returns stale value
- branch returns inconsistent type/value
- empty result incorrectly treated as success

------------------------------------------------------------
F. EXCEPTION / ERROR FLOW
------------------------------------------------------------

Look for:

- exception swallowed and success returned
- invalid value used after exception
- incorrect except branch
- state modified before failure
- error path producing a normal result

Do not report merely "this could throw".

The supplied code must demonstrate why the behavior is incorrect.

------------------------------------------------------------
G. MUTABLE DEFAULT ARGUMENTS
------------------------------------------------------------

Inspect defaults such as:

    def f(items=[]):
        ...

If the mutable object is modified and therefore persists across calls,
this can be a real bug.

Only report it when the function's behavior actually demonstrates the
problem.

------------------------------------------------------------
H. ASYNC BUGS
------------------------------------------------------------

Look for:

- coroutine created but never awaited
- async result treated as the final value
- missing await that changes behavior
- incorrect async control flow

------------------------------------------------------------
I. STATE / MUTATION BUGS
------------------------------------------------------------

Look for:

- object modified too early
- shared mutable state changed unexpectedly
- mutation affects later calculations
- state update performed on the wrong branch
- state reset incorrectly

------------------------------------------------------------
J. VALIDATION / BUSINESS LOGIC
------------------------------------------------------------

Look for explicit contradictions inside the supplied code.

Examples:

    value is validated as positive
    but later negative values are required for the calculation

or:

    function calculates expenses
    but includes income transactions in the same calculation

Only report such a defect when the contradiction is supported by the code.

------------------------------------------------------------
K. RESOURCE LIFECYCLE
------------------------------------------------------------

Look for:

- resource created but not released
- cleanup skipped on a demonstrated path
- incorrect lifecycle ordering

Only report when the target itself demonstrates the defect.

------------------------------------------------------------
L. SECURITY BUGS
------------------------------------------------------------

Only report security bugs when the dangerous operation is directly visible.

Examples:

- unsafe SQL construction
- unsafe filesystem path construction
- command construction
- unsafe deserialization

Do not speculate about vulnerabilities outside the supplied code.

============================================================
BUGS THAT MUST NOT BE REPORTED
============================================================

Do NOT report:

- style preferences
- naming preferences
- formatting
- missing comments
- missing logging
- missing type hints
- refactoring suggestions
- performance concerns without demonstrated incorrect behavior
- scalability concerns
- hypothetical future requirements
- "could potentially fail" without a concrete execution path
- "best practice" violations by themselves
- code that you personally would implement differently

BAD:

    "The function could use validation."

GOOD:

    "The function accepts a value, enters the negative branch because the
     comparison is reversed, and therefore returns a result inconsistent
     with the calculation performed by the function."

============================================================
SINGLE-FILE SCOPE
============================================================

This review is intentionally SINGLE-FILE.

The TARGET FUNCTION belongs to:

    {target.file_path}

You may use:

- the target function
- imports shown in context
- containing class shown in context
- direct local callees shown in context

Do NOT assume behavior from files that were not provided.

If proving the bug requires an external file that is not supplied,
do not invent the missing behavior.

============================================================
SEMANTIC REASONING PROCEDURE
============================================================

Before producing the JSON, perform this internal analysis:

STEP 1
Understand what the function appears to calculate or accomplish.

STEP 2
Identify important inputs and outputs.

STEP 3
Trace the most important values from input to output.

STEP 4
Inspect every meaningful condition.

STEP 5
Inspect arithmetic and aggregation.

STEP 6
Inspect mutations and state changes.

STEP 7
Inspect loops and collection handling.

STEP 8
Inspect exceptions and early returns.

STEP 9
Inspect the final return value.

STEP 10
Ask:

    "Can I give a concrete input/execution path that produces
     incorrect behavior?"

If YES:
    report the strongest concrete bug.

If NO:
    bug_found=false.

============================================================
DO NOT REQUIRE A BUG TO BE OBVIOUS
============================================================

The bug does NOT have to contain a syntax error.

Semantic bugs often look perfectly valid syntactically.

For example:

    total = 0

    for transaction in transactions:
        total += transaction.amount

This can be a semantic bug if the surrounding supplied code explicitly
establishes that only expense transactions should contribute to total.

You must reason about the behavior, not just syntax.

============================================================
REPORT ONLY THE STRONGEST BUG
============================================================

If multiple possible issues exist:

- report only the strongest concrete bug
- do not return multiple bugs
- do not create a list
- choose the bug with the clearest evidence

============================================================
LOCATION REQUIREMENTS
============================================================

For bug_found=true:

    file MUST equal:
        {target.file_path}

    start_line MUST be within:
        {target.start_line} - {target.end_line}

    end_line MUST be within:
        {target.start_line} - {target.end_line}

    relevant_code MUST be copied EXACTLY from the target function.

Never invent source code.

Never invent line numbers.

============================================================
CONFIDENCE
============================================================

Confidence represents evidence strength.

0.95 - 1.00
    Directly demonstrated by the supplied code.

0.90 - 0.94
    Very strong evidence with almost no ambiguity.

0.80 - 0.89
    Strong evidence with minor interpretation.

0.70 - 0.79
    Reasonably supported but some interpretation is required.

Below 0.70
    Do NOT report the bug.
    Return bug_found=false.

Do not increase confidence merely because the bug "sounds plausible".

============================================================
OUTPUT FORMAT
============================================================

Return EXACTLY ONE JSON OBJECT.

No Markdown.

No code fences.

No explanation before the JSON.

No explanation after the JSON.

------------------------------------------------------------
NO BUG
------------------------------------------------------------

{{
  "bug_found": false,
  "bug_type": "",
  "title": "",
  "description": "",
  "file": "{target.file_path}",
  "start_line": {target.start_line},
  "end_line": {target.end_line},
  "evidence": "",
  "reasoning": "",
  "expected_behavior": "",
  "actual_behavior": "",
  "confidence": 0.0,
  "relevant_code": ""
}}

------------------------------------------------------------
TRUE BUG
------------------------------------------------------------

{{
  "bug_found": true,
  "bug_type": "specific semantic bug category",
  "title": "short concrete title",
  "description": "precise description of the defect",
  "file": "{target.file_path}",
  "start_line": 0,
  "end_line": 0,
  "evidence": "specific source evidence proving the defect",
  "reasoning": "explain the concrete execution path that produces wrong behavior",
  "expected_behavior": "what the function should do",
  "actual_behavior": "what the current implementation does",
  "confidence": 0.0,
  "relevant_code": "exact source excerpt copied from the target function"
}}

============================================================
SELF-CHECK BEFORE OUTPUT
============================================================

If bug_found=true, verify:

[ ] I identified a concrete behavioral defect.
[ ] I identified a specific execution/input path.
[ ] The defect is visible in the supplied code.
[ ] The defect belongs to the target function.
[ ] I did not invent external requirements.
[ ] relevant_code is copied exactly.
[ ] file is the target file.
[ ] line numbers are inside the target function.
[ ] expected_behavior differs from actual_behavior.
[ ] confidence reflects actual evidence.

If ANY of these are false:

    return bug_found=false.

IMPORTANT:

If the reasoning itself proves that a concrete defect exists,
DO NOT output bug_found=false.

============================================================
TARGET
============================================================

Language:
{target.language}

File:
{target.file_path}

Function:
{target.qualified_name}

Function lines:
{target.start_line}-{target.end_line}

Parameters:
{", ".join(target.parameters) if target.parameters else "(none)"}

Async:
{target.is_async}

Decorators:
{", ".join(target.decorators) if target.decorators else "(none)"}

============================================================
CONTEXT
============================================================

Included sections:
{", ".join(context.included)}

Context truncated:
{context.truncated}

============================================================
SOURCE / CONTEXT
============================================================

{context.text}
""".strip()


# =============================================================================
# Component 6 — LLM response parsing
# =============================================================================

def parse_llm_finding(
    text: str,
) -> dict[str, Any] | None:
    """
    Parse exactly one JSON object from the LLM response.

    Supported forms:

        {...}

    and:

        ```json
        {...}
        ```

    A small amount of whitespace around the JSON is allowed.

    The parser intentionally does not perform aggressive JSON repair because
    silently repairing a hallucinated response can create false findings.
    """

    if not isinstance(
        text,
        str,
    ):
        return None

    stripped = text.strip()

    if not stripped:
        return None

    # -------------------------------------------------------------
    # Remove one Markdown fence.
    # -------------------------------------------------------------

    if stripped.startswith("```"):

        lines = stripped.splitlines()

        if len(lines) < 2:
            return None

        first_line = lines[0].strip()

        if not first_line.startswith("```"):
            return None

        lines = lines[1:]

        if (
            lines
            and lines[-1].strip().startswith("```")
        ):
            lines = lines[:-1]

        stripped = "\n".join(
            lines
        ).strip()

    if not stripped:
        return None

    # -------------------------------------------------------------
    # Direct JSON parse.
    # -------------------------------------------------------------

    try:
        value = json.loads(
            stripped
        )
    except (
        TypeError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(
        value,
        dict,
    ):
        return None

    return value


# =============================================================================
# Component 7 — Finding validation
# =============================================================================

def _normalize_source_for_match(
    value: str,
) -> str:
    """
    Normalize only line-ending differences.

    We deliberately do NOT strip arbitrary whitespace because relevant_code
    should remain closely tied to the actual source.
    """

    return (
        value
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )


def _line_numbers_for_source_fragment(
    source: str,
    fragment: str,
    target_start_line: int,
) -> tuple[int, int] | None:
    """
    Determine source line numbers for an exact source fragment.

    Returns:

        (start_line, end_line)

    or None if the fragment cannot be located.
    """

    source_normalized = _normalize_source_for_match(
        source
    )

    fragment_normalized = _normalize_source_for_match(
        fragment
    )

    if not fragment_normalized.strip():
        return None

    index = source_normalized.find(
        fragment_normalized
    )

    if index < 0:
        return None

    before = source_normalized[:index]

    start_line = (
        target_start_line
        + before.count("\n")
    )

    fragment_lines = (
        fragment_normalized.count("\n")
        + 1
    )

    end_line = (
        start_line
        + fragment_lines
        - 1
    )

    return (
        start_line,
        end_line,
    )


def _source_identifiers(
    source: str,
) -> set[str]:
    """
    Extract identifiers from source using Python AST.

    This is used only as supplementary evidence.

    It is NOT used as the primary proof of a finding.
    """

    try:
        tree = ast.parse(
            textwrap.dedent(
                source
            )
        )
    except SyntaxError:
        return set()

    names: set[str] = set()

    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.Name,
        ):
            names.add(
                node.id
            )

        elif isinstance(
            node,
            ast.arg,
        ):
            names.add(
                node.arg
            )

        elif isinstance(
            node,
            ast.Attribute,
        ):
            names.add(
                node.attr
            )

        elif isinstance(
            node,
            ast.FunctionDef,
        ):
            names.add(
                node.name
            )

        elif isinstance(
            node,
            ast.AsyncFunctionDef,
        ):
            names.add(
                node.name
            )

    return names


def _extract_identifiers_from_text(
    text: str,
) -> set[str]:
    """
    Extract identifier-like tokens from natural-language evidence.

    This is intentionally only a weak supporting signal.

    It is NOT used to reject a finding by itself.
    """

    if not isinstance(
        text,
        str,
    ):
        return set()

    identifiers = set()

    # Python-like identifiers, including names such as:
    #
    # transaction.amount
    # total_cents
    # calculate_total
    #
    for match in re.finditer(
        r"\b[A-Za-z_][A-Za-z0-9_]*\b",
        text,
    ):
        token = match.group(0)

        if token.isidentifier():
            identifiers.add(
                token
            )

    return identifiers


def _evidence_has_source_connection(
    candidate: dict[str, Any],
    target: ExtractedFunction,
) -> bool:
    """
    Determine whether the LLM evidence has a reasonable connection to the
    target source.

    This is deliberately permissive.

    The old validator rejected legitimate findings because it required a
    simplistic identifier intersection.

    Here we use several signals:

    1. relevant_code is exact source.
    2. evidence mentions identifiers from source.
    3. reasoning mentions identifiers from source.
    4. expected/actual behavior mentions identifiers from source.

    At least one meaningful source connection is required.
    """

    target_source = target.source

    source_names = _source_identifiers(
        target_source
    )

    # -------------------------------------------------------------
    # Strongest signal:
    # exact relevant code.
    # -------------------------------------------------------------

    relevant_code = candidate.get(
        "relevant_code",
        "",
    )

    if isinstance(
        relevant_code,
        str,
    ) and relevant_code.strip():

        if _normalize_source_for_match(
            relevant_code
        ) in _normalize_source_for_match(
            target_source
        ):
            return True

    # -------------------------------------------------------------
    # Natural-language evidence signals.
    # -------------------------------------------------------------

    text_fields = (
        candidate.get(
            "evidence",
            "",
        ),
        candidate.get(
            "reasoning",
            "",
        ),
        candidate.get(
            "expected_behavior",
            "",
        ),
        candidate.get(
            "actual_behavior",
            "",
        ),
    )

    mentioned_names: set[str] = set()

    for field in text_fields:

        if not isinstance(
            field,
            str,
        ):
            continue

        mentioned_names.update(
            _extract_identifiers_from_text(
                field
            )
        )

    if (
        source_names
        and mentioned_names
        and (
            source_names
            & mentioned_names
        )
    ):
        return True

    # -------------------------------------------------------------
    # Operators/expressions can be valid evidence even when the
    # natural-language parser does not find an identifier.
    #
    # Examples:
    #
    #     amount * 100
    #     balance += transaction.amount
    #     if amount < 0
    #
    # Relevant code already passed the exact-source check above,
    # so this section is mostly defensive.
    # -------------------------------------------------------------

    if isinstance(
        relevant_code,
        str,
    ):

        if any(
            operator in relevant_code
            for operator in (
                "=",
                "+",
                "-",
                "*",
                "/",
                "%",
                "<",
                ">",
                "==",
                "!=",
                " in ",
                " not in ",
            )
        ):
            if relevant_code.strip():
                return True

    return False


def validate_finding(
    candidate: dict[str, Any] | None,
    target: ExtractedFunction,
    config: SemanticReviewConfig | None = None,
) -> tuple[str, str | None]:
    """
    Validate a parsed LLM candidate against the actual target source.

    Returns:

        ("NO_BUG", None)

        ("SUPPORTED", None)

        ("UNCERTAIN", reason)

        ("UNSUPPORTED", reason)

    Important:

    Validation is designed to prevent hallucinations without suppressing
    legitimate semantic findings.

    The old identifier-only evidence validation was too aggressive.
    """

    config = (
        config
        or SemanticReviewConfig()
    )

    # =================================================================
    # Basic response validation
    # =================================================================

    if not candidate:
        return (
            "UNSUPPORTED",
            "Malformed or missing JSON object.",
        )

    if not isinstance(
        candidate.get(
            "bug_found"
        ),
        bool,
    ):
        return (
            "UNSUPPORTED",
            "Missing or invalid bug_found field.",
        )

    # =================================================================
    # Explicit NO BUG
    # =================================================================

    if candidate["bug_found"] is False:

        # -------------------------------------------------------------
        # If the model claims no bug, we trust that decision here.
        #
        # This component validates findings; it does not invent findings
        # from a no-bug response.
        # -------------------------------------------------------------

        return (
            "NO_BUG",
            None,
        )

    # =================================================================
    # Required evidence fields
    # =================================================================

    required_string_fields = (
        "bug_type",
        "title",
        "description",
        "evidence",
        "reasoning",
        "expected_behavior",
        "actual_behavior",
        "relevant_code",
    )

    for field_name in required_string_fields:

        value = candidate.get(
            field_name
        )

        if not isinstance(
            value,
            str,
        ):
            return (
                "UNSUPPORTED",
                f"Field '{field_name}' must be a string.",
            )

        if not value.strip():
            return (
                "UNSUPPORTED",
                f"Missing required field '{field_name}'.",
            )

    # =================================================================
    # File validation
    # =================================================================

    candidate_file = candidate.get(
        "file"
    )

    if candidate_file != target.file_path:
        return (
            "UNSUPPORTED",
            "Finding references a different file.",
        )

    # =================================================================
    # Line validation
    # =================================================================

    try:

        start = int(
            candidate["start_line"]
        )

        end = int(
            candidate["end_line"]
        )

    except (
        KeyError,
        TypeError,
        ValueError,
    ):

        return (
            "UNSUPPORTED",
            "Invalid finding location.",
        )

    if start < target.start_line:
        return (
            "UNSUPPORTED",
            "Finding starts before the target function.",
        )

    if end < start:
        return (
            "UNSUPPORTED",
            "Finding end line is before start line.",
        )

    if end > target.end_line:
        return (
            "UNSUPPORTED",
            "Finding ends outside the target function.",
        )

    # =================================================================
    # Relevant-code validation
    # =================================================================

    relevant_code = candidate[
        "relevant_code"
    ]

    normalized_target_source = (
        _normalize_source_for_match(
            target.source
        )
    )

    normalized_relevant_code = (
        _normalize_source_for_match(
            relevant_code
        )
    )

    if (
        not normalized_relevant_code.strip()
        or normalized_relevant_code
        not in normalized_target_source
    ):
        return (
            "UNSUPPORTED",
            (
                "relevant_code is not an exact "
                "source fragment from the target function."
            ),
        )

    # =================================================================
    # Verify that the reported lines correspond reasonably to the
    # relevant code.
    # =================================================================

    fragment_location = (
        _line_numbers_for_source_fragment(
            target.source,
            relevant_code,
            target.start_line,
        )
    )

    if fragment_location is not None:

        fragment_start, fragment_end = (
            fragment_location
        )

        # -------------------------------------------------------------
        # Allow a small range around the exact fragment because the LLM
        # may report the enclosing statement rather than the smallest
        # possible expression.
        # -------------------------------------------------------------

        if (
            end < fragment_start
            or start > fragment_end
        ):
            return (
                "UNSUPPORTED",
                (
                    "Reported location does not "
                    "overlap relevant_code."
                ),
            )

    # =================================================================
    # Confidence validation
    # =================================================================

    try:

        confidence = float(
            candidate.get(
                "confidence",
                0.0,
            )
        )

    except (
        TypeError,
        ValueError,
    ):

        return (
            "UNSUPPORTED",
            "Invalid confidence value.",
        )

    if not 0.0 <= confidence <= 1.0:
        return (
            "UNSUPPORTED",
            "Confidence must be between 0.0 and 1.0.",
        )

    if confidence < config.min_confidence:
        return (
            "UNCERTAIN",
            (
                f"Confidence {confidence:.2f} is below "
                f"minimum {config.min_confidence:.2f}."
            ),
        )

    # =================================================================
    # Evidence/source connection
    # =================================================================

    if not _evidence_has_source_connection(
        candidate,
        target,
    ):
        return (
            "UNCERTAIN",
            (
                "The finding could not be sufficiently "
                "connected to the supplied target source."
            ),
        )

    # =================================================================
    # Expected vs actual behavior
    # =================================================================

    expected = (
        candidate[
            "expected_behavior"
        ]
        .strip()
        .lower()
    )

    actual = (
        candidate[
            "actual_behavior"
        ]
        .strip()
        .lower()
    )

    if expected == actual:
        return (
            "UNCERTAIN",
            "Expected and actual behavior are identical.",
        )

    # =================================================================
    # Reasoning quality
    # =================================================================

    reasoning = candidate[
        "reasoning"
    ].strip()

    if len(reasoning) < 15:
        return (
            "UNCERTAIN",
            "Reasoning is too short to establish a concrete defect.",
        )

    # =================================================================
    # Description quality
    # =================================================================

    description = candidate[
        "description"
    ].strip()

    if len(description) < 10:
        return (
            "UNCERTAIN",
            "Description is too short to establish a concrete defect.",
        )

    # =================================================================
    # Evidence quality
    # =================================================================

    evidence = candidate[
        "evidence"
    ].strip()

    if len(evidence) < 10:
        return (
            "UNCERTAIN",
            "Evidence is too short to establish a concrete defect.",
        )

    # =================================================================
    # Final semantic consistency check
    # =================================================================

    # If the model says bug_found=true, we require:
    #
    # - real source fragment
    # - valid location
    # - confidence threshold
    # - source connection
    # - different expected/actual behavior
    # - meaningful reasoning
    #
    # At this point the finding is supported enough to persist.

    return (
        "SUPPORTED",
        None,
    )