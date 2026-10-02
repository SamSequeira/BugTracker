"""
Controlled Multi-Hop Repository Context Retrieval Engine.

Progressively investigates the repository around a suspicious function through
up to 5 traversal levels, attaching a typed reason to every retrieved item.

Levels:
  0 ΓÇö TARGET      : target function, enclosing class, imports, file role
  1 ΓÇö DIRECT      : direct callees, direct callers, referenced classes
  2 ΓÇö DEPENDENCY  : callees-of-callees, callers-of-callers, value producers/consumers
  3 ΓÇö CONTRACT    : model fields, configuration constants, validation functions
  4 ΓÇö CROSS-LAYER : API routes ΓåÆ service ΓåÆ model (where statically detectable)

Guarantees:
  - Every item carries an explicit, static-analysis-derived reason.
  - Unresolved symbols are marked is_unresolved=True, never fabricated.
  - Deduplication via a seen-set (qualname-keyed) prevents duplicate context.
  - Circular dependencies (AΓåÆBΓåÆA) are detected and short-circuited.
  - Hard budget caps: max_chars, max_items, max_files, max_depth.
  - retrieve_context_for_function() preserves the original signature and
    returns a RetrievedContextPackage with all existing fields intact.
"""

import ast
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from app.services.llm_logic_reviewer.repository_index import (
    ClassIndexEntry,
    FileIndexEntry,
    FunctionIndexEntry,
    RepositoryIndex,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Budget defaults
# ---------------------------------------------------------------------------
MAX_CONTEXT_CHARS = 6000
MAX_ITEMS = 25
MAX_FILES = 8
MAX_DEPTH = 4
MAX_CALLEE_CHUNKS = 4   # kept for backward-compat reference
MAX_CALLER_CHUNKS = 3   # kept for backward-compat reference
MAX_RECURSION_DEPTH = 2  # kept for backward-compat reference

# ---------------------------------------------------------------------------
# Permitted relationship types and their canonical reason strings.
# No free-form reason fabrication is allowed outside this mapping.
# ---------------------------------------------------------------------------
RELATIONSHIP_REASONS: Dict[str, str] = {
    "target":            "target function under investigation",
    "enclosing_class":   "class enclosing the target function",
    "direct_callee":     "called by target function",
    "direct_caller":     "calls target function",
    "callee_of_callee":  "called by a direct callee (two-hop dependency)",
    "caller_of_caller":  "calls a direct caller (two-hop ancestor)",
    "value_producer":    "produces a value consumed by target function",
    "value_consumer":    "consumes the return value of target function",
    "related_class":     "class referenced in target function or its file",
    "model_field":       "ORM/data model whose field is accessed by target",
    "config_value":      "configuration constant referenced by target function",
    "api_route":         "API route whose handler reaches target function",
    "validation_fn":     "validation function called before or after target",
    "unresolved":        "symbol called in code but not found in repository index",
}

# Relevance scores by relationship type (deterministic, not LLM-generated)
RELEVANCE_SCORES: Dict[str, float] = {
    "target":            1.0,
    "direct_callee":     1.0,
    "direct_caller":     0.95,
    "value_producer":    0.85,
    "callee_of_callee":  0.80,
    "value_consumer":    0.80,
    "caller_of_caller":  0.75,
    "enclosing_class":   0.70,
    "related_class":     0.70,
    "model_field":       0.65,
    "api_route":         0.60,
    "validation_fn":     0.60,
    "config_value":      0.55,
    "unresolved":        0.30,
}


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

@dataclass
class RetrievedItem:
    """One node in the multi-hop traversal graph."""
    kind: str                           # "function" | "class" | "constant" | "unresolved"
    name: str                           # simple name (for display)
    relationship: str                   # key from RELATIONSHIP_REASONS
    reason: str                         # human-readable reason string
    hop_distance: int                   # 0 = target, 1 = direct, 2 = two-hop, ΓÇª
    relevance_score: float              # 0.0ΓÇô1.0
    is_unresolved: bool = False         # True if symbol not found in index
    fn: Optional[FunctionIndexEntry] = None
    cls: Optional[ClassIndexEntry] = None
    raw: str = ""                       # freeform for constants / config values


@dataclass
class MultiHopContextPackage:
    """
    Full result from the multi-hop retrieval engine.
    Superset of RetrievedContextPackage for callers that want richer data.
    """
    target_func_name: str
    target_file_path: str
    file_role: str
    repository_summary: str
    items: List[RetrievedItem]
    unresolved_symbols: List[str]
    budget_exhausted: bool
    formatted_context_block: str
    # Legacy fields (populated for full backward compat)
    direct_callees: List[FunctionIndexEntry] = field(default_factory=list)
    direct_callers: List[FunctionIndexEntry] = field(default_factory=list)
    related_classes: List[ClassIndexEntry] = field(default_factory=list)
    enclosing_imports: List[str] = field(default_factory=list)
    deep_callees: List[FunctionIndexEntry] = field(default_factory=list)


# Backward-compatible alias
@dataclass
class RetrievedContextPackage:
    """Structured context ready for LLM prompt injection (original interface)."""
    target_func_name: str
    target_file_path: str
    file_role: str
    repository_summary: str
    direct_callees: List[FunctionIndexEntry]
    direct_callers: List[FunctionIndexEntry]
    related_classes: List[ClassIndexEntry]
    enclosing_imports: List[str]
    deep_callees: List[FunctionIndexEntry]
    formatted_context_block: str
    # Extended fields available on the new package (optional; None if not run)
    multi_hop: Optional[MultiHopContextPackage] = None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _format_function_summary(fn: FunctionIndexEntry, detail_level: str = "compact") -> str:
    """Format a function entry for prompt inclusion."""
    params_str = ", ".join(fn.parameters)
    returns_str = ", ".join(fn.returns) if fn.returns else "None"

    header = f"def {fn.name}({params_str})"
    if fn.class_name:
        header = f"{fn.class_name}.{header}"

    lines = [f"Function: {header} (in {fn.file_path}:{fn.start_line})"]
    if fn.docstring:
        clean_doc = fn.docstring.strip().replace("\n", " ")
        if len(clean_doc) > 120:
            clean_doc = clean_doc[:117] + "..."
        lines.append(f'  Docstring: "{clean_doc}"')
    if fn.returns:
        lines.append(f"  Returns expressions: {returns_str}")

    if detail_level == "code" and fn.code_snippet:
        snip_lines = fn.code_snippet.splitlines()
        if len(snip_lines) <= 25:
            lines.append("  Implementation:")
            lines.append("  ```python")
            for ln in snip_lines:
                lines.append(f"    {ln}")
            lines.append("  ```")
        else:
            lines.append("  Implementation (truncated):")
            lines.append("  ```python")
            for ln in snip_lines[:15]:
                lines.append(f"    {ln}")
            lines.append("    ...")
            lines.append("  ```")

    return "\n".join(lines)


def _format_item(item: RetrievedItem, char_budget: int) -> str:
    """Format a RetrievedItem into a prompt-safe string block."""
    if item.is_unresolved:
        return (
            f"  [UNRESOLVED] {item.name}\n"
            f"    Reason: {item.reason}\n"
            f"    Status: UNRESOLVED RELATIONSHIP (symbol called in code, not found in index)"
        )

    if item.kind == "function" and item.fn:
        fn = item.fn
        params_str = ", ".join(fn.parameters)
        header = f"def {fn.name}({params_str})"
        if fn.class_name:
            header = f"{fn.class_name}.{header}"
        lines = [
            f"  [{item.relationship.upper().replace('_', '-')}] {header} [{fn.file_path}:{fn.start_line}]",
            f"    Reason: {item.reason}",
        ]
        if fn.docstring:
            doc = fn.docstring.strip().replace("\n", " ")
            if len(doc) > 120:
                doc = doc[:117] + "..."
            lines.append(f'    Docstring: "{doc}"')
        if fn.returns:
            ret_str = ", ".join(fn.returns[:3])
            lines.append(f"    Returns: {ret_str}")
        # Include code snippet if budget allows
        if fn.code_snippet and char_budget > 400:
            snip_lines = fn.code_snippet.splitlines()
            if len(snip_lines) <= 20:
                lines.append("    Implementation:")
                lines.append("    ```python")
                for ln in snip_lines:
                    lines.append(f"      {ln}")
                lines.append("    ```")
            else:
                lines.append("    Implementation (truncated):")
                lines.append("    ```python")
                for ln in snip_lines[:12]:
                    lines.append(f"      {ln}")
                lines.append("      ...")
                lines.append("    ```")
        return "\n".join(lines)

    if item.kind == "class" and item.cls:
        cls = item.cls
        attrs_str = ", ".join(cls.attributes[:8]) if cls.attributes else "none"
        methods_str = ", ".join(cls.methods[:6]) if cls.methods else "none"
        return (
            f"  [{item.relationship.upper().replace('_', '-')}] class {cls.name} [{cls.file_path}:{cls.start_line}]\n"
            f"    Reason: {item.reason}\n"
            f"    Attributes: {attrs_str}\n"
            f"    Methods: {methods_str}"
        )

    if item.kind == "constant":
        return (
            f"  [CONFIG-VALUE] {item.name}\n"
            f"    Reason: {item.reason}\n"
            f"    Value context: {item.raw}"
        )

    return f"  [{item.relationship.upper()}] {item.name}\n    Reason: {item.reason}"


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _extract_calls_from_code(code: str) -> Set[str]:
    """Extract all function/method call names from source code via AST."""
    calls: Set[str] = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls.add(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls.add(node.func.attr)
    except SyntaxError:
        pass
    return calls


def _extract_uppercase_names(code: str) -> Set[str]:
    """Extract UPPERCASE_NAMES that may be configuration constants."""
    names: Set[str] = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id.isupper() and len(node.id) > 1:
                names.add(node.id)
    except SyntaxError:
        pass
    return names


def _extract_attribute_objects(code: str) -> Set[str]:
    """Extract the object names from obj.attr access patterns."""
    objs: Set[str] = set()
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    objs.add(node.value.id)
    except SyntaxError:
        pass
    return objs


# ---------------------------------------------------------------------------
# Multi-Hop Engine
# ---------------------------------------------------------------------------

class MultiHopEngine:
    """
    Progressive, budget-bounded multi-hop traversal engine.

    Walks the call graph around a target function through up to 5 levels,
    attaching a typed reason to every retrieved item and enforcing hard caps
    on character budget, item count, file count, and traversal depth.
    """

    def __init__(
        self,
        repo_index: RepositoryIndex,
        target_func_name: str,
        target_code: str,
        file_path: str,
        max_chars: int = MAX_CONTEXT_CHARS,
        max_items: int = MAX_ITEMS,
        max_files: int = MAX_FILES,
        max_depth: int = MAX_DEPTH,
    ):
        self.repo_index = repo_index
        self.target_func_name = target_func_name
        self.target_code = target_code
        self.norm_file = file_path.replace("\\", "/")
        self.max_chars = max_chars
        self.max_items = max_items
        self.max_files = max_files
        self.max_depth = max_depth

        # State
        self.items: List[RetrievedItem] = []
        # Dedup key: qualname for functions, "class:Name" for classes, "const:NAME" for constants
        self.seen: Set[str] = set()
        self.files_touched: Set[str] = set()
        self.unresolved_symbols: List[str] = []
        self.chars_used: int = 0
        self.budget_exhausted: bool = False

    # ------------------------------------------------------------------
    # Budget helpers
    # ------------------------------------------------------------------

    def _over_budget(self) -> bool:
        return (
            len(self.items) >= self.max_items
            or self.chars_used >= self.max_chars
        )

    def _remaining_chars(self) -> int:
        return max(0, self.max_chars - self.chars_used)

    def _can_add_file(self, fp: str) -> bool:
        return fp in self.files_touched or len(self.files_touched) < self.max_files

    # ------------------------------------------------------------------
    # Item registration
    # ------------------------------------------------------------------

    def _dedup_key_fn(self, fn: FunctionIndexEntry) -> str:
        return fn.qualname

    def _dedup_key_cls(self, cls: ClassIndexEntry) -> str:
        return f"class:{cls.name}:{cls.file_path}"

    def _add_fn_item(
        self,
        fn: FunctionIndexEntry,
        relationship: str,
        hop: int,
    ) -> bool:
        """Add a function item. Returns True if added, False if skipped."""
        if self._over_budget():
            self.budget_exhausted = True
            return False
        key = self._dedup_key_fn(fn)
        if key in self.seen:
            return False
        if not self._can_add_file(fn.file_path):
            return False
        self.seen.add(key)
        self.files_touched.add(fn.file_path)
        reason = RELATIONSHIP_REASONS.get(relationship, relationship)
        score = RELEVANCE_SCORES.get(relationship, 0.5)
        item = RetrievedItem(
            kind="function",
            name=fn.name,
            relationship=relationship,
            reason=reason,
            hop_distance=hop,
            relevance_score=score,
            fn=fn,
        )
        self.items.append(item)
        return True

    def _add_cls_item(
        self,
        cls: ClassIndexEntry,
        relationship: str,
        hop: int,
    ) -> bool:
        if self._over_budget():
            self.budget_exhausted = True
            return False
        key = self._dedup_key_cls(cls)
        if key in self.seen:
            return False
        if not self._can_add_file(cls.file_path):
            return False
        self.seen.add(key)
        self.files_touched.add(cls.file_path)
        reason = RELATIONSHIP_REASONS.get(relationship, relationship)
        score = RELEVANCE_SCORES.get(relationship, 0.5)
        item = RetrievedItem(
            kind="class",
            name=cls.name,
            relationship=relationship,
            reason=reason,
            hop_distance=hop,
            relevance_score=score,
            cls=cls,
        )
        self.items.append(item)
        return True

    def _add_unresolved(self, name: str, called_from: str, hop: int) -> None:
        if name in self.unresolved_symbols:
            return
        self.unresolved_symbols.append(name)
        # Only add to items if under budget
        if self._over_budget():
            return
        key = f"unresolved:{name}"
        if key in self.seen:
            return
        self.seen.add(key)
        reason = RELATIONSHIP_REASONS["unresolved"]
        item = RetrievedItem(
            kind="unresolved",
            name=name,
            relationship="unresolved",
            reason=f"{reason} ΓÇö called from {called_from}",
            hop_distance=hop,
            relevance_score=RELEVANCE_SCORES["unresolved"],
            is_unresolved=True,
        )
        self.items.append(item)

    def _add_const_item(
        self,
        name: str,
        raw: str,
        relationship: str,
        hop: int,
    ) -> bool:
        if self._over_budget():
            return False
        key = f"const:{name}"
        if key in self.seen:
            return False
        self.seen.add(key)
        reason = RELATIONSHIP_REASONS.get(relationship, relationship)
        score = RELEVANCE_SCORES.get(relationship, 0.5)
        item = RetrievedItem(
            kind="constant",
            name=name,
            relationship=relationship,
            reason=reason,
            hop_distance=hop,
            relevance_score=score,
            raw=raw,
        )
        self.items.append(item)
        return True

    # ------------------------------------------------------------------
    # Level 0: Target
    # ------------------------------------------------------------------

    def _level0_target(self) -> None:
        """Register the target function itself and its enclosing class."""
        # Mark target as seen to prevent it being re-added at deeper levels
        self.seen.add(self.target_func_name)

        # Try to find the target in the index
        fn = self.repo_index.find_function(self.target_func_name, current_file=self.norm_file)
        if fn:
            key = self._dedup_key_fn(fn)
            self.seen.add(key)
            self.files_touched.add(fn.file_path)
            item = RetrievedItem(
                kind="function",
                name=fn.name,
                relationship="target",
                reason=RELATIONSHIP_REASONS["target"],
                hop_distance=0,
                relevance_score=1.0,
                fn=fn,
            )
            self.items.append(item)

            # Enclosing class
            if fn.class_name:
                cls = self.repo_index.find_class(fn.class_name)
                if cls:
                    self._add_cls_item(cls, "enclosing_class", hop=0)

    # ------------------------------------------------------------------
    # Level 1: Direct callees and callers
    # ------------------------------------------------------------------

    def _level1_direct(self) -> None:
        """Resolve direct callees (from target_code AST) and direct callers."""
        if self.max_depth < 1:
            return

        calls_in_target = _extract_calls_from_code(self.target_code)
        file_entry = self.repo_index.files.get(self.norm_file)
        # Attribute objects in target code (e.g. stripe.X -> 'stripe')
        attr_objects = _extract_attribute_objects(self.target_code)

        # Mark calls through unresolved imported modules (e.g. stripe.create)
        # These come in as attribute method names (e.g. 'create') but the object
        # (e.g. 'stripe') is an unresolved import ΓÇö tag the import as unresolved.
        if file_entry:
            for attr_obj in attr_objects:
                if attr_obj in file_entry.imported_names_map:
                    src_module = file_entry.imported_names_map[attr_obj]
                    # Check if the source module is in unresolved imports
                    if any(src_module in u or attr_obj in u for u in file_entry.unresolved_imports):
                        self._add_unresolved(
                            f"{attr_obj}.* (external module)",
                            self.target_func_name,
                            hop=1,
                        )

        # Direct callees
        for call_name in calls_in_target:
            if self._over_budget():
                break
            # Skip if same as target (recursive call handled later)
            if call_name == self.target_func_name:
                continue
            fn = self.repo_index.find_function(call_name, current_file=self.norm_file)
            if fn:
                self._add_fn_item(fn, "direct_callee", hop=1)
            else:
                # Check if it's in unresolved imports of the file
                if file_entry and call_name in file_entry.imported_names_map:
                    self._add_unresolved(call_name, self.target_func_name, hop=1)
                elif call_name[0].isupper():
                    # PascalCase: may be a class constructor ΓÇö try class lookup
                    cls = self.repo_index.find_class(call_name)
                    if cls:
                        self._add_cls_item(cls, "related_class", hop=1)
                    else:
                        self._add_unresolved(call_name, self.target_func_name, hop=1)
                # else: lowercase call to unknown fn ΓÇö skip silently (builtin/stdlib)

        # Direct callers
        callers = self.repo_index.find_callers(self.target_func_name)
        for caller in callers:
            if self._over_budget():
                break
            self._add_fn_item(caller, "direct_caller", hop=1)

        # Classes defined in the same file
        file_entry = self.repo_index.files.get(self.norm_file)
        if file_entry:
            for cls_name in file_entry.classes:
                if self._over_budget():
                    break
                cls = self.repo_index.find_class(cls_name)
                if cls:
                    self._add_cls_item(cls, "related_class", hop=1)

    # ------------------------------------------------------------------
    # Level 2: Dependency relationships (two-hop)
    # ------------------------------------------------------------------

    def _level2_dependency(self) -> None:
        """Resolve callees-of-callees and callers-of-callers."""
        if self.max_depth < 2:
            return

        # Snapshot Level-1 items before we extend
        l1_fns = [
            item for item in self.items
            if item.kind == "function"
            and item.hop_distance == 1
            and not item.is_unresolved
            and item.fn is not None
        ]

        # Callees of direct callees
        for item in l1_fns:
            if self._over_budget():
                break
            if item.relationship != "direct_callee":
                continue
            callee = item.fn
            for sub_name in callee.called_functions:
                if self._over_budget():
                    break
                if sub_name == self.target_func_name:
                    # Back-edge to target ΓÇö value producer pattern
                    continue
                fn = self.repo_index.find_function(sub_name, current_file=callee.file_path)
                if fn:
                    self._add_fn_item(fn, "callee_of_callee", hop=2)
                else:
                    self._add_unresolved(sub_name, callee.name, hop=2)

        # Callers of direct callers
        for item in l1_fns:
            if self._over_budget():
                break
            if item.relationship != "direct_caller":
                continue
            caller = item.fn
            # Find what caller's callers are
            grandcallers = self.repo_index.find_callers(caller.name)
            for gc in grandcallers:
                if self._over_budget():
                    break
                self._add_fn_item(gc, "caller_of_caller", hop=2)

    # ------------------------------------------------------------------
    # Level 3: Contract relationships
    # ------------------------------------------------------------------

    def _level3_contract(self) -> None:
        """
        Retrieve model fields, config constants, and validation functions.
        Only statically provable relationships are added.
        """
        if self.max_depth < 3:
            return

        # Model fields: find ORM classes referenced via attribute access.
        # Try both exact name and Title-case (e.g. 'order' -> 'Order').
        attr_objects = _extract_attribute_objects(self.target_code)
        for obj_name in attr_objects:
            if self._over_budget():
                break
            # Exact match first
            cls = self.repo_index.find_class(obj_name)
            if cls is None:
                # Try Title-case (e.g. 'order' param -> 'Order' model)
                cls = self.repo_index.find_class(obj_name.capitalize())
            if cls is None:
                # Try all registered classes for a case-insensitive match
                for cname, entries in self.repo_index.classes_by_name.items():
                    if cname.lower() == obj_name.lower() and entries:
                        cls = entries[0]
                        break
            if cls and cls.is_model:
                self._add_cls_item(cls, "model_field", hop=3)

        # Config constants: UPPERCASE_NAMES in target code
        const_names = _extract_uppercase_names(self.target_code)
        file_entry = self.repo_index.files.get(self.norm_file)
        if file_entry:
            for const_name in const_names:
                if self._over_budget():
                    break
                if const_name in file_entry.constants:
                    self._add_const_item(
                        const_name,
                        raw=f"defined in {self.norm_file}",
                        relationship="config_value",
                        hop=3,
                    )

        # Validation functions: callees whose names contain 'validate', 'check', 'verify'
        for item in list(self.items):
            if self._over_budget():
                break
            if item.kind == "function" and item.fn and item.hop_distance <= 1:
                fn = item.fn
                val_keywords = ("validate", "check", "verify", "is_valid", "ensure")
                if any(kw in fn.name.lower() for kw in val_keywords):
                    # Re-tag if already added but add reason note
                    key = self._dedup_key_fn(fn)
                    if key in self.seen:
                        # Already present ΓÇö just note it's also a validation fn
                        for existing in self.items:
                            if existing.fn is fn and existing.relationship != "validation_fn":
                                existing.reason += " (also: validation function)"
                                break

    # ------------------------------------------------------------------
    # Level 4: Cross-layer (API routes)
    # ------------------------------------------------------------------

    def _level4_cross_layer(self) -> None:
        """
        Detect API route ΓåÆ handler ΓåÆ service ΓåÆ model chains where statically possible.
        Only adds items if target function has callers with route decorators, or
        if target itself has a route decorator.
        """
        if self.max_depth < 4:
            return
        if self._remaining_chars() < 500:
            return

        # Check if target itself is a route handler
        fn = self.repo_index.find_function(self.target_func_name, current_file=self.norm_file)
        if fn and fn.api_references:
            route_tag = fn.api_references[0]
            item = RetrievedItem(
                kind="function",
                name=fn.name,
                relationship="api_route",
                reason=f"target function is an API route handler ({route_tag})",
                hop_distance=0,
                relevance_score=RELEVANCE_SCORES["api_route"],
                fn=fn,
            )
            # Don't add duplicate but annotate existing target item
            for existing in self.items:
                if existing.fn is fn and existing.relationship == "target":
                    existing.reason += f" [API route: {route_tag}]"
                    break
            return

        # Check if any direct caller is a route handler
        for item in list(self.items):
            if self._over_budget():
                break
            if item.kind == "function" and item.fn and item.relationship == "direct_caller":
                caller_fn = item.fn
                if caller_fn.api_references:
                    route_tag = caller_fn.api_references[0]
                    item.reason += f" ΓÇö API route handler ({route_tag}); target is downstream service"
                    item.relationship = "api_route"
                    item.relevance_score = RELEVANCE_SCORES["api_route"]

    # ------------------------------------------------------------------
    # Main run
    # ------------------------------------------------------------------

    def run(self) -> "MultiHopContextPackage":
        """Execute all retrieval levels and return the context package."""
        self._level0_target()
        self._level1_direct()
        self._level2_dependency()
        self._level3_contract()
        self._level4_cross_layer()

        # Sort items by (hop_distance ASC, relevance_score DESC)
        self.items.sort(key=lambda x: (x.hop_distance, -x.relevance_score))

        formatted = self._format_block()

        # Extract typed lists for backward compat
        direct_callees = [
            item.fn for item in self.items
            if item.relationship == "direct_callee" and item.fn
        ]
        direct_callers = [
            item.fn for item in self.items
            if item.relationship == "direct_caller" and item.fn
        ]
        related_classes = [
            item.cls for item in self.items
            if item.kind == "class" and item.cls and item.relationship != "enclosing_class"
        ]
        deep_callees = [
            item.fn for item in self.items
            if item.relationship == "callee_of_callee" and item.fn
        ]

        file_entry = self.repo_index.files.get(self.norm_file)
        enclosing_imports = file_entry.imports if file_entry else []
        file_role = file_entry.file_role if file_entry else "APPLICATION_LOGIC"

        summary_str = ""
        if self.repo_index.summary:
            summary_str = self.repo_index.summary.architecture_summary

        return MultiHopContextPackage(
            target_func_name=self.target_func_name,
            target_file_path=self.norm_file,
            file_role=file_role,
            repository_summary=summary_str,
            items=self.items,
            unresolved_symbols=self.unresolved_symbols,
            budget_exhausted=self.budget_exhausted,
            formatted_context_block=formatted,
            direct_callees=direct_callees,
            direct_callers=direct_callers,
            related_classes=related_classes,
            enclosing_imports=enclosing_imports,
            deep_callees=deep_callees,
        )

    # ------------------------------------------------------------------
    # Formatted output
    # ------------------------------------------------------------------

    def _format_block(self) -> str:
        """Render the multi-hop context into a prompt-ready markdown block."""
        sections: List[str] = []
        current_chars = 0

        # Repository overview
        if self.repo_index.summary:
            s = self.repo_index.summary
            fw_str = ", ".join(s.frameworks) if s.frameworks else "None"
            file_entry = self.repo_index.files.get(self.norm_file)
            file_role = file_entry.file_role if file_entry else "APPLICATION_LOGIC"
            overview = (
                f"### REPOSITORY OVERVIEW\n"
                f"- Project: {s.name}\n"
                f"- Architecture: {s.architecture_summary}\n"
                f"- Technologies/Frameworks: {fw_str}\n"
                f"- Key Domains: {', '.join(s.primary_domains) if s.primary_domains else 'General'}\n"
                f"- Target File Role: {file_role}\n"
            )
            sections.append(overview)
            current_chars += len(overview)

        # Group items by hop level
        by_level: Dict[int, List[RetrievedItem]] = {}
        for item in self.items:
            by_level.setdefault(item.hop_distance, []).append(item)

        level_labels = {
            0: "TARGET",
            1: "LEVEL 1 ΓÇö DIRECT DEPENDENCIES",
            2: "LEVEL 2 ΓÇö DEPENDENCY CHAIN",
            3: "LEVEL 3 ΓÇö CONTRACT & MODEL RELATIONSHIPS",
            4: "LEVEL 4 ΓÇö CROSS-LAYER RELATIONSHIPS",
        }

        for lvl in sorted(by_level.keys()):
            if current_chars >= self.max_chars:
                self.budget_exhausted = True
                break
            level_items = by_level[lvl]
            label = level_labels.get(lvl, f"LEVEL {lvl}")
            lines = [f"### {label}:"]
            for item in level_items:
                remaining = self.max_chars - current_chars
                if remaining <= 50:
                    self.budget_exhausted = True
                    break
                item_txt = _format_item(item, char_budget=remaining)
                lines.append(item_txt)
                lines.append("")  # blank line between items
            block = "\n".join(lines)
            if current_chars + len(block) > self.max_chars:
                # Try adding a truncation notice instead
                notice = f"### {label}:\n  [... truncated ΓÇö budget exhausted ...]"
                sections.append(notice)
                self.budget_exhausted = True
                break
            sections.append(block)
            current_chars += len(block)

        # Unresolved symbols summary
        if self.unresolved_symbols and current_chars + 200 < self.max_chars:
            unres_lines = ["### UNRESOLVED SYMBOLS:"]
            for sym in self.unresolved_symbols[:8]:
                unres_lines.append(
                    f"  - {sym} (called in code, not found in repository index"
                    f" ΓÇö likely external/third-party)"
                )
            unres_block = "\n".join(unres_lines)
            sections.append(unres_block)

        return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Public API ΓÇö multi-hop package
# ---------------------------------------------------------------------------

def retrieve_multi_hop_context(
    target_func_name: str,
    target_code: str,
    file_path: str,
    repo_index: Optional[RepositoryIndex],
    max_chars: int = MAX_CONTEXT_CHARS,
    max_items: int = MAX_ITEMS,
    max_files: int = MAX_FILES,
    max_depth: int = MAX_DEPTH,
) -> MultiHopContextPackage:
    """
    Run the multi-hop traversal engine and return a MultiHopContextPackage.

    Every item has a typed relationship and a static-analysis-derived reason.
    Unresolved symbols are marked explicitly ΓÇö no relationships are fabricated.
    """
    if not repo_index:
        file_role = "APPLICATION_LOGIC"
        return MultiHopContextPackage(
            target_func_name=target_func_name,
            target_file_path=file_path,
            file_role=file_role,
            repository_summary="",
            items=[],
            unresolved_symbols=[],
            budget_exhausted=False,
            formatted_context_block="",
        )

    engine = MultiHopEngine(
        repo_index=repo_index,
        target_func_name=target_func_name,
        target_code=target_code,
        file_path=file_path,
        max_chars=max_chars,
        max_items=max_items,
        max_files=max_files,
        max_depth=max_depth,
    )
    return engine.run()


# ---------------------------------------------------------------------------
# Public API ΓÇö backward-compatible shim
# ---------------------------------------------------------------------------

def retrieve_context_for_function(
    target_func_name: str,
    target_code: str,
    file_path: str,
    repo_index: Optional[RepositoryIndex],
    max_chars: int = MAX_CONTEXT_CHARS,
) -> RetrievedContextPackage:
    """
    Backward-compatible entry point. Calls the multi-hop engine internally
    and returns a RetrievedContextPackage with all original fields intact.

    Callers that want the full multi-hop result can access pkg.multi_hop.
    """
    pkg = retrieve_multi_hop_context(
        target_func_name=target_func_name,
        target_code=target_code,
        file_path=file_path,
        repo_index=repo_index,
        max_chars=max_chars,
    )

    norm_file = file_path.replace("\\", "/")
    file_entry = repo_index.files.get(norm_file) if repo_index else None
    file_role = file_entry.file_role if file_entry else "APPLICATION_LOGIC"
    enclosing_imports = file_entry.imports if file_entry else []
    summary_str = ""
    if repo_index and repo_index.summary:
        summary_str = repo_index.summary.architecture_summary

    return RetrievedContextPackage(
        target_func_name=target_func_name,
        target_file_path=norm_file,
        file_role=file_role,
        repository_summary=summary_str,
        direct_callees=pkg.direct_callees,
        direct_callers=pkg.direct_callers,
        related_classes=pkg.related_classes,
        enclosing_imports=enclosing_imports,
        deep_callees=pkg.deep_callees,
        formatted_context_block=pkg.formatted_context_block,
        multi_hop=pkg,
    )
