"""
JAVA_EQ_001 — String/Object comparison with == instead of .equals() (Java)
---------------------------------------------------------------------------
Detects binary_expression nodes that use `==` or `!=` to compare
operands that are likely object references rather than primitives.
Reference equality checks identity, not value — for Strings this is
almost always a bug.

Detection heuristics (applied in order, each independently sufficient)
----------------------------------------------------------------------
1. Either operand is a method_invocation or object_creation_expression
   (return type is always a reference, never a primitive).
2. Either operand is a field_access (e.g. obj.name).
3. Either operand is a string_literal (e.g. "hello").
4. Either operand is an identifier explicitly declared as `String` /
   `java.lang.String` in a local_variable_declaration, formal_parameter,
   or field_declaration in the enclosing lexical scope hierarchy.
5. Either operand is an identifier whose name follows Java's variable
   naming convention for String objects.
6. Either operand is a type_identifier starting with uppercase (not
   ALL_CAPS enum constant).

Always skipped
--------------
- Either side is a null literal  (null checks are idiomatic Java)
- Either side is a primitive literal
- Either side is explicitly declared as a primitive type (int, boolean,
  long, double, float, char, byte, short)
- Both sides are ALL_CAPS enum constants
- Type-name vs enum-constant comparisons
"""

from __future__ import annotations

import re
from typing import Iterator, List, Optional, Set, Dict, Tuple

from ..base_rule import BaseRule
from ..models import CandidateIssue


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REFERENCE_NODE_TYPES = {
    "method_invocation",
    "object_creation_expression",
    "field_access",
}

_STRING_NAME_HINTS = {
    "str", "name", "text", "msg", "message", "label",
    "key", "value", "path", "url", "uri", "email",
    "token", "id", "code", "description", "title", "content",
}

_ENUM_CONST_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')

# Primitive types that can never be String
_PRIMITIVE_TYPES = {
    "int", "long", "double", "float", "boolean", "char", "byte", "short",
    "void",
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _is_null(node: dict) -> bool:
    return (node.get("text") or "") == "null" or node.get("type") == "null_literal"


def _is_primitive_literal(node: dict) -> bool:
    return node.get("type", "") in {
        "decimal_integer_literal", "decimal_floating_point_literal",
        "integer_literal", "floating_point_literal",
        "true", "false", "character_literal",
    }


def _is_enum_constant(node: dict) -> bool:
    if node.get("type") != "identifier":
        return False
    text = node.get("text") or ""
    return bool(_ENUM_CONST_RE.match(text)) and len(text) > 1


def _is_type_name_only(node: dict) -> bool:
    if node.get("type") != "identifier":
        return False
    text = node.get("text") or ""
    return bool(re.match(r'^[A-Z][a-zA-Z0-9]+$', text))


def _extract_declared_type(declaration: dict) -> Optional[str]:
    children = declaration.get("children", [])
    if not children:
        return None
    for child in children:
        ntype = child.get("type", "")
        if ntype in ("type_identifier", "scoped_type_identifier", "integral_type",
                     "floating_point_type", "boolean_type", "void_type"):
            return (child.get("text") or "").strip() or None
        if ntype == "generic_type":
            first = child.get("children", [{}])[0]
            base_type = (first.get("text") or "").strip()
            return base_type or (child.get("text") or "").strip() or None
        if ntype == "array_type":
            return (child.get("text") or "").strip() or None

    for child in children:
        if child.get("type") not in ("modifiers", "annotation", "marker_annotation"):
            text = (child.get("text") or "").strip()
            if text:
                return text
    return None


def _var_names_in_declaration(declaration: dict) -> List[str]:
    ntype = declaration.get("type", "")
    names: List[str] = []
    if ntype in ("local_variable_declaration", "field_declaration"):
        for child in declaration.get("children", []):
            if child.get("type") == "variable_declarator":
                for c in child.get("children", []):
                    if c.get("type") == "identifier":
                        t = (c.get("text") or "").strip()
                        if t:
                            names.append(t)
            elif child.get("type") == "identifier" and ntype == "field_declaration":
                t = (child.get("text") or "").strip()
                if t:
                    names.append(t)
    elif ntype in ("formal_parameter", "catch_formal_parameter"):
        for child in declaration.get("children", []):
            if child.get("type") == "identifier":
                t = (child.get("text") or "").strip()
                if t:
                    names.append(t)
    return names


def _index_scope_declarations(ast_root: dict) -> Tuple[dict, dict]:
    """
    Index declarations per scope node in a single O(N) pass for fast
    hierarchical resolution.
    """
    parent_map: dict = {}
    scope_decls: dict = {}

    def _walk(curr: dict, parent: Optional[dict]):
        if parent is not None:
            parent_map[id(curr)] = parent

        ntype = curr.get("type", "")
        if ntype in ("block", "class_declaration", "interface_declaration",
                     "method_declaration", "constructor_declaration", "module"):
            decls: dict = {}
            for child in curr.get("children", []):
                ctype = child.get("type", "")
                if ctype in ("local_variable_declaration", "field_declaration", "formal_parameter"):
                    dtype = _extract_declared_type(child)
                    if dtype:
                        for vname in _var_names_in_declaration(child):
                            decls[vname] = dtype
                elif ctype in ("formal_parameters", "parameters"):
                    for p in child.get("children", []):
                        if p.get("type") in ("formal_parameter", "catch_formal_parameter"):
                            dtype = _extract_declared_type(p)
                            if dtype:
                                for vname in _var_names_in_declaration(p):
                                    decls[vname] = dtype
            if decls:
                scope_decls[id(curr)] = decls

        for child in curr.get("children", []):
            _walk(child, curr)

    _walk(ast_root, None)
    return parent_map, scope_decls


def _resolve_declared_type(
    ident_node: dict,
    parent_map: dict,
    scope_decls: dict,
) -> Optional[str]:
    name = (ident_node.get("text") or "").strip()
    if not name:
        return None

    curr = parent_map.get(id(ident_node))
    while curr is not None:
        decls = scope_decls.get(id(curr))
        if decls and name in decls:
            return decls[name]
        curr = parent_map.get(id(curr))
    return None


# ---------------------------------------------------------------------------
# Operand reference-type detector
# ---------------------------------------------------------------------------

def _looks_like_object_reference(
    node: dict,
    declared_type: Optional[str],
) -> bool:
    ntype = node.get("type", "")

    # Always a reference: method call, new expression, field access
    if ntype in _REFERENCE_NODE_TYPES:
        return True

    # String literal
    if ntype == "string_literal":
        return True

    if ntype == "identifier":
        text = node.get("text") or ""
        if not text:
            return False

        # Skip enum constants
        if _is_enum_constant(node):
            return False

        # Check explicit declared type from lexical hierarchy
        if declared_type:
            if declared_type in _PRIMITIVE_TYPES:
                return False
            if declared_type in ("String", "java.lang.String"):
                return True
            if declared_type.endswith("[]") or "<" in declared_type:
                return False

        # Any uppercase-starting (non-enum) identifier
        if text[0].isupper():
            return True

        # Lowercase variable with String-hint name
        lower = text.lower()
        if any(hint in lower for hint in _STRING_NAME_HINTS):
            return True

    return False


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

class JavaStringEquality(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_EQ_001"

    @property
    def issue_type(self) -> str:
        return "string_reference_equality"

    @property
    def severity(self) -> str:
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        # Index scope hierarchy once in O(N)
        parent_map, scope_decls = _index_scope_declarations(ast)

        for node in self._walk(ast):
            if node.get("type") != "binary_expression":
                continue

            children = node.get("children", [])
            if len(children) < 3:
                continue

            operator_node = children[1]
            op_text = operator_node.get("text") or ""
            if op_text not in ("==", "!="):
                continue

            left, right = children[0], children[2]

            # null checks are idiomatic — skip
            if _is_null(left) or _is_null(right):
                continue

            # Primitive literal on either side — skip
            if _is_primitive_literal(left) or _is_primitive_literal(right):
                continue

            # Both enum constants — correct Java
            if _is_enum_constant(left) and _is_enum_constant(right):
                continue

            # Type-name vs enum-constant
            if (_is_type_name_only(left) and _is_enum_constant(right)) or \
               (_is_enum_constant(left)  and _is_type_name_only(right)):
                continue

            # Resolve declared types hierarchically in O(1)
            dtype_left = _resolve_declared_type(left, parent_map, scope_decls) if left.get("type") == "identifier" else None
            dtype_right = _resolve_declared_type(right, parent_map, scope_decls) if right.get("type") == "identifier" else None

            # Skip if either operand is explicitly declared as a primitive
            if (dtype_left in _PRIMITIVE_TYPES) or (dtype_right in _PRIMITIVE_TYPES):
                continue

            # At least one operand must look like an object reference / String
            if not (_looks_like_object_reference(left, dtype_left) or
                    _looks_like_object_reference(right, dtype_right)):
                continue

            op = op_text
            suggested = ".equals()" if op == "==" else "!object.equals(other)"
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"Object compared with `{op}` checks reference identity, "
                    f"not value equality. For Strings use `.equals()` or "
                    f"`Objects.equals()` instead."
                ),
                evidence={
                    "operator": op,
                    "left_operand": left.get("text") or "?",
                    "right_operand": right.get("text") or "?",
                    "suggested": suggested,
                },
            )
