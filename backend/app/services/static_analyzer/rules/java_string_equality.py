"""
JAVA_EQ_001 — String/Object comparison with == instead of .equals() (Java)
---------------------------------------------------------------------------
Detects binary_expression nodes that use `==` or `!=` to compare
operands that are likely object references rather than primitives.
Reference equality checks identity, not value — for Strings this is
almost always a bug.
"""

from __future__ import annotations

import re
from typing import Iterator, List, Optional, Set, Dict, Tuple

from ..base_rule import BaseRule
from ..models import CandidateIssue


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


def _is_enum_field_access(node: dict) -> bool:
    """Checks if node is a field access to an enum constant, e.g. JsonToken.NULL or Color.RED."""
    if node.get("type") != "field_access":
        return False
    children = node.get("children", [])
    if children:
        field = children[-1]
        text = field.get("text") or ""
        return bool(_ENUM_CONST_RE.match(text)) and len(text) > 1
    return False


def _is_type_name_only(node: dict) -> bool:
    if node.get("type") != "identifier":
        return False
    text = node.get("text") or ""
    return bool(re.match(r'^[A-Z][a-zA-Z0-9]+$', text))


def _extract_declared_type(declaration: dict) -> Optional[str]:
    children = declaration.get("children", [])
    if not children:
        return None
    type_node = next(
        (c for c in children if c.get("type") in (
            "type_identifier", "integral_type", "floating_point_type",
            "boolean_type", "void_type", "generic_type", "array_type",
            "scoped_type_identifier",
        )),
        None,
    )
    if type_node:
        return type_node.get("text")
    return None


def _index_scope_declarations(ast: dict) -> Tuple[Dict[int, dict], Dict[int, Dict[str, str]]]:
    parent_map: Dict[int, dict] = {}
    scope_decls: Dict[int, Dict[str, str]] = {}

    def _walk_and_index(node: dict, current_scope_id: int) -> None:
        ntype = node.get("type", "")
        new_scope_id = current_scope_id
        if ntype in ("class_declaration", "method_declaration", "constructor_declaration", "block"):
            new_scope_id = id(node)
            if new_scope_id not in scope_decls:
                scope_decls[new_scope_id] = {}

        if ntype in ("local_variable_declaration", "field_declaration", "formal_parameter"):
            dtype = _extract_declared_type(node)
            if dtype:
                for child in node.get("children", []):
                    if child.get("type") in ("variable_declarator", "identifier"):
                        vname = child.get("text", "")
                        if child.get("type") == "variable_declarator":
                            vkids = child.get("children", [])
                            if vkids and vkids[0].get("type") == "identifier":
                                vname = vkids[0].get("text", "")
                        if vname and new_scope_id in scope_decls:
                            scope_decls[new_scope_id][vname] = dtype

        for child in node.get("children", []):
            parent_map[id(child)] = node
            _walk_and_index(child, new_scope_id)

    _walk_and_index(ast, id(ast))
    return parent_map, scope_decls


def _resolve_declared_type(
    ident_node: dict,
    parent_map: Dict[int, dict],
    scope_decls: Dict[int, Dict[str, str]],
) -> Optional[str]:
    vname = ident_node.get("text", "")
    if not vname:
        return None

    curr = ident_node
    while curr is not None:
        curr_id = id(curr)
        if curr_id in scope_decls and vname in scope_decls[curr_id]:
            return scope_decls[curr_id][vname]
        curr = parent_map.get(curr_id)
    return None


def _looks_like_object_reference(
    node: dict,
    declared_type: Optional[str],
) -> bool:
    ntype = node.get("type", "")

    # Skip enum field access (e.g. JsonToken.NULL)
    if _is_enum_field_access(node):
        return False

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

            # Both enum constants or enum field accesses — correct Java
            if (_is_enum_constant(left) or _is_enum_field_access(left)) and \
               (_is_enum_constant(right) or _is_enum_field_access(right)):
                continue

            # If either side is an enum field access (e.g. token == JsonToken.NULL)
            if _is_enum_field_access(left) or _is_enum_field_access(right):
                continue

            # Type-name vs enum-constant
            if (_is_type_name_only(left) and _is_enum_constant(right)) or \
               (_is_enum_constant(left) and _is_type_name_only(right)):
                continue

            # Resolve declared types hierarchically in O(1)
            dtype_left = _resolve_declared_type(left, parent_map, scope_decls) if left.get("type") == "identifier" else None
            dtype_right = _resolve_declared_type(right, parent_map, scope_decls) if right.get("type") == "identifier" else None

            # Skip if either operand is explicitly declared as a primitive
            if (dtype_left in _PRIMITIVE_TYPES) or (dtype_right in _PRIMITIVE_TYPES):
                continue

            # At least one operand must look like an object reference / String
            left_is_ref = _looks_like_object_reference(left, dtype_left)
            right_is_ref = _looks_like_object_reference(right, dtype_right)
            if not (left_is_ref or right_is_ref):
                continue

            # Confidence calibration: HIGH if either operand is a literal string or explicit String type
            is_string_literal = (left.get("type") == "string_literal" or right.get("type") == "string_literal")
            is_explicit_string = (dtype_left in ("String", "java.lang.String") or dtype_right in ("String", "java.lang.String"))
            confidence = "high" if (is_string_literal or is_explicit_string) else "medium"

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
                    "confidence": confidence,
                },
                confidence=confidence,
            )
