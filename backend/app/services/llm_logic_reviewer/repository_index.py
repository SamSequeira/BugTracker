"""
Repository Intelligence Index for BugTracker Semantic LLM Detector.

Constructs an in-memory, scan-scoped index of:
- Files, modules, and classified roles
- Functions, signatures, docstrings, calls, line ranges, and rich semantic records:
  * parameters and parameter usage
  * local variables and constants
  * return expressions and return paths
  * called functions and calling functions
  * imported symbols and unresolved imports
  * attribute accesses
  * object construction
  * exceptions raised/caught
  * conditions (if tests)
  * loops
  * database/model references
  * API route references
  * external service calls
  * decorators
- Classes, inheritance, methods, and attributes
- Bidirectional call graph (Caller <-> Callee) with import-aware disambiguation
- Imports and dependency mappings
- Repository-level summary (architecture, frameworks, key domains)

Designed to be lightweight, fast, cached, deterministic, and degrading gracefully.
"""

import ast
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field

from app.services.llm_logic_reviewer.semantic_facts import classify_file_role

logger = logging.getLogger(__name__)

EXCLUDED_DIRS = {
    ".venv", "venv", "__pycache__", "node_modules", ".git",
    "migrations", "alembic", ".pytest_cache", "site-packages",
    "dist", "build", ".next", ".cache"
}

# Known database/ORM indicators
DB_BASE_INDICATORS = {"base", "model", "declarative_base", "document", "entity", "schema"}
DB_CALL_INDICATORS = {"filter", "filter_by", "query", "session", "execute", "commit", "save", "delete", "first", "all", "get", "add"}
API_DECORATOR_INDICATORS = {"get", "post", "put", "delete", "patch", "route", "api_view"}
EXTERNAL_SERVICE_INDICATORS = {"requests", "httpx", "aiohttp", "api", "client", "stripe", "boto3", "smtp"}


@dataclass
class FunctionIndexEntry:
    name: str
    qualname: str
    file_path: str
    module_name: str
    class_name: Optional[str]
    parameters: List[str]
    parameter_usage: Dict[str, List[str]] = field(default_factory=dict)
    local_variables: List[str] = field(default_factory=list)
    returns: List[str] = field(default_factory=list)
    return_count: int = 0
    docstring: str = ""
    code_snippet: str = ""
    start_line: int = 1
    end_line: int = 1
    called_functions: List[str] = field(default_factory=list)
    is_async: bool = False
    decorators: List[str] = field(default_factory=list)
    exceptions: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    loops: List[str] = field(default_factory=list)
    attribute_accesses: List[str] = field(default_factory=list)
    object_constructions: List[str] = field(default_factory=list)
    db_model_references: List[str] = field(default_factory=list)
    api_references: List[str] = field(default_factory=list)
    external_service_calls: List[str] = field(default_factory=list)
    imported_symbols: List[str] = field(default_factory=list)


@dataclass
class ClassIndexEntry:
    name: str
    file_path: str
    base_classes: List[str]
    methods: List[str]
    docstring: str
    attributes: List[str]
    is_model: bool = False
    start_line: int = 1
    end_line: int = 1


@dataclass
class FileIndexEntry:
    file_path: str
    module_name: str
    file_role: str
    imports: List[str]
    imported_names_map: Dict[str, str] = field(default_factory=dict)  # local_name -> module / full_qualname
    unresolved_imports: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)  # qualnames
    classes: List[str] = field(default_factory=list)    # class names
    constants: List[str] = field(default_factory=list)


@dataclass
class ModuleLevelStateEntry:
    """
    Represents a module-level mutable variable (e.g. ``summary_cache = {}``)
    that may be shared across multiple functions in the same file.

    This is the key data structure for detecting cache-staleness and
    shared-state invalidation bugs (BUG_B, BUG_D patterns).
    """
    name: str           # variable name, e.g. "summary_cache"
    file_path: str      # relative path to the file that owns it
    line: int           # line number of the module-level assignment
    init_value: str     # string repr of the RHS at definition time
    readers: List[str] = field(default_factory=list)   # qualnames that READ this var
    writers: List[str] = field(default_factory=list)   # qualnames that WRITE this var


@dataclass
class RepositorySummary:
    name: str
    frameworks: List[str]
    architecture_summary: str
    primary_domains: List[str]
    total_files: int
    total_functions: int


class RepositoryIndex:
    """In-memory index of repository code structure, semantic properties, and relationships."""

    def __init__(self, root_path: str, frameworks: Optional[List[str]] = None):
        self.root_path = Path(root_path).resolve()
        self.frameworks = frameworks or []
        
        # File path (relative) -> FileIndexEntry
        self.files: Dict[str, FileIndexEntry] = {}
        
        # Function qualname / name -> List of FunctionIndexEntry
        self.functions_by_name: Dict[str, List[FunctionIndexEntry]] = {}
        self.functions_by_qualname: Dict[str, FunctionIndexEntry] = {}
        
        # Class name -> List of ClassIndexEntry
        self.classes_by_name: Dict[str, List[ClassIndexEntry]] = {}
        
        # Qualified call graph (keys = file_path::func_name to avoid cross-file collisions)
        # qualname -> set of qualnames it calls
        self.callees_of: Dict[str, Set[str]] = {}
        # qualname -> set of qualnames that call it
        self.callers_of: Dict[str, Set[str]] = {}

        # Legacy unqualified call graph (kept for backward compatibility)
        # function_name -> set of function names (may have collisions across files)
        self.callees_of_name: Dict[str, Set[str]] = {}
        self.callers_of_name: Dict[str, Set[str]] = {}
        
        # Module-level mutable state: file_path -> list of state entries
        # Used for cache-staleness and shared-state invalidation bug detection.
        self.module_level_state: Dict[str, List["ModuleLevelStateEntry"]] = {}
        
        # Project overview
        self.summary: Optional[RepositorySummary] = None

    def find_function(
        self,
        name: str,
        current_file: Optional[str] = None,
        enclosing_class: Optional[str] = None,
    ) -> Optional[FunctionIndexEntry]:
        """Find the best matching function definition with import & class disambiguation."""
        # 1. If method on a specific class (e.g. Class.method)
        if enclosing_class:
            qual = f"{enclosing_class}.{name}"
            if qual in self.functions_by_qualname:
                return self.functions_by_qualname[qual]

        entries = self.functions_by_name.get(name, [])
        if not entries:
            # Check if name is Class.method
            if "." in name:
                return self.functions_by_qualname.get(name)
            return None
        if len(entries) == 1:
            return entries[0]

        # 2. Check import-aware resolution if caller file is known
        if current_file:
            norm_curr = current_file.replace("\\", "/")
            f_entry = self.files.get(norm_curr)
            if f_entry and name in f_entry.imported_names_map:
                imported_source = f_entry.imported_names_map[name]
                # Match against entry file_path or module
                for e in entries:
                    if imported_source in e.file_path or imported_source == e.module_name:
                        return e

            # 3. Prefer function in the same file
            for e in entries:
                if e.file_path.replace("\\", "/") == norm_curr:
                    return e

        return entries[0]

    def find_callers(self, func_name: str) -> List[FunctionIndexEntry]:
        """Return function entries that directly call func_name (unqualified, backward compat)."""
        caller_names = self.callers_of_name.get(func_name) or self.callers_of.get(func_name, set())
        results = []
        for name in caller_names:
            fn = self.find_function(name) or self.functions_by_qualname.get(name)
            if fn and fn not in results:
                results.append(fn)
        return results

    def find_callees(self, func_name: str) -> List[FunctionIndexEntry]:
        """Return function entries that are directly called by func_name (unqualified, backward compat)."""
        callee_names = self.callees_of_name.get(func_name) or self.callees_of.get(func_name, set())
        results = []
        for name in callee_names:
            fn = self.find_function(name) or self.functions_by_qualname.get(name)
            if fn and fn not in results:
                results.append(fn)
        return results

    def find_callers_by_qualname(self, qualname: str) -> List[FunctionIndexEntry]:
        """Return function entries that call this qualified function name.
        
        Uses the qualified call graph (file_path::func_name) which avoids
        cross-file collisions when the same function name exists in multiple files.
        """
        caller_qualnames = self.callers_of.get(qualname, set())
        results = []
        for qn in caller_qualnames:
            fn = self.functions_by_qualname.get(qn)
            if fn:
                results.append(fn)
        return results

    def find_callees_by_qualname(self, qualname: str) -> List[FunctionIndexEntry]:
        """Return function entries called by this qualified function name."""
        callee_qualnames = self.callees_of.get(qualname, set())
        results = []
        for qn in callee_qualnames:
            fn = self.functions_by_qualname.get(qn)
            if fn:
                results.append(fn)
        return results

    def find_shared_state_readers(self, state_var_name: str, file_path: str = "") -> List[FunctionIndexEntry]:
        """Return functions that read a module-level state variable.
        
        Searches all files if file_path is empty, or just the given file otherwise.
        This is the primary mechanism for detecting stale-cache bugs.
        """
        results = []
        target_files = ([file_path] if file_path else list(self.module_level_state.keys()))
        for fp in target_files:
            for entry in self.module_level_state.get(fp, []):
                if entry.name == state_var_name:
                    for qn in entry.readers:
                        fn = self.functions_by_qualname.get(qn)
                        if fn:
                            results.append(fn)
        return results

    def find_shared_state_writers(self, state_var_name: str, file_path: str = "") -> List[FunctionIndexEntry]:
        """Return functions that write to a module-level state variable."""
        results = []
        target_files = ([file_path] if file_path else list(self.module_level_state.keys()))
        for fp in target_files:
            for entry in self.module_level_state.get(fp, []):
                if entry.name == state_var_name:
                    for qn in entry.writers:
                        fn = self.functions_by_qualname.get(qn)
                        if fn:
                            results.append(fn)
        return results

    def get_module_level_state(self, file_path: str) -> List["ModuleLevelStateEntry"]:
        """Get all module-level mutable state variables for a given file."""
        norm = file_path.replace("\\", "/")
        return self.module_level_state.get(norm, [])

    def find_class(self, class_name: str) -> Optional[ClassIndexEntry]:
        """Find a class definition by name."""
        entries = self.classes_by_name.get(class_name, [])
        return entries[0] if entries else None

    def find_constant(self, constant_name: str, file_path: Optional[str] = None) -> Optional[str]:
        """Find a constant definition by name, optionally scoped to a specific file."""
        if file_path:
            # Search in specific file
            norm_path = file_path.replace("\\", "/")
            file_entry = self.files.get(norm_path)
            if file_entry and constant_name in file_entry.constants:
                return file_entry.file_path
        else:
            # Search all files
            for file_entry in self.files.values():
                if constant_name in file_entry.constants:
                    return file_entry.file_path
        return None


def _safe_unparse(node: ast.AST) -> str:
    """Safely convert AST node to string across Python versions."""
    try:
        if hasattr(ast, "unparse"):
            return ast.unparse(node)
        return "<expr>"
    except Exception:
        return "<expr>"


def _extract_semantic_function_details(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    code_lines: List[str],
    file_path: str,
    module_name: str,
    class_name: Optional[str],
    file_imports: List[str],
) -> FunctionIndexEntry:
    """Extract comprehensive semantic properties of a function using AST."""
    func_name = node.name
    start_l = getattr(node, "lineno", 1)
    end_l = getattr(node, "end_lineno", start_l)
    snippet_lines = code_lines[start_l - 1: end_l]
    snippet = "\n".join(snippet_lines)

    params = [arg.arg for arg in node.args.args]
    doc = ast.get_docstring(node) or ""

    # Decorators
    decorators = []
    for d in node.decorator_list:
        decorators.append(_safe_unparse(d))

    # Parameter usage, local vars, calls, returns, conditions, exceptions
    param_usage: Dict[str, List[str]] = {p: [] for p in params}
    local_vars: Set[str] = set()
    called: List[str] = []
    returns: List[str] = []
    exceptions: List[str] = []
    conditions: List[str] = []
    loops: List[str] = []
    attribute_accesses: List[str] = []
    object_constructions: List[str] = []
    db_references: List[str] = []
    api_references: List[str] = []
    external_calls: List[str] = []

    # API route check from decorators
    for dec in decorators:
        dec_l = dec.lower()
        if any(api_k in dec_l for api_k in API_DECORATOR_INDICATORS):
            api_references.append(f"Route decorator: @{dec}")

    for sub in ast.walk(node):
        # Function Calls & Object construction
        if isinstance(sub, ast.Call):
            call_name = ""
            if isinstance(sub.func, ast.Name):
                call_name = sub.func.id
                called.append(call_name)
                # Object construction heuristic: PascalCase call
                if call_name and call_name[0].isupper() and "_" not in call_name:
                    object_constructions.append(call_name)
                    if any(db_k in call_name.lower() for db_k in ("model", "record", "entity", "user", "order", "item")):
                        db_references.append(f"Instantiates model: {call_name}")
            elif isinstance(sub.func, ast.Attribute):
                call_name = sub.func.attr
                called.append(call_name)
                # Check obj.method()
                if isinstance(sub.func.value, ast.Name):
                    caller_obj = sub.func.value.id
                    if caller_obj.lower() in EXTERNAL_SERVICE_INDICATORS or any(ext in caller_obj.lower() for ext in EXTERNAL_SERVICE_INDICATORS):
                        external_calls.append(f"{caller_obj}.{call_name}")
                    if call_name in DB_CALL_INDICATORS or any(db_w in caller_obj.lower() for db_w in ("db", "session", "repo", "query")):
                        db_references.append(f"{caller_obj}.{call_name}()")

        # Attribute accesses: obj.attr
        elif isinstance(sub, ast.Attribute):
            if isinstance(sub.value, ast.Name):
                attr_str = f"{sub.value.id}.{sub.attr}"
                attribute_accesses.append(attr_str)
                if sub.value.id in param_usage:
                    param_usage[sub.value.id].append(f"accessed .{sub.attr}")

        # Assignments (local variables)
        elif isinstance(sub, ast.Assign):
            for t in sub.targets:
                if isinstance(t, ast.Name) and t.id not in params:
                    local_vars.add(t.id)
                elif isinstance(t, ast.Tuple):
                    for el in t.elts:
                        if isinstance(el, ast.Name) and el.id not in params:
                            local_vars.add(el.id)

        # Returns
        elif isinstance(sub, ast.Return):
            if sub.value is not None:
                returns.append(_safe_unparse(sub.value))
            else:
                returns.append("None")

        # Conditions
        elif isinstance(sub, ast.If):
            cond_str = _safe_unparse(sub.test)
            if len(cond_str) > 100:
                cond_str = cond_str[:97] + "..."
            conditions.append(cond_str)

        # Loops
        elif isinstance(sub, (ast.For, ast.While)):
            loops.append("for" if isinstance(sub, ast.For) else "while")

        # Exceptions (raise or try/except)
        elif isinstance(sub, ast.Raise):
            if sub.exc is not None:
                exceptions.append(f"raise {_safe_unparse(sub.exc)}")
            else:
                exceptions.append("re-raise")
        elif isinstance(sub, ast.ExceptHandler):
            ex_type = _safe_unparse(sub.type) if sub.type else "Exception"
            exceptions.append(f"catches {ex_type}")

    # Make qualname unique by including file_path to avoid collisions across files
    qualname = f"{file_path}::{class_name}.{func_name}" if class_name else f"{file_path}::{func_name}"

    return FunctionIndexEntry(
        name=func_name,
        qualname=qualname,
        file_path=file_path,
        module_name=module_name,
        class_name=class_name,
        parameters=params,
        parameter_usage=param_usage,
        local_variables=sorted(list(local_vars)),
        returns=returns,
        return_count=len(returns),
        docstring=doc,
        code_snippet=snippet,
        start_line=start_l,
        end_line=end_l,
        called_functions=called,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        decorators=decorators,
        exceptions=exceptions,
        conditions=conditions,
        loops=loops,
        attribute_accesses=attribute_accesses[:15],
        object_constructions=object_constructions[:10],
        db_model_references=db_references[:10],
        api_references=api_references[:5],
        external_service_calls=external_calls[:5],
        imported_symbols=file_imports[:15],
    )


def build_repository_index(
    repo_path: str,
    frameworks: Optional[List[str]] = None,
    file_filter: Optional[List[str]] = None,
) -> RepositoryIndex:
    """
    Build an enriched AST-based repository index for Python files in repo_path.
    Extracts rich static semantic records while degrading gracefully.
    """
    root = Path(repo_path).resolve()
    index = RepositoryIndex(str(root), frameworks=frameworks)

    if file_filter:
        files_to_scan = [root / f if not Path(f).is_absolute() else Path(f) for f in file_filter]
    else:
        files_to_scan = []
        for ext in ("*.py", "*.js", "*.jsx", "*.ts", "*.tsx"):
            for p in root.rglob(ext):
                if any(part in EXCLUDED_DIRS for part in p.parts):
                    continue
                files_to_scan.append(p)

    total_funcs = 0
    domains = set()

    for file_path in files_to_scan:
        if not file_path.exists():
            continue

        try:
            rel_path = str(file_path.relative_to(root)).replace("\\", "/")
        except ValueError:
            rel_path = file_path.name

        try:
            source_code = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug("Could not read %s for indexing: %s", rel_path, e)
            continue

        module_name = file_path.stem
        file_role = classify_file_role(rel_path, source_code)

        # Non-Python files: parse JS/TS functions & API calls via regex
        if file_path.suffix.lower() in (".js", ".jsx", ".ts", ".tsx"):
            _index_js_file(
                source_code=source_code,
                rel_path=rel_path,
                module_name=module_name,
                file_role=file_role,
                index=index,
            )
            continue

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            continue

        file_role = classify_file_role(rel_path, source_code)
        module_name = file_path.stem

        # Extract domain from directory name (e.g. services/payment_service.py -> payment)
        parts = file_path.parts
        for part in parts:
            if part in ("auth", "payment", "payments", "order", "orders", "user", "users", "report", "reports"):
                domains.add(part.capitalize())

        imports: List[str] = []
        imported_names_map: Dict[str, str] = {}
        unresolved_imports: List[str] = []
        constants: List[str] = []
        file_functions: List[str] = []
        file_classes: List[str] = []

        code_lines = source_code.splitlines()

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp_name = alias.name
                    as_name = alias.asname or alias.name
                    imports.append(imp_name)
                    imported_names_map[as_name] = imp_name
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    full_imp = f"{mod}.{alias.name}" if mod else alias.name
                    as_name = alias.asname or alias.name
                    imports.append(full_imp)
                    imported_names_map[as_name] = mod or alias.name
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        if target.id.isupper():
                            constants.append(target.id)
                        else:
                            init_val = _safe_unparse(node.value)
                            state_entry = ModuleLevelStateEntry(
                                name=target.id,
                                file_path=rel_path,
                                line=getattr(node, "lineno", 1),
                                init_value=init_val,
                                readers=[],
                                writers=[],
                            )
                            index.module_level_state.setdefault(rel_path, []).append(state_entry)

        # Track classes first so methods are associated with their class
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                class_name = node.name
                file_classes.append(class_name)
                bases = [_safe_unparse(b) for b in node.bases]
                doc = ast.get_docstring(node) or ""
                
                # Check if model: primarily by inheritance from ORM base classes.
                # File role is only supplemental when the class itself has no bases
                # (avoids tagging every plain utility class in a models.py).
                has_model_base = any(
                    any(b_ind in b.lower() for b_ind in DB_BASE_INDICATORS)
                    for b in bases
                )
                is_model = has_model_base or (
                    "model" in file_role.lower() and bool(bases)
                )

                methods = []
                attrs = []
                for n in node.body:
                    if isinstance(n, ast.Assign):
                        for t in n.targets:
                            if isinstance(t, ast.Name):
                                attrs.append(t.id)
                    elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.append(n.name)
                        fn_entry = _extract_semantic_function_details(
                            node=n,
                            code_lines=code_lines,
                            file_path=rel_path,
                            module_name=module_name,
                            class_name=class_name,
                            file_imports=imports,
                        )
                        index.functions_by_name.setdefault(n.name, []).append(fn_entry)
                        index.functions_by_qualname[fn_entry.qualname] = fn_entry
                        file_functions.append(fn_entry.qualname)
                        total_funcs += 1

                        # Update call graph
                        index.callees_of.setdefault(fn_entry.qualname, set()).update(fn_entry.called_functions)
                        index.callees_of_name.setdefault(n.name, set()).update(fn_entry.called_functions)
                        for c in fn_entry.called_functions:
                            index.callers_of_name.setdefault(c, set()).add(n.name)
                            index.callers_of.setdefault(c, set()).add(fn_entry.qualname)

                start_l = getattr(node, "lineno", 1)
                end_l = getattr(node, "end_lineno", start_l)
                c_entry = ClassIndexEntry(
                    name=class_name,
                    file_path=rel_path,
                    base_classes=bases,
                    methods=methods,
                    docstring=doc,
                    attributes=attrs,
                    is_model=is_model,
                    start_line=start_l,
                    end_line=end_l,
                )
                index.classes_by_name.setdefault(class_name, []).append(c_entry)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Top-level function
                fn_entry = _extract_semantic_function_details(
                    node=node,
                    code_lines=code_lines,
                    file_path=rel_path,
                    module_name=module_name,
                    class_name=None,
                    file_imports=imports,
                )
                index.functions_by_name.setdefault(node.name, []).append(fn_entry)
                index.functions_by_qualname[fn_entry.qualname] = fn_entry
                file_functions.append(fn_entry.qualname)
                total_funcs += 1

                # Update call graph
                index.callees_of.setdefault(fn_entry.qualname, set()).update(fn_entry.called_functions)
                index.callees_of_name.setdefault(node.name, set()).update(fn_entry.called_functions)
                for c in fn_entry.called_functions:
                    index.callers_of_name.setdefault(c, set()).add(node.name)
                    index.callers_of.setdefault(c, set()).add(fn_entry.qualname)

        # Check for unresolved imports (imported local names that do not map to scanned files)
        all_file_stems = {Path(p).stem for p in files_to_scan}
        for imp_name in imports:
            root_mod = imp_name.split(".")[0]
            if root_mod not in all_file_stems and root_mod not in ("sys", "os", "ast", "json", "typing", "datetime", "pathlib", "logging"):
                unresolved_imports.append(imp_name)

        index.files[rel_path] = FileIndexEntry(
            file_path=rel_path,
            module_name=module_name,
            file_role=file_role,
            imports=imports,
            imported_names_map=imported_names_map,
            unresolved_imports=unresolved_imports,
            functions=file_functions,
            classes=file_classes,
            constants=constants,
        )

    # Post-process call graph and module-level state readers/writers
    import re
    for qual, fn_e in index.functions_by_qualname.items():
        for c in fn_e.called_functions:
            callee_fn = index.find_function(c, current_file=fn_e.file_path, enclosing_class=fn_e.class_name)
            if callee_fn:
                index.callees_of.setdefault(qual, set()).add(callee_fn.qualname)
                index.callers_of.setdefault(callee_fn.qualname, set()).add(qual)

    for fp, entries in index.module_level_state.items():
        for entry in entries:
            for fn_e in index.functions_by_qualname.values():
                # Check if function is in same file or imports this file
                snippet = fn_e.code_snippet
                if re.search(r'\b' + re.escape(entry.name) + r'\b', snippet):
                    is_writer = bool(
                        re.search(r'\b' + re.escape(entry.name) + r'\s*(\[[^\]]*\])?\s*([+\-*/%&|^]?=)', snippet)
                        or re.search(r'\b' + re.escape(entry.name) + r'\.(update|clear|pop|popitem|setdefault|append|extend|remove)\b', snippet)
                    )
                    if is_writer:
                        if fn_e.qualname not in entry.writers:
                            entry.writers.append(fn_e.qualname)
                    else:
                        if fn_e.qualname not in entry.readers:
                            entry.readers.append(fn_e.qualname)

    # Generate repository summary
    fw_str = ", ".join(frameworks) if frameworks else "Python Application"
    arch_str = f"Multi-tier codebase ({len(index.files)} files, {total_funcs} functions)"
    index.summary = RepositorySummary(
        name=root.name,
        frameworks=frameworks or [],
        architecture_summary=arch_str,
        primary_domains=sorted(list(domains)),
        total_files=len(index.files),
        total_functions=total_funcs,
    )

    return index


def _index_js_file(
    source_code: str,
    rel_path: str,
    module_name: str,
    file_role: str,
    index: RepositoryIndex,
) -> None:
    """Regex-based parser for JavaScript / TypeScript files for repository intelligence."""
    import re

    lines = source_code.splitlines()
    fn_matches = re.findall(
        r'(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)|(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>',
        source_code,
    )

    api_calls = re.findall(r'(?:fetch|axios\.(?:get|post|put|delete|patch))\s*\(\s*[`\'"]([^`\'"]+)[`\'"]', source_code)
    file_functions = []

    for match in fn_matches:
        fn_name = match[0] or match[2]
        params_str = match[1] if match[0] else match[3]
        if not fn_name:
            continue
        params = [p.strip().split(":")[0].strip() for p in params_str.split(",") if p.strip()]

        fn_entry = FunctionIndexEntry(
            name=fn_name,
            qualname=fn_name,
            file_path=rel_path,
            module_name=module_name,
            class_name=None,
            parameters=params,
            code_snippet=source_code[:1000],
            api_references=[f"API Request: {url}" for url in api_calls],
        )

        index.functions_by_name.setdefault(fn_name, []).append(fn_entry)
        index.functions_by_qualname[fn_name] = fn_entry
        file_functions.append(fn_name)

    index.files[rel_path] = FileIndexEntry(
        file_path=rel_path,
        module_name=module_name,
        file_role=file_role,
        imports=[],
        functions=file_functions,
        classes=[],
        constants=[],
    )



# Global scan cache: repo_path -> RepositoryIndex
_INDEX_CACHE: Dict[str, RepositoryIndex] = {}

def get_repository_index(repo_path: str, frameworks: Optional[List[str]] = None) -> RepositoryIndex:
    """Get or build the cached RepositoryIndex for a repository path."""
    key = str(Path(repo_path).resolve())
    if key not in _INDEX_CACHE:
        _INDEX_CACHE[key] = build_repository_index(repo_path, frameworks=frameworks)
    return _INDEX_CACHE[key]

def clear_repository_index_cache() -> None:
    """Clear cached repository indexes."""
    _INDEX_CACHE.clear()
