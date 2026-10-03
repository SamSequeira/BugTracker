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
import logging
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)



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
        ".tox",
        ".mypy_cache",
        ".ruff_cache",
        ".idea",
        ".vscode",
        "htmlcov",
    }
)


SOURCE_SUFFIXES = {
    ".py": "python",
    ".js": "javascript",
    ".java": "java",
}


# =============================================================================
# Tree-sitter parser infrastructure
# =============================================================================

_PARSERS: dict[str, Any] = {}


def _get_parser(language: str) -> Any | None:
    norm_lang = language.lower()
    if norm_lang in _PARSERS:
        return _PARSERS[norm_lang]

    # Reusing existing parser setup from ast_generator.py
    try:
        from app.services.ast_generator import ASTGenerator

        gen = ASTGenerator()
        for k, v in gen._parsers.items():
            _PARSERS[k.lower()] = v
        if norm_lang in _PARSERS:
            return _PARSERS[norm_lang]
    except Exception:
        pass

    # Direct tree-sitter initialization fallback
    try:
        from tree_sitter import Language, Parser

        if norm_lang == "python":
            import tree_sitter_python as mod
        elif norm_lang == "javascript":
            import tree_sitter_javascript as mod
        elif norm_lang == "java":
            import tree_sitter_java as mod
        else:
            return None

        try:
            lang_obj = Language(mod.language())
        except TypeError:
            lang_obj = Language(mod.language(), norm_lang)

        parser = Parser()
        if hasattr(parser, "set_language"):
            parser.set_language(lang_obj)
        else:
            parser.language = lang_obj

        _PARSERS[norm_lang] = parser
        return parser
    except Exception:
        return None


def _validate_syntax(source: str, language: str, filename: str = "") -> bool:
    """Validate source code syntax using the appropriate parser."""
    if language == "python":
        try:
            ast.parse(source, filename=filename)
            return True
        except SyntaxError:
            return False

    parser = _get_parser(language)
    if parser is None:
        return False

    try:
        tree = parser.parse(source.encode("utf-8"))
        root = tree.root_node
        if root is None or root.type == "ERROR":
            return False
        return not root.has_error
    except Exception:
        return False


def _has_executable_definitions(source: str, language: str) -> bool:
    """Check if source contains executable function/method/class definitions."""
    if language == "python":
        try:
            tree = ast.parse(source)
            return any(
                isinstance(
                    node,
                    (
                        ast.FunctionDef,
                        ast.AsyncFunctionDef,
                        ast.ClassDef,
                    ),
                )
                for node in ast.walk(tree)
            )
        except SyntaxError:
            return False

    parser = _get_parser(language)
    if parser is None:
        return False

    try:
        tree = parser.parse(source.encode("utf-8"))
        root = tree.root_node
        if root is None:
            return False

        if language == "javascript":
            target_types = {
                "function_declaration",
                "generator_function_declaration",
                "method_definition",
                "class_declaration",
                "arrow_function",
                "function_expression",
            }
        elif language == "java":
            target_types = {
                "method_declaration",
                "constructor_declaration",
                "class_declaration",
                "interface_declaration",
                "enum_declaration",
                "record_declaration",
            }
        else:
            return False

        stack = [root]
        while stack:
            n = stack.pop()
            if n.type in target_types:
                return True
            stack.extend(n.children)
        return False
    except Exception:
        return False



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
            "20",
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

# Maximum size for a single source file (10MB in characters, ~10MB assuming mostly ASCII)
MAX_INDIVIDUAL_FILE_CHARS = 10_000_000



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
    # Metadata added in context v2 — all fields have defaults for backward compat
    omitted: tuple[str, ...] = ()
    unresolved_symbols: tuple[str, ...] = ()
    cross_file_resolved: tuple[str, ...] = ()


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
    seen_paths: set[Path] = set()

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

        # Skip duplicate paths (symlinks, hardlinks)
        resolved_path = path.resolve()
        if resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)

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

        if lower_name.endswith((".test.js", ".spec.js", "_test.js")):
            continue

        if lower_name.endswith(("test.java", "tests.java", "testcase.java")):
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

        if file_size > MAX_INDIVIDUAL_FILE_CHARS:
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

        language = SOURCE_SUFFIXES[suffix]

        if not _validate_syntax(
            source,
            language,
            filename=str(path),
        ):
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
            "index",
            "application",
        }:
            reasons.append(
                "application-entry hint"
            )

        # -------------------------------------------------------------
        # Executable definitions
        # -------------------------------------------------------------

        if _has_executable_definitions(source, language):
            reasons.append(
                "executable definitions"
            )

        # Files without specific hints get lower priority but are still included
        if not reasons:
            if language == "python":
                reasons.append("executable-python-file")
            else:
                reasons.append(f"executable-{language}-file")

        candidates.append(
            SelectedFile(
                path=path,
                relative_path=relative.as_posix(),
                language=language,
                source_chars=len(source),
                selection_reasons=tuple(reasons),
            )
        )

    # -------------------------------------------------------------
    # Deterministic ordering
    # -------------------------------------------------------------

    candidates.sort(
        key=lambda item: (
            "application-directory hint" not in item.selection_reasons,
            "application-entry hint" not in item.selection_reasons,
            (
                "executable-python-file" in item.selection_reasons
                or f"executable-{item.language}-file" in item.selection_reasons
            ),
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


def _extract_js_functions(
    selected_file: SelectedFile,
) -> list[ExtractedFunction]:
    """
    Extract JavaScript functions, async functions, arrow functions, and class methods using tree-sitter.
    """
    try:
        source = selected_file.path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []

    lines = source.splitlines()
    parser = _get_parser("javascript")
    if parser is None:
        return []

    try:
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        return []

    root = tree.root_node
    if root is None:
        return []

    def _get_node_source(n) -> str:
        s_line = n.start_point[0]
        e_line = n.end_point[0]
        return "\n".join(lines[s_line : e_line + 1])

    # 1. Imports
    imports_list: list[str] = []
    for child in root.children:
        if child.type == "import_statement":
            imports_list.append(_get_node_source(child))
        elif child.type in ("variable_declaration", "lexical_declaration"):
            child_text = child.text.decode("utf-8", errors="replace") if child.text else ""
            if "require(" in child_text:
                imports_list.append(_get_node_source(child))
    imports = tuple(imports_list)

    # 2. Module definitions (top-level constants/variables/classes)
    module_defs: list[tuple[str, str, str]] = []
    seen_defs: set[str] = set()
    for child in root.children:
        if child.type == "class_declaration":
            name_node = child.child_by_field_name("name")
            if name_node and name_node.text:
                c_name = name_node.text.decode("utf-8", errors="replace")
                if c_name not in seen_defs:
                    seen_defs.add(c_name)
                    module_defs.append(("class", c_name, _get_node_source(child)))
        elif child.type in ("variable_declaration", "lexical_declaration"):
            for declarator in child.children:
                if declarator.type == "variable_declarator":
                    val = declarator.child_by_field_name("value")
                    if val and val.type not in ("arrow_function", "function_expression", "generator_function"):
                        name_node = declarator.child_by_field_name("name")
                        if name_node and name_node.text:
                            v_name = name_node.text.decode("utf-8", errors="replace")
                            if v_name not in seen_defs:
                                seen_defs.add(v_name)
                                module_defs.append(("variable", v_name, _get_node_source(child)))

    def _get_js_parameters(param_node) -> tuple[str, ...]:
        if not param_node:
            return ()
        if param_node.type == "identifier":
            return (param_node.text.decode("utf-8", errors="replace"),)
        params: list[str] = []
        for p in param_node.children:
            if p.type == "identifier":
                params.append(p.text.decode("utf-8", errors="replace"))
            elif p.type == "assignment_pattern":
                left = p.child_by_field_name("left")
                if left and left.text:
                    params.append(left.text.decode("utf-8", errors="replace"))
            elif p.type == "rest_pattern":
                arg = p.child_by_field_name("argument")
                if arg and arg.text:
                    params.append("..." + arg.text.decode("utf-8", errors="replace"))
                elif p.text:
                    params.append(p.text.decode("utf-8", errors="replace"))
            elif p.type in ("object_pattern", "array_pattern") and p.text:
                params.append(p.text.decode("utf-8", errors="replace"))
        return tuple(params)

    def _is_js_async(n) -> bool:
        for child in n.children:
            if child.type == "async":
                return True
        return False

    def _get_js_decorators(n) -> tuple[str, ...]:
        decs: list[str] = []
        for child in n.children:
            if child.type == "decorator" and child.text:
                decs.append(child.text.decode("utf-8", errors="replace"))
        return tuple(decs)

    def _get_called_names(n) -> tuple[str, ...]:
        calls: set[str] = set()
        stack = [n]
        while stack:
            curr = stack.pop()
            if curr.type == "call_expression":
                fn = curr.child_by_field_name("function")
                if fn:
                    if fn.type == "identifier" and fn.text:
                        calls.add(fn.text.decode("utf-8", errors="replace"))
                    elif fn.type == "member_expression":
                        prop = fn.child_by_field_name("property")
                        if prop and prop.type in ("property_identifier", "identifier") and prop.text:
                            calls.add(prop.text.decode("utf-8", errors="replace"))
            elif curr.type == "new_expression":
                ctor = curr.child_by_field_name("constructor")
                if ctor and ctor.type == "identifier" and ctor.text:
                    calls.add(ctor.text.decode("utf-8", errors="replace"))
            stack.extend(curr.children)
        return tuple(sorted(calls))

    results: list[ExtractedFunction] = []
    seen: set[tuple[str, int]] = set()

    def _visit(node, class_name: str | None = None, class_source: str | None = None):
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            c_name = name_node.text.decode("utf-8", errors="replace") if (name_node and name_node.text) else "AnonymousClass"
            c_src = _get_node_source(node)
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    _visit(child, class_name=c_name, class_source=c_src)
            return

        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            m_name = name_node.text.decode("utf-8", errors="replace") if (name_node and name_node.text) else "anonymous"
            q_name = f"{class_name}.{m_name}" if class_name else m_name
            start_line = node.start_point[0] + 1
            key = (q_name, start_line)
            if key not in seen:
                seen.add(key)
                fn_source = _get_node_source(node)
                params = _get_js_parameters(node.child_by_field_name("parameters"))
                results.append(
                    ExtractedFunction(
                        file_path=selected_file.relative_path,
                        language="javascript",
                        name=m_name,
                        class_name=class_name,
                        qualified_name=q_name,
                        start_line=start_line,
                        end_line=node.end_point[0] + 1,
                        source=fn_source,
                        parameters=params,
                        is_async=_is_js_async(node),
                        decorators=_get_js_decorators(node),
                        called_names=_get_called_names(node),
                        imports=imports,
                        class_source=class_source,
                        module_definitions=tuple(
                            (kind, d_name, d_src)
                            for kind, d_name, d_src in module_defs
                            if re.search(r"\b" + re.escape(d_name) + r"\b", fn_source)
                            and not (kind == "class" and d_name == class_name)
                        ),
                    )
                )
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    _visit(child, class_name=class_name, class_source=class_source)
            return

        if node.type in ("function_declaration", "generator_function_declaration"):
            name_node = node.child_by_field_name("name")
            fn_name = name_node.text.decode("utf-8", errors="replace") if (name_node and name_node.text) else "anonymous"
            q_name = f"{class_name}.{fn_name}" if class_name else fn_name
            start_line = node.start_point[0] + 1
            key = (q_name, start_line)
            if key not in seen:
                seen.add(key)
                fn_source = _get_node_source(node)
                params = _get_js_parameters(node.child_by_field_name("parameters"))
                results.append(
                    ExtractedFunction(
                        file_path=selected_file.relative_path,
                        language="javascript",
                        name=fn_name,
                        class_name=class_name,
                        qualified_name=q_name,
                        start_line=start_line,
                        end_line=node.end_point[0] + 1,
                        source=fn_source,
                        parameters=params,
                        is_async=_is_js_async(node),
                        decorators=_get_js_decorators(node),
                        called_names=_get_called_names(node),
                        imports=imports,
                        class_source=class_source,
                        module_definitions=tuple(
                            (kind, d_name, d_src)
                            for kind, d_name, d_src in module_defs
                            if re.search(r"\b" + re.escape(d_name) + r"\b", fn_source)
                            and not (kind == "class" and d_name == class_name)
                        ),
                    )
                )
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    _visit(child, class_name=class_name, class_source=class_source)
            return

        if node.type == "variable_declarator":
            val = node.child_by_field_name("value")
            if val and val.type in ("arrow_function", "function_expression", "generator_function"):
                name_node = node.child_by_field_name("name")
                fn_name = name_node.text.decode("utf-8", errors="replace") if (name_node and name_node.text) else "anonymous"
                q_name = f"{class_name}.{fn_name}" if class_name else fn_name
                parent = node.parent
                decl_node = parent if parent and parent.type in ("lexical_declaration", "variable_declaration") else node
                if decl_node.parent and decl_node.parent.type == "export_statement":
                    decl_node = decl_node.parent
                start_line = decl_node.start_point[0] + 1
                key = (q_name, start_line)
                if key not in seen:
                    seen.add(key)
                    fn_source = _get_node_source(decl_node)
                    param_node = val.child_by_field_name("parameters") or val.child_by_field_name("parameter")
                    params = _get_js_parameters(param_node)
                    results.append(
                        ExtractedFunction(
                            file_path=selected_file.relative_path,
                            language="javascript",
                            name=fn_name,
                            class_name=class_name,
                            qualified_name=q_name,
                            start_line=start_line,
                            end_line=decl_node.end_point[0] + 1,
                            source=fn_source,
                            parameters=params,
                            is_async=_is_js_async(val),
                            decorators=(),
                            called_names=_get_called_names(val),
                            imports=imports,
                            class_source=class_source,
                            module_definitions=tuple(
                                (kind, d_name, d_src)
                                for kind, d_name, d_src in module_defs
                                if re.search(r"\b" + re.escape(d_name) + r"\b", fn_source)
                                and not (kind == "class" and d_name == class_name)
                            ),
                        )
                    )
                body = val.child_by_field_name("body")
                if body:
                    if body.type == "statement_block":
                        for child in body.children:
                            _visit(child, class_name=class_name, class_source=class_source)
                    else:
                        _visit(body, class_name=class_name, class_source=class_source)
                return

        for child in node.children:
            _visit(child, class_name=class_name, class_source=class_source)

    for child in root.children:
        _visit(child)

    results.sort(
        key=lambda function: (
            function.file_path.lower(),
            function.start_line,
            function.qualified_name.lower(),
        )
    )
    return results


def _extract_java_functions(
    selected_file: SelectedFile,
) -> list[ExtractedFunction]:
    """
    Extract Java methods and constructors from classes, interfaces, records, and enums using tree-sitter.
    """
    try:
        source = selected_file.path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return []

    lines = source.splitlines()
    parser = _get_parser("java")
    if parser is None:
        return []

    try:
        tree = parser.parse(source.encode("utf-8"))
    except Exception:
        return []

    root = tree.root_node
    if root is None:
        return []

    def _get_node_source(n) -> str:
        s_line = n.start_point[0]
        e_line = n.end_point[0]
        return "\n".join(lines[s_line : e_line + 1])

    # 1. Imports
    imports_list: list[str] = []
    for child in root.children:
        if child.type == "import_declaration":
            imports_list.append(_get_node_source(child))
    imports = tuple(imports_list)

    def _get_java_parameters(param_node) -> tuple[str, ...]:
        if not param_node:
            return ()
        params: list[str] = []
        for p in param_node.children:
            if p.type in ("formal_parameter", "spread_parameter"):
                name_node = p.child_by_field_name("name")
                if name_node and name_node.text:
                    params.append(name_node.text.decode("utf-8", errors="replace"))
                else:
                    for sub in p.children:
                        if sub.type == "identifier" and sub.text:
                            params.append(sub.text.decode("utf-8", errors="replace"))
                            break
        return tuple(params)

    def _get_java_annotations(node) -> tuple[str, ...]:
        annotations: list[str] = []
        modifiers = node.child_by_field_name("modifiers")
        if modifiers:
            for child in modifiers.children:
                if child.type in ("annotation", "marker_annotation") and child.text:
                    annotations.append(child.text.decode("utf-8", errors="replace"))
        return tuple(annotations)

    def _get_java_called_names(node) -> tuple[str, ...]:
        calls: set[str] = set()
        stack = [node]
        while stack:
            curr = stack.pop()
            if curr.type == "method_invocation":
                name_node = curr.child_by_field_name("name")
                if name_node and name_node.text:
                    calls.add(name_node.text.decode("utf-8", errors="replace"))
            elif curr.type == "object_creation_expression":
                type_node = curr.child_by_field_name("type")
                if type_node and type_node.text:
                    calls.add(type_node.text.decode("utf-8", errors="replace"))
            stack.extend(curr.children)
        return tuple(sorted(calls))

    results: list[ExtractedFunction] = []
    seen: set[tuple[str, int]] = set()

    def _visit(
        node,
        class_name: str | None = None,
        class_source: str | None = None,
        class_fields: tuple[tuple[str, str, str], ...] = (),
    ):
        if node.type in (
            "class_declaration",
            "record_declaration",
            "enum_declaration",
            "interface_declaration",
        ):
            name_node = node.child_by_field_name("name")
            c_name = name_node.text.decode("utf-8", errors="replace") if (name_node and name_node.text) else "UnknownClass"
            c_src = _get_node_source(node)
            body = node.child_by_field_name("body")

            fields_list: list[tuple[str, str, str]] = []
            if body:
                for child in body.children:
                    if child.type == "field_declaration":
                        f_src = _get_node_source(child)
                        for sub in child.children:
                            if sub.type == "variable_declarator":
                                v_name_node = sub.child_by_field_name("name")
                                if v_name_node and v_name_node.text:
                                    fields_list.append(("field", v_name_node.text.decode("utf-8", errors="replace"), f_src))

            if body:
                for child in body.children:
                    _visit(
                        child,
                        class_name=c_name,
                        class_source=c_src,
                        class_fields=tuple(fields_list),
                    )
            return

        if node.type in ("method_declaration", "constructor_declaration"):
            # Only extract methods/constructors with an implementation body
            body = node.child_by_field_name("body")
            if not body:
                return

            name_node = node.child_by_field_name("name")
            m_name = name_node.text.decode("utf-8", errors="replace") if (name_node and name_node.text) else "unknown"
            q_name = f"{class_name}.{m_name}" if class_name else m_name
            start_line = node.start_point[0] + 1
            key = (q_name, start_line)
            if key not in seen:
                seen.add(key)
                fn_source = _get_node_source(node)
                params = _get_java_parameters(node.child_by_field_name("parameters"))
                annotations = _get_java_annotations(node)
                calls = _get_java_called_names(node)

                matching_fields = tuple(
                    (kind, f_name, f_src)
                    for kind, f_name, f_src in class_fields
                    if re.search(r"\b" + re.escape(f_name) + r"\b", fn_source)
                )

                results.append(
                    ExtractedFunction(
                        file_path=selected_file.relative_path,
                        language="java",
                        name=m_name,
                        class_name=class_name,
                        qualified_name=q_name,
                        start_line=start_line,
                        end_line=node.end_point[0] + 1,
                        source=fn_source,
                        parameters=params,
                        is_async=False,
                        decorators=annotations,
                        called_names=calls,
                        imports=imports,
                        class_source=class_source,
                        module_definitions=matching_fields,
                    )
                )
            return

        for child in node.children:
            _visit(
                child,
                class_name=class_name,
                class_source=class_source,
                class_fields=class_fields,
            )

    for child in root.children:
        _visit(child)

    results.sort(
        key=lambda function: (
            function.file_path.lower(),
            function.start_line,
            function.qualified_name.lower(),
        )
    )
    return results


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
    if selected_file.language == "javascript":
        return _extract_js_functions(selected_file)

    if selected_file.language == "java":
        return _extract_java_functions(selected_file)

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
# Context-building helpers (added for context-quality improvement)
# =============================================================================

import sys as _sys


# Standard library module names (top-level packages only, sampled)
_STDLIB_TOP: frozenset[str] = frozenset({
    "abc", "ast", "asyncio", "base64", "binascii", "builtins", "cgi", "codecs",
    "collections", "concurrent", "contextlib", "copy", "csv", "dataclasses",
    "datetime", "decimal", "difflib", "email", "enum", "errno", "fnmatch",
    "functools", "gc", "glob", "gzip", "hashlib", "heapq", "hmac", "html",
    "http", "importlib", "inspect", "io", "ipaddress", "itertools", "json",
    "keyword", "linecache", "locale", "logging", "lzma", "math", "mimetypes",
    "multiprocessing", "numbers", "operator", "os", "pathlib", "pickle",
    "platform", "pprint", "queue", "random", "re", "secrets", "select",
    "shlex", "shutil", "signal", "socket", "socketserver", "sqlite3", "ssl",
    "stat", "string", "struct", "subprocess", "sys", "tarfile", "tempfile",
    "textwrap", "threading", "time", "timeit", "token", "tokenize", "traceback",
    "types", "typing", "unicodedata", "unittest", "urllib", "uuid", "warnings",
    "weakref", "xml", "xmlrpc", "zipfile", "zipimport", "zlib",
})

# Augment with runtime stdlib set if available
try:
    import sys as _sys_rt
    if hasattr(_sys_rt, "stdlib_module_names"):
        _STDLIB_TOP = _STDLIB_TOP | _sys_rt.stdlib_module_names  # type: ignore[attr-defined]
except Exception:
    pass


def _top_package(module_path: str) -> str:
    """Return the top-level package name from a dotted import path."""
    return module_path.split(".")[0] if module_path else ""


def _classify_imports_python(
    import_stmts: tuple[str, ...],
    repo_root: str | None = None,
) -> dict[str, list[str]]:
    """
    Classify Python import statements into four buckets.

    Returns a dict with keys:
        "stdlib"       - standard library
        "local"        - local project (starts with 'app', 'backend', relative, or
                         top-level package exists as directory under repo_root)
        "third_party"  - everything else
        "unknown"      - unparseable lines
    """
    buckets: dict[str, list[str]] = {
        "stdlib": [],
        "local": [],
        "third_party": [],
        "unknown": [],
    }

    # Common local project root package names
    local_hints: set[str] = {"app", "backend", "core", "api", "services", "models",
                              "routers", "data", "config", "utils", "helpers",
                              "schemas", "db", "repositories"}

    for stmt in import_stmts:
        try:
            node = ast.parse(stmt.strip(), mode="single").body[0]
        except (SyntaxError, IndexError):
            buckets["unknown"].append(stmt)
            continue

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # Relative import → always local
            if node.level and node.level > 0:
                buckets["local"].append(stmt)
                continue
            top = _top_package(module)
        elif isinstance(node, ast.Import):
            top = _top_package(node.names[0].name if node.names else "")
            module = top
        else:
            buckets["unknown"].append(stmt)
            continue

        if not top:
            buckets["unknown"].append(stmt)
        elif top in _STDLIB_TOP:
            buckets["stdlib"].append(stmt)
        elif top in local_hints:
            buckets["local"].append(stmt)
        elif repo_root:
            # Check if the top-level package exists as a directory
            pkg_dir = Path(repo_root) / top
            if pkg_dir.is_dir():
                buckets["local"].append(stmt)
            else:
                buckets["third_party"].append(stmt)
        else:
            buckets["third_party"].append(stmt)

    return buckets


def _return_flow_python(source: str) -> list[str]:
    """
    Deterministically extract what a Python function returns.

    Returns a list of short descriptive strings such as:
        "None (implicit)"
        "variable: active_counts"
        "literal: False"
        "call: expense_service.create_expense(...)"
        "multiple return branches"
    """
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return []

    # The outer function node
    func_nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not func_nodes:
        return []
    func = func_nodes[0]

    returns: list[str] = []
    seen: set[str] = set()

    def _describe_return(value: ast.expr | None) -> str:
        if value is None:
            return "None (explicit)"
        if isinstance(value, ast.Constant):
            return f"literal: {repr(value.value)}"
        if isinstance(value, ast.Name):
            return f"variable: {value.id}"
        if isinstance(value, ast.Tuple):
            parts = [_describe_return(e) for e in value.elts[:3]]
            return "tuple: (" + ", ".join(parts) + (")" if len(value.elts) <= 3 else ", ...)")
        if isinstance(value, ast.Dict):
            return "dict literal"
        if isinstance(value, ast.List):
            return "list literal"
        if isinstance(value, ast.Call):
            if isinstance(value.func, ast.Name):
                return f"call: {value.func.id}(...)"
            if isinstance(value.func, ast.Attribute):
                prefix = ""
                if isinstance(value.func.value, ast.Name):
                    prefix = value.func.value.id + "."
                return f"call: {prefix}{value.func.attr}(...)"
            return "call expression"
        if isinstance(value, ast.Attribute):
            if isinstance(value.value, ast.Name):
                return f"attribute: {value.value.id}.{value.attr}"
        if isinstance(value, ast.IfExp):
            return "conditional expression"
        return "expression"

    # Walk only the direct body of the function (don't descend into nested functions)
    def _walk_body(stmts):
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue  # skip nested
            if isinstance(stmt, ast.Return):
                desc = _describe_return(stmt.value)
                if desc not in seen:
                    seen.add(desc)
                    returns.append(desc)
            # recurse into branches
            for child_list in [
                getattr(stmt, "body", []),
                getattr(stmt, "orelse", []),
                getattr(stmt, "finalbody", []),
            ]:
                if isinstance(child_list, list):
                    _walk_body(child_list)
            for handler in getattr(stmt, "handlers", []):
                _walk_body(getattr(handler, "body", []))

    _walk_body(func.body)

    # Implicit None
    if not returns:
        returns.append("None (implicit)")
    elif len(returns) > 1:
        returns.append("multiple return branches")

    return returns


def _param_usage_python(source: str, params: tuple[str, ...], start_line: int = 1) -> dict[str, list[str]]:
    """
    For each parameter, return a list of usage facts deterministically derived from AST.

    Facts have the form:
        "read at line N"
        "passed to call_name(...)"
        "used in arithmetic at line N"
        "used in comparison at line N"
        "subscripted at line N"
        "attribute access: param.attr at line N"
    """
    usage: dict[str, list[str]] = {p: [] for p in params}
    if not params:
        return usage

    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return usage

    param_set = set(params)
    line_offset = start_line - 1  # AST lines are 1-based from dedented source

    for node in ast.walk(tree):
        # Skip nested function defs
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pass  # we still walk inside — we just want to label them

        # Detect parameter reads inside Call arguments
        if isinstance(node, ast.Call):
            call_name = ""
            if isinstance(node.func, ast.Name):
                call_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    call_name = node.func.value.id + "." + node.func.attr
                else:
                    call_name = node.func.attr
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if isinstance(arg, ast.Name) and arg.id in param_set:
                    fact = f"passed to {call_name}(...)"
                    if fact not in usage[arg.id]:
                        usage[arg.id].append(fact)

        # Arithmetic usage
        if isinstance(node, ast.BinOp):
            for side in (node.left, node.right):
                if isinstance(side, ast.Name) and side.id in param_set:
                    line = getattr(side, "lineno", None)
                    label = f"used in arithmetic"
                    if line:
                        label += f" at line {line + line_offset}"
                    if label not in usage[side.id]:
                        usage[side.id].append(label)

        # Comparison usage
        if isinstance(node, ast.Compare):
            if isinstance(node.left, ast.Name) and node.left.id in param_set:
                line = getattr(node.left, "lineno", None)
                label = f"used in comparison"
                if line:
                    label += f" at line {line + line_offset}"
                if label not in usage[node.left.id]:
                    usage[node.left.id].append(label)

        # Subscript
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id in param_set:
                line = getattr(node.value, "lineno", None)
                label = "subscripted"
                if line:
                    label += f" at line {line + line_offset}"
                if label not in usage[node.value.id]:
                    usage[node.value.id].append(label)

        # Attribute access
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in param_set:
                line = getattr(node.value, "lineno", None)
                label = f"attribute access: {node.value.id}.{node.attr}"
                if line:
                    label += f" at line {line + line_offset}"
                if label not in usage[node.value.id]:
                    usage[node.value.id].append(label)

    # Add "read at line N" for any param referenced with ast.Name Load that isn't covered above
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in param_set:
            line = getattr(node, "lineno", None)
            if line:
                label = f"read at line {line + line_offset}"
                if not any(f"line {line + line_offset}" in f for f in usage[node.id]):
                    if len(usage[node.id]) < 6:  # cap to avoid noise
                        usage[node.id].append(label)

    return usage


def _local_symbol_table_python(source: str, start_line: int = 1) -> list[tuple[str, list[str]]]:
    """
    Build a compact symbol table for local variables inside a function.

    Returns a list of (name, [facts]) where facts are things like:
        "assigned at line N"
        "value from call: foo(...)"
        "used at line N"

    Only variables that are locally assigned AND used are included.
    Parameters are excluded (handled separately).
    Skips dunder names and private names starting with __.
    """
    try:
        tree = ast.parse(textwrap.dedent(source))
    except SyntaxError:
        return []

    func_nodes = [n for n in ast.walk(tree)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not func_nodes:
        return []
    func = func_nodes[0]

    param_names: set[str] = {
        a.arg for a in (
            list(func.args.posonlyargs)
            + list(func.args.args)
            + list(func.args.kwonlyargs)
            + ([func.args.vararg] if func.args.vararg else [])
            + ([func.args.kwarg] if func.args.kwarg else [])
        )
    }

    line_offset = start_line - 1
    assigns: dict[str, list[str]] = {}
    reads: dict[str, list[int]] = {}

    def _call_desc(node: ast.expr) -> str:
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return f"call: {node.func.id}(...)"
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    return f"call: {node.func.value.id}.{node.func.attr}(...)"
                return f"call: {node.func.attr}(...)"
        if isinstance(node, ast.Constant):
            return f"constant: {repr(node.value)}"
        if isinstance(node, ast.Name):
            return f"variable: {node.id}"
        return "expression"

    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            line = getattr(node, "lineno", None)
            for tgt in node.targets:
                for name in _target_names(tgt):
                    if name in param_names or name.startswith("__"):
                        continue
                    facts = assigns.setdefault(name, [])
                    label = "assigned"
                    if line:
                        label += f" at line {line + line_offset}"
                    value_desc = _call_desc(node.value)
                    label += f", value from {value_desc}"
                    if label not in facts:
                        facts.append(label)

        elif isinstance(node, ast.AnnAssign) and node.value:
            line = getattr(node, "lineno", None)
            for name in _target_names(node.target):
                if name in param_names or name.startswith("__"):
                    continue
                facts = assigns.setdefault(name, [])
                label = "assigned"
                if line:
                    label += f" at line {line + line_offset}"
                value_desc = _call_desc(node.value)
                label += f", value from {value_desc}"
                if label not in facts:
                    facts.append(label)

        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in param_names or node.id.startswith("__"):
                continue
            line = getattr(node, "lineno", None)
            if line:
                reads.setdefault(node.id, []).append(line + line_offset)

    # Build result: only symbols that have both an assignment AND at least one read
    result: list[tuple[str, list[str]]] = []
    for name, assign_facts in assigns.items():
        read_lines = reads.get(name, [])
        if not read_lines:
            continue  # assigned but never read — skip
        facts = list(assign_facts)
        # Add up to 3 read-line references
        for rl in sorted(set(read_lines))[:3]:
            facts.append(f"read at line {rl}")
        result.append((name, facts))

    return result


def _compact_class_summary(class_source: str, target_name: str) -> str:
    """
    Produce a compact summary of a containing class:
    - class signature
    - class-level attributes
    - field assignments from __init__ (brief)
    - signatures of all methods (not bodies), EXCEPT the target itself

    This avoids flooding the context budget with irrelevant method bodies.
    """
    if not class_source:
        return ""

    try:
        tree = ast.parse(textwrap.dedent(class_source))
    except SyntaxError:
        return class_source[:800] + "\n  ... (class body truncated)"

    class_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    if not class_nodes:
        return class_source[:800] + "\n  ... (class body truncated)"

    cls = class_nodes[0]
    lines: list[str] = []

    # Class header (decorators + class line)
    if cls.decorator_list:
        for dec in cls.decorator_list:
            lines.append(f"@{ast.unparse(dec)}")
    bases = ", ".join(ast.unparse(b) for b in cls.bases) if cls.bases else ""
    lines.append(f"class {cls.name}({bases}):" if bases else f"class {cls.name}:")

    # Class-level attributes
    for item in cls.body:
        if isinstance(item, (ast.Assign, ast.AnnAssign)):
            try:
                lines.append(f"    {ast.unparse(item)}")
            except Exception:
                pass

    # Collect field hints from __init__ (self.x = ...)
    init_fields: list[str] = []
    for method in cls.body:
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)) and method.name == "__init__":
            for stmt in method.body:
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name) and tgt.value.id == "self":
                            init_fields.append(f"  self.{tgt.attr}")
                elif isinstance(stmt, ast.AnnAssign):
                    if isinstance(stmt.target, ast.Attribute) and isinstance(stmt.target.value, ast.Name) and stmt.target.value.id == "self":
                        init_fields.append(f"  self.{stmt.target.attr}")
            break

    if init_fields:
        lines.append("  # Fields (from __init__):")
        lines.extend(init_fields[:8])  # cap at 8 fields
        if len(init_fields) > 8:
            lines.append(f"  # ... {len(init_fields) - 8} more fields")

    # Method signatures (exclude target)
    method_sigs: list[str] = []
    for method in cls.body:
        if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if method.name == target_name:
                continue  # skip the target itself
            try:
                sig = ast.unparse(method.args)
                async_prefix = "async " if isinstance(method, ast.AsyncFunctionDef) else ""
                dec_str = ""
                if method.decorator_list:
                    decs = ", ".join(f"@{ast.unparse(d)}" for d in method.decorator_list[:2])
                    dec_str = f"  {decs}\n"
                method_sigs.append(f"{dec_str}  {async_prefix}def {method.name}({sig}): ...")
            except Exception:
                method_sigs.append(f"  def {method.name}(...): ...")
        elif isinstance(method, ast.ClassVar if hasattr(ast, 'ClassVar') else type(None)):
            pass

    if method_sigs:
        lines.append("  # Methods:")
        lines.extend(method_sigs[:12])  # cap at 12 method signatures
        if len(method_sigs) > 12:
            lines.append(f"  # ... {len(method_sigs) - 12} more methods")

    return "\n".join(lines)


def _resolve_cross_file_callee(
    called_name: str,
    target_imports: tuple[str, ...],
    repo_root: str | None,
) -> tuple[str | None, str | None, str | None]:
    """
    Try to resolve a called name to a local project function definition.

    Heuristic:
    1. Scan import statements for `called_name` or a module that exports it.
    2. Map the module to a file path under repo_root.
    3. Parse that file, find the function, return (file_path, qualified_name, source).

    Returns:
        (file_relative_path, qualified_name, source) if resolved
        (None, None, None)                           if not resolved
    """
    if not repo_root or not called_name:
        return None, None, None

    repo_path = Path(repo_root)

    # Determine the unqualified name to look up
    # called_name may be "module.func" or just "func"
    parts = called_name.rsplit(".", 1)
    func_name = parts[-1]
    module_hint = parts[0] if len(parts) == 2 else None

    # Build candidate file paths from imports
    candidate_files: list[Path] = []

    for stmt in target_imports:
        try:
            node = ast.parse(stmt.strip(), mode="single").body[0]
        except (SyntaxError, IndexError):
            continue

        if isinstance(node, ast.ImportFrom):
            module = (node.module or "").replace(".", "/")
            names = [alias.name for alias in node.names]
            asnames = {alias.asname or alias.name: alias.name for alias in node.names}

            # Direct: from module import func_name
            if func_name in names or func_name in asnames:
                for suffix in (".py", "/__init__.py"):
                    candidate = repo_path / (module + suffix)
                    if candidate.exists():
                        candidate_files.append(candidate)

            # Submodule imported: from services import expense_service
            for name in names:
                sub = (module + "/" + name).replace("//", "/").strip("/")
                for suffix in (".py", "/__init__.py"):
                    candidate = repo_path / (sub + suffix)
                    if candidate.exists():
                        candidate_files.append(candidate)

            # Dotted module file: from services.expense_service import ...
            if module:
                for suffix in (".py", "/__init__.py"):
                    candidate = repo_path / (module + suffix)
                    if candidate.exists():
                        candidate_files.append(candidate)

        elif isinstance(node, ast.Import):
            for alias in node.names:
                mod_path = alias.name.replace(".", "/")
                for suffix in (".py", "/__init__.py"):
                    candidate = repo_path / (mod_path + suffix)
                    if candidate.exists():
                        candidate_files.append(candidate)

    # Search each candidate file for the function
    seen_files: set[Path] = set()
    for fpath in candidate_files:
        resolved = fpath.resolve()
        if resolved in seen_files:
            continue
        seen_files.add(resolved)
        try:
            src = fpath.read_text(encoding="utf-8", errors="replace")
            ftree = ast.parse(src)
            lines = src.splitlines()
            for fn_node in ast.walk(ftree):
                if isinstance(fn_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if fn_node.name == func_name:
                        fn_src = "\n".join(lines[fn_node.lineno - 1 : fn_node.end_lineno])
                        rel = str(fpath.relative_to(repo_path)).replace("\\", "/")
                        qname = fn_node.name
                        for parent in ast.walk(ftree):
                            if isinstance(parent, ast.ClassDef):
                                if any(
                                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                                    and child.name == fn_node.name
                                    for child in parent.body
                                ):
                                    qname = f"{parent.name}.{fn_node.name}"
                        return rel, qname, fn_src
        except Exception:
            continue

    return None, None, None


# =============================================================================
# Component 3 — Context construction
# =============================================================================
# =============================================================================
# Component 3 — Context construction
# =============================================================================

def build_context(
    target: ExtractedFunction,
    all_functions: Iterable[ExtractedFunction],
    config: SemanticReviewConfig | None = None,
    repo_root: str | None = None,
) -> ContextPackage:
    """
    Build bounded, priority-ordered, evidence-first local context for the LLM.

    Priority order (highest → lowest):
        1. Complete target function (never truncated)
        2. Direct local callees (same file, actually called by target)
        3. Direct local callers (same file, actually call the target)
        4. Cross-file project callees (resolved from imports)
        5. Module-level symbols directly referenced by target
        6. Containing class summary (compact — only fields + method signatures)
        7. Classified imports
        8. Return-value flow summary
        9. Parameter usage summary
        10. Local symbol table

    Backward-compatible: new repo_root param defaults to None.
    Existing ContextPackage fields (text, included, truncated) are unchanged.
    New optional ContextPackage fields: omitted, unresolved_symbols, cross_file_resolved.
    """

    config = config or SemanticReviewConfig()

    budget = config.max_context_chars
    sections: list[str] = []
    included: list[str] = []
    omitted: list[str] = []
    unresolved_symbols: list[str] = []
    cross_file_resolved: list[str] = []
    truncated = False

    def _remaining() -> int:
        used = sum(len(s) + 2 for s in sections)
        return budget - used

    def _add(section_text: str, label: str) -> bool:
        """Attempt to add a section. Returns True if added."""
        needed = len(section_text) + 2
        if _remaining() >= needed:
            sections.append(section_text)
            included.append(label)
            return True
        return False

    # =========================================================================
    # PRIORITY 1: Target function (NEVER truncated)
    # =========================================================================

    target_header = (
        f"TARGET FUNCTION "
        f"{target.qualified_name} "
        f"({target.file_path}:"
        f"{target.start_line}-"
        f"{target.end_line})"
    )
    target_block = target_header + "\n" + target.source
    sections.append(target_block)
    included.append("target_function")

    # =========================================================================
    # PRIORITY 2: Direct local callees (same file, directly called)
    # =========================================================================

    added_callees: set[str] = set()

    if config.max_context_depth >= 1:
        local_functions: dict[str, ExtractedFunction] = {}
        for fn in all_functions:
            if (
                fn.file_path == target.file_path
                and fn.qualified_name != target.qualified_name
            ):
                if (
                    fn.name not in local_functions
                    or (target.class_name and fn.class_name == target.class_name)
                ):
                    local_functions[fn.name] = fn
                local_functions[fn.qualified_name] = fn

        for called_name in target.called_names:
            dep = local_functions.get(called_name)
            if dep is None:
                continue
            if dep.qualified_name in added_callees:
                continue

            sig_params = ", ".join(dep.parameters) if dep.parameters else ""
            async_pfx = "async " if dep.is_async else ""
            sig = f"{async_pfx}def {dep.name}({sig_params})"

            block = (
                f"DIRECT LOCAL CALLEE\n"
                f"Name: {dep.qualified_name}\n"
                f"File: {dep.file_path}\n"
                f"Lines: {dep.start_line}-{dep.end_line}\n"
                f"\nSource:\n{dep.source}"
            )

            if _add(block, f"direct_callee:{dep.qualified_name}"):
                added_callees.add(dep.qualified_name)
            else:
                omitted.append(f"direct_callee:{dep.qualified_name} (budget)")
                truncated = True

    # =========================================================================
    # PRIORITY 3: Direct local callers (same file)
    # =========================================================================

    if config.max_context_depth >= 1:
        added_callers: set[str] = set()
        local_callers = sorted(
            [
                fn
                for fn in all_functions
                if (
                    fn.file_path == target.file_path
                    and fn.qualified_name != target.qualified_name
                    and fn.qualified_name not in added_callees
                    and (
                        target.name in fn.called_names
                        or target.qualified_name in fn.called_names
                    )
                )
            ],
            key=lambda fn: (fn.start_line, fn.qualified_name.lower()),
        )

        for caller in local_callers:
            if caller.qualified_name in added_callers:
                continue

            # Caller contract evidence: how does the caller use the return value?
            caller_contract: list[str] = []
            if target.language == "python":
                try:
                    caller_tree = ast.parse(textwrap.dedent(caller.source))
                    target_call_names = {target.name, target.qualified_name}
                    for node in ast.walk(caller_tree):
                        if isinstance(node, ast.Assign):
                            if isinstance(node.value, ast.Call):
                                fn_node = node.value.func
                                call_name = ""
                                if isinstance(fn_node, ast.Name):
                                    call_name = fn_node.id
                                elif isinstance(fn_node, ast.Attribute):
                                    call_name = fn_node.attr
                                if call_name in target_call_names or target.name in call_name:
                                    for tgt_node in node.targets:
                                        for tgt_name in _target_names(tgt_node):
                                            caller_contract.append(f"return value assigned to `{tgt_name}`")
                                            # Check how tgt_name is used later
                                            for sub in ast.walk(caller_tree):
                                                if isinstance(sub, ast.Subscript):
                                                    if isinstance(sub.value, ast.Name) and sub.value.id == tgt_name:
                                                        try:
                                                            key = ast.unparse(sub.slice)
                                                            caller_contract.append(f"caller accesses `{tgt_name}[{key}]`")
                                                        except Exception:
                                                            pass
                                                elif isinstance(sub, ast.Attribute):
                                                    if isinstance(sub.value, ast.Name) and sub.value.id == tgt_name:
                                                        caller_contract.append(f"caller accesses `{tgt_name}.{sub.attr}`")
                except Exception:
                    pass

            contract_str = ""
            if caller_contract:
                contract_str = "\nCALLER CONTRACT EVIDENCE:\n" + "\n".join(
                    f"- {c}" for c in caller_contract[:5]
                )

            block = (
                f"DIRECT LOCAL CALLER\n"
                f"Name: {caller.qualified_name}\n"
                f"File: {caller.file_path}\n"
                f"Lines: {caller.start_line}-{caller.end_line}\n"
                f"\nSource:\n{caller.source}"
                f"{contract_str}"
            )

            if _add(block, f"direct_caller:{caller.qualified_name}"):
                added_callers.add(caller.qualified_name)
            else:
                omitted.append(f"direct_caller:{caller.qualified_name} (budget)")
                truncated = True

    # =========================================================================
    # PRIORITY 4: Cross-file local project callee resolution
    # =========================================================================

    # Only attempt for Python (deterministic AST-based resolution)
    if target.language == "python" and repo_root and config.max_context_depth >= 1:
        for called_name in target.called_names:
            # Skip if already covered by same-file callees
            if any(called_name in lbl for lbl in included if lbl.startswith("direct_callee:")):
                continue
            # Only try dotted names (module.func pattern)
            if "." not in called_name and called_name not in {
                n.split(".")[-1] for n in (target.called_names or ())
            }:
                pass  # try anyway for plain names referenced via imports

            rel, qname, fn_src = _resolve_cross_file_callee(
                called_name, target.imports, repo_root
            )

            if rel and fn_src:
                block = (
                    f"CROSS-FILE LOCAL CALLEE\n"
                    f"Symbol: {called_name}\n"
                    f"Resolved to: {qname}\n"
                    f"File: {rel}\n"
                    f"\nSource:\n{fn_src}"
                )
                if _add(block, f"cross_file_callee:{called_name}"):
                    cross_file_resolved.append(f"{called_name} -> {rel}:{qname}")
                else:
                    omitted.append(f"cross_file_callee:{called_name} (budget)")
                    truncated = True
            else:
                # Mark as unresolved so the prompt can instruct the model correctly
                unresolved_symbols.append(called_name)

    # =========================================================================
    # PRIORITY 5: Module-level definitions used by target
    # =========================================================================

    skipped_module_def = False
    for kind, def_name, def_source in target.module_definitions:
        block = (
            f"MODULE-LEVEL SYMBOL USED BY TARGET\n"
            f"Name: {def_name}\n"
            f"Type: {kind}\n"
            f"\nSource:\n{def_source}"
        )
        if not _add(block, f"module_def:{def_name}"):
            skipped_module_def = True
            omitted.append(f"module_def:{def_name} (budget)")
            truncated = True

    # =========================================================================
    # PRIORITY 6: Containing class — compact summary only
    # =========================================================================

    if target.class_source:
        compact_cls = _compact_class_summary(target.class_source, target.name)
        block = f"CONTAINING CLASS\n{compact_cls}"
        if not _add(block, "containing_class"):
            omitted.append("containing_class (budget)")
            truncated = True

    # =========================================================================
    # PRIORITY 7: Classified imports
    # =========================================================================

    if target.imports and target.language == "python":
        classified = _classify_imports_python(target.imports, repo_root)
        import_lines: list[str] = ["RELEVANT IMPORTS"]

        if classified["stdlib"]:
            import_lines.append("STANDARD LIBRARY:")
            import_lines.extend(f"  {s}" for s in classified["stdlib"])

        if classified["local"]:
            import_lines.append("LOCAL PROJECT:")
            import_lines.extend(f"  {s}" for s in classified["local"])

        if classified["third_party"]:
            import_lines.append("THIRD PARTY (external - behavior not available in repository):")
            import_lines.extend(f"  {s}" for s in classified["third_party"])

        if classified["unknown"]:
            import_lines.append("UNKNOWN:")
            import_lines.extend(f"  {s}" for s in classified["unknown"])

        # Mark unresolved symbols that came from local imports
        for sym in list(unresolved_symbols):
            import_lines.append(f"UNRESOLVED LOCAL SYMBOL: {sym} (source not found in project)")

        block = "\n".join(import_lines)
        if not _add(block, "imports"):
            # Fall back to plain import list if classified version doesn't fit
            plain = "RELEVANT IMPORTS\n" + "\n".join(target.imports)
            if not _add(plain, "imports"):
                omitted.append("imports (budget)")
    elif target.imports:
        plain = "RELEVANT IMPORTS\n" + "\n".join(target.imports)
        if not _add(plain, "imports"):
            omitted.append("imports (budget)")

    # =========================================================================
    # PRIORITY 8: Return-value flow (Python only)
    # =========================================================================

    if target.language == "python" and _remaining() > 200:
        ret_flows = _return_flow_python(target.source)
        if ret_flows:
            block = "TARGET RETURN FLOW\nReturns:\n" + "\n".join(
                f"- {r}" for r in ret_flows
            )
            _add(block, "return_flow")

    # =========================================================================
    # PRIORITY 9: Parameter usage (Python only)
    # =========================================================================

    if target.language == "python" and target.parameters and _remaining() > 300:
        param_usage = _param_usage_python(target.source, target.parameters, target.start_line)
        usage_lines: list[str] = ["PARAMETER USAGE"]
        for param in target.parameters:
            facts = param_usage.get(param, [])
            if facts:
                usage_lines.append(f"`{param}`")
                usage_lines.extend(f"  - {f}" for f in facts[:5])
        if len(usage_lines) > 1:
            block = "\n".join(usage_lines)
            _add(block, "param_usage")

    # =========================================================================
    # PRIORITY 10: Local symbol table (Python only)
    # =========================================================================

    if target.language == "python" and _remaining() > 300:
        sym_table = _local_symbol_table_python(target.source, target.start_line)
        if sym_table:
            sym_lines: list[str] = ["LOCAL SYMBOLS"]
            for sym_name, facts in sym_table[:8]:  # cap at 8 symbols
                sym_lines.append(f"`{sym_name}`")
                sym_lines.extend(f"  - {f}" for f in facts[:4])
            block = "\n".join(sym_lines)
            _add(block, "local_symbols")

    # =========================================================================
    # Context limit notice
    # =========================================================================

    if omitted:
        notice_parts = ["CONTEXT LIMIT NOTICE: The following lower-priority context was omitted:"]
        notice_parts.extend(f"- {item}" for item in omitted[:10])
        notice = "\n".join(notice_parts)
        _add(notice, "context_limit_notice")

    return ContextPackage(
        text="\n\n".join(sections),
        included=tuple(included),
        truncated=truncated or skipped_module_def,
        omitted=tuple(omitted),
        unresolved_symbols=tuple(unresolved_symbols),
        cross_file_resolved=tuple(cross_file_resolved),
    )


def _format_language_name(language: str) -> str:
    """Format language identifier into canonical display name."""
    mapping = {
        "python": "Python",
        "javascript": "JavaScript",
        "java": "Java",
    }
    return mapping.get(language.lower(), language.capitalize())


def _build_compact_prompt(
    target: ExtractedFunction,
    context: ContextPackage,
) -> str:
    """
    Component 4: Compact prompt for smaller local models (SEMANTIC_PROMPT_MODE=compact).

    Supports Python, JavaScript, and Java.
    - Explicit LANGUAGE declaration
    - Target identification (file, language, function, qualified name, line range, parameters, async, decorators)
    - Numbered target source code for exact line numbers
    - Context package from Component 3 preserved without duplicate target source
    - Full 10-step SEMANTIC REASONING PROCEDURE + A-K bug categories + SELF-CHECK
    - VERY IMPORTANT DECISION RULE: no bug_found=false after describing a real defect
    - Language-specific & general semantic defect checklist
    - Strict JSON output format matching Component 6/7 expectations
    """
    lang_display = _format_language_name(target.language)

    numbered = "\n".join(
        f"{number}: {line}"
        for number, line in enumerate(
            target.source.splitlines(),
            start=target.start_line,
        )
    )

    # Build context block that excludes the target function body to avoid duplication.
    # Strategy: locate the TARGET FUNCTION header in context.text, then skip past it and
    # the target source to obtain the remaining context sections.
    target_header = (
        f"TARGET FUNCTION "
        f"{target.qualified_name} "
        f"({target.file_path}:"
        f"{target.start_line}-"
        f"{target.end_line})"
    )
    header_idx = context.text.find(target_header)
    if header_idx >= 0:
        after_header = context.text[header_idx + len(target_header):]
        src_idx = after_header.find(target.source)
        if src_idx >= 0:
            other = after_header[src_idx + len(target.source):].strip()
        else:
            other = after_header.strip()
    else:
        # Fallback: strip first occurrence of the raw source text
        idx = context.text.find(target.source)
        if idx >= 0:
            other = context.text[idx + len(target.source):].strip()
        else:
            other = context.text.strip()

    decorators = (
        "\n".join("@" + d if not d.startswith("@") else d for d in target.decorators)
        if target.decorators
        else "(none)"
    )

    params_str = ", ".join(target.parameters) if target.parameters else "(none)"

    other_block = (
        f"""
CONTEXT FROM THE SAME FILE (module definitions, imports, class, direct callees/callers):
{other}
"""
        if other
        else ""
    )

    # Language-specific semantic bug checklist
    lang_lower = target.language.lower()
    if lang_lower == "python":
        lang_checklist = (
            "- Mutable default arguments (e.g. def fn(val=[]) or val={}) mutated or returned\n"
            "- Missing await on coroutine/async calls causing unawaited coroutine objects\n"
            "- Unhandled None attribute or subscript access without prior check\n"
            "- Dict key or list index access without boundary/membership check\n"
            "- Bare except or exception handler that swallows errors and leaves broken state"
        )
    elif lang_lower == "javascript":
        lang_checklist = (
            "- Missing await on Promise (floating promise, returning raw Promise instead of resolved value)\n"
            "- Loose equality (== or !=) causing unexpected type coercion pitfalls instead of strict (=== / !==)\n"
            "- Property access on null or undefined without optional chaining or guard\n"
            "- Incorrect 'this' context binding in callbacks, event handlers, or arrow functions\n"
            "- Array mutating methods (e.g. sort, reverse, splice) modifying shared state unexpectedly\n"
            "- Callback / Promise chaining resolution order or unhandled rejection"
        )
    elif lang_lower == "java":
        lang_checklist = (
            "- Object identity comparison (== or !=) instead of .equals() for Strings, Longs, or Objects\n"
            "- NullPointerException on method calls or auto-unboxing of null wrappers (Integer, Long, Boolean)\n"
            "- Off-by-one errors in loop conditions or collection/array index boundaries\n"
            "- Unclosed AutoCloseable resources (streams, connections) not using try-with-resources\n"
            "- Contract mismatches between caller expectations and method return values"
        )
    else:
        lang_checklist = (
            "- Incorrect return-value usage, missing null checks, contract mismatches, or resource lifecycle leaks"
        )

    return f"""You are a careful {lang_display} code reviewer. Decide if ONE function contains a real semantic bug.

LANGUAGE: {lang_display}
FILE: {target.file_path}
FUNCTION: {target.name}
QUALIFIED NAME: {target.qualified_name}
LINES: {target.start_line}-{target.end_line}
PARAMETERS: {params_str}
ASYNC: {target.is_async}
DECORATORS/ANNOTATIONS:
{decorators}

TARGET FUNCTION SOURCE (each line starts with its 1-indexed line number and colon; the number is NOT part of the code):
{numbered}
{other_block}
SEMANTIC REASONING PROCEDURE — perform all steps internally before producing JSON:

STEP 1: State in one sentence what this function should accomplish.
STEP 2: Identify the key inputs and the expected output.
STEP 3: Trace the most important value from input to transformation to output.
STEP 4: Inspect every condition (if/else, comparisons, operators). Are they reversed or checking the wrong variable?
STEP 5: Inspect arithmetic and aggregation. Wrong operand, sign, formula, or accumulation?
STEP 6: Inspect state mutations. Is the wrong object mutated? Mutation done at wrong time?
STEP 7: Inspect loops and collections. Which elements actually reach the result? Off-by-one? Wrong filter?
STEP 8: Inspect exception/early-return paths. Is broken state silently returned as success?
STEP 9: Inspect the return value. Is the computed value actually returned, or a stale/wrong variable?
STEP 10: Ask "Can I give a concrete input or execution path that produces incorrect behavior?"
  YES: report the strongest concrete bug (bug_found=true, confidence >= 0.70).
  NO:  bug_found=false.

SEMANTIC BUG CATEGORIES — check each one:
A. WRONG CONDITIONS: inverted comparison (> vs <), wrong variable in condition, unreachable valid branch
B. WRONG ARITHMETIC: wrong operand/variable/sign, incorrect formula, off-by-one, accumulating wrong values
C. WRONG DATA FLOW: stale value used, variable overwritten too early, calculated value ignored, wrong variable returned
D. COLLECTION BUGS: wrong filtering, off-by-one indexing, wrong first/last element, skipped elements
E. RETURN-VALUE BUGS: computed result ignored, wrong variable returned, inconsistent type/value across branches
F. EXCEPTION/ERROR FLOW: exception swallowed and success returned, invalid value used after exception
G. MUTABLE DEFAULT ARGUMENTS: mutable default mutated and persisted across calls (Python)
H. ASYNC BUGS: coroutine created but never awaited, async result treated as final value
I. STATE/MUTATION BUGS: object modified too early, shared state changed unexpectedly, update on wrong branch
J. VALIDATION/BUSINESS LOGIC: explicit contradiction between validation and calculation in the supplied code
K. RESOURCE LIFECYCLE: resource created but not released, cleanup skipped on a demonstrated path
{lang_checklist}

VERY IMPORTANT DECISION RULE:
If your reasoning identifies a CONCRETE mismatch between expected and actual behavior caused by a specific
statement, then bug_found MUST be true. Do NOT describe a real defect in reasoning and then output bug_found=false.

NOT A BUG (answer bug_found=false):
- Code that already guards the case (if/else, null/None checks, try-catch/except)
- Style: formatting, naming, indentation, missing docstrings, general code quality
- Hypothetical requirements not visible in the code; never invent fields, functions, or application requirements
- Normal framework/library idioms and dependency injection
- Returning bug_found=false is perfectly acceptable. Never manufacture a bug because the function looks unusual.

SELF-CHECK (only when considering bug_found=true):
[ ] Concrete behavioral defect with a specific execution path identified.
[ ] Defect is visible in the supplied code, not invented.
[ ] relevant_code is copied exactly from the TARGET FUNCTION source above (no line numbers).
[ ] file equals "{target.file_path}".
[ ] start_line and end_line are within {target.start_line}-{target.end_line}.
[ ] expected_behavior differs from actual_behavior.
[ ] confidence >= 0.70 with real evidence.
If ANY item fails, set bug_found=false.

REPLY WITH EXACTLY ONE JSON OBJECT AND NOTHING ELSE (no markdown fences, no code blocks, no text before or after).
Use exactly these keys:
{{
  "reasoning": "2-3 sentences: what the function should do, what it actually does for a concrete test input, and your verdict.",
  "bug_found": true or false,
  "confidence": number from 0.0 to 1.0 (0.0 if no bug, >= 0.70 required for bug_found=true),
  "bug_type": "short category name, or null if no bug",
  "title": "short concrete title, or null if no bug",
  "description": "precise explanation of the defect, or null if no bug",
  "file": "{target.file_path}",
  "buggy_line": the line number shown before the buggy line (between {target.start_line} and {target.end_line}), or null if no bug,
  "start_line": the line number shown before the first buggy line (between {target.start_line} and {target.end_line}), or 0 if no bug,
  "end_line": the line number shown before the last buggy line (between {target.start_line} and {target.end_line}), or 0 if no bug,
  "evidence": "the ONE buggy line copied exactly from the TARGET FUNCTION without line number, or null if no bug",
  "relevant_code": "the same ONE buggy line copied exactly from the TARGET FUNCTION without line number, or null if no bug",
  "expected_behavior": "what should happen, or null if no bug",
  "actual_behavior": "what happens instead, or null if no bug",
  "suggested_fix": "short description of the correction, or null if no bug"
}}""".strip()



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

    lang_display = _format_language_name(target.language)
    return f"""
LANGUAGE: {lang_display}

You are a precise semantic bug detector for {lang_display} source code.

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
# Component 5 — LLM invocation
# =============================================================================

def invoke_llm(
    prompt: str,
    provider: Any | None = None,
    target: ExtractedFunction | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Component 5: Invoke the configured LLM provider with the prompt from Component 4.

    Responsibilities:
    - Receive prompt from Component 4 and invoke configured LLM provider.
    - Support existing Ollama, Gemini, Groq, OpenAI, and OmniRoute setups.
    - Preserve all provider configuration (model, endpoint, timeout, temperature, env vars).
    - Perform exactly ONE LLM invocation per review request.
    - Catch provider errors, timeouts, connection failures, and empty responses safely.
    - Preserve raw LLM response long enough for Component 6 to parse.
    - Perform NO response parsing (preserves strict component separation).
    - Provide lightweight logging without leaking sensitive source code.

    Returns:
        dict with:
            "response": str (raw LLM output, or empty string on error)
            "error": str | None (error message if failed, else None)
            "meta": dict (optional metadata from provider)
    """
    target_info = (
        f"{target.qualified_name} ({target.language})"
        if target
        else "unknown target"
    )

    if not isinstance(prompt, str) or not prompt.strip():
        logger.warning("Component 5: Empty prompt for %s", target_info)
        return {
            "response": "",
            "error": "Prompt is empty.",
        }

    # Use supplied provider or initialize from existing configuration
    if provider is None:
        try:
            from app.services.llm_logic_reviewer.llm_provider import create_llm_provider
            provider = create_llm_provider()
        except Exception as exc:
            err_msg = f"Failed to initialize LLM provider: {exc}"
            logger.error("Component 5: %s for %s", err_msg, target_info)
            return {
                "response": "",
                "error": err_msg,
            }

    provider_name = type(provider).__name__
    model_name = getattr(provider, "model", getattr(provider, "primary_model", "configured model"))

    logger.info(
        "Component 5: Invoking %s (%s) for %s [chars=%d]",
        provider_name,
        model_name,
        target_info,
        len(prompt),
    )

    try:
        result = provider.generate(prompt, **kwargs)
    except Exception as exc:
        err_msg = f"LLM provider {provider_name} raised an exception: {exc}"
        logger.warning("Component 5: %s for %s", err_msg, target_info)
        return {
            "response": "",
            "error": err_msg,
        }

    if not isinstance(result, dict):
        err_msg = f"LLM provider {provider_name} returned non-dict result: {type(result)}"
        logger.warning("Component 5: %s for %s", err_msg, target_info)
        return {
            "response": "",
            "error": err_msg,
        }

    raw_response = result.get("response", "")
    error = result.get("error")

    if not isinstance(raw_response, str):
        raw_response = str(raw_response or "")

    if error and not raw_response.strip():
        logger.warning(
            "Component 5: Provider %s reported error for %s: %s",
            provider_name,
            target_info,
            error,
        )
        return {
            "response": "",
            "error": str(error),
            "meta": result.get("meta", {}),
        }

    if not raw_response.strip():
        err_msg = f"LLM provider {provider_name} returned an empty response."
        logger.warning("Component 5: %s for %s", err_msg, target_info)
        return {
            "response": "",
            "error": err_msg,
            "meta": result.get("meta", {}),
        }

    logger.info(
        "Component 5: Successfully received %d chars from %s for %s",
        len(raw_response),
        provider_name,
        target_info,
    )

    return {
        "response": raw_response,
        "error": error,
        "meta": result.get("meta", {}),
    }


async def invoke_llm_async(
    prompt: str,
    provider: Any | None = None,
    target: ExtractedFunction | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Async-compatible wrapper for invoke_llm running in a worker thread."""
    import asyncio
    return await asyncio.to_thread(
        invoke_llm,
        prompt,
        provider=provider,
        target=target,
        **kwargs,
    )


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