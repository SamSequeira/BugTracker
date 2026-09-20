"""
JAVA_EQ_001 — String/Object comparison with == instead of .equals() (Java)
---------------------------------------------------------------------------
Detects `binary_expression` nodes that use `==` or `!=` to compare String operands.
In Java, `==` tests object reference identity rather than content equality.

Exemptions:
- Null comparisons: `s == null`, `s != null`
- Primitive literal comparisons: `x == 0`, `b == true`
- Enum constant comparisons: `token == JsonToken.NULL`
- Class literal comparisons: `type == String.class`
"""

from __future__ import annotations

import re
from typing import Iterator, List, Optional, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_PRIMITIVE_TYPES = {
    "int", "long", "double", "float", "boolean", "char", "byte", "short",
}

_ENUM_CONST_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')


def _is_null_node(node: dict) -> bool:
    return (node.get("text") or "").strip() == "null" or node.get("type") == "null_literal"


def _is_primitive_or_class_literal(node: dict) -> bool:
    ntype = node.get("type", "")
    text = (node.get("text") or "").strip()
    if ntype in (
        "decimal_integer_literal", "decimal_floating_point_literal",
        "integer_literal", "floating_point_literal", "true", "false",
        "character_literal",
    ):
        return True
    if text.endswith(".class") or ntype == "class_literal":
        return True
    return False


def _is_enum_constant(node: dict) -> bool:
    ntype = node.get("type", "")
    if ntype == "field_access":
        kids = node.get("children", [])
        if kids:
            field_text = (kids[-1].get("text") or "").strip()
            return bool(_ENUM_CONST_RE.match(field_text)) and len(field_text) > 1
    if ntype == "identifier":
        text = (node.get("text") or "").strip()
        return bool(_ENUM_CONST_RE.match(text)) and len(text) > 1
    return False


_STRING_HINT_RE = re.compile(
    r'^(?:str|string|name|text|msg|message|label|key|value|path|url|uri|email|token|id|code|description|title|content|payload|response|request|body|raw|line|word|.*text|.*content|.*token|.*email|.*url|.*id|first_?name|last_?name|email_?address|.*string|.*address|.*name)$',
    re.IGNORECASE,
)

_PRIMITIVE_NAME_RE = re.compile(
    r'^(?:i|j|k|n|m|count|limit|age|max_?age|min_?age|size|index|idx|pos|len|length|offset|capacity|total|sum|num|number|port)$',
    re.IGNORECASE,
)


def _is_string_node(node: dict, scope_types: Dict[str, str]) -> bool:
    ntype = node.get("type", "")
    text = (node.get("text") or "").strip()
    if ntype in ("string_literal", "string"):
        return True
    if ntype == "identifier":
        decl_type = scope_types.get(text, "")
        if decl_type:
            return decl_type in ("String", "java.lang.String")
        if _PRIMITIVE_NAME_RE.match(text):
            return False
        if _STRING_HINT_RE.match(text):
            return True
    if ntype == "method_invocation":
        if any(m in text for m in (
            ".toString(", ".trim(", ".substring(", ".toLowerCase(", ".toUpperCase(",
            ".getName(", ".getTitle(", ".getContent(", ".getValue(", ".getPath(",
            ".getEmail(", ".getToken(", ".getString(", ".readLine(", ".format("
        )):
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
        yield from self._analyze_scope(ast, {}, file_path, source_lines)

    def _analyze_scope(
        self,
        node: dict,
        outer_types: Dict[str, str],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        scope_types = dict(outer_types)
        ntype = node.get("type", "")

        # Extract formal parameters if method/constructor
        if ntype in ("method_declaration", "constructor_declaration"):
            params = next((c for c in node.get("children", []) if c.get("type") in ("formal_parameters", "parameters")), None)
            if params:
                for p in params.get("children", []):
                    if p.get("type") == "formal_parameter":
                        pkids = p.get("children", [])
                        type_node = next((c for c in pkids if c.get("type") in ("type_identifier", "scoped_type_identifier", "integral_type", "floating_point_type", "boolean_type", "array_type")), None)
                        ident_node = next((c for c in pkids if c.get("type") == "identifier"), None)
                        if type_node and ident_node:
                            vname = (ident_node.get("text") or "").strip()
                            vtype = (type_node.get("text") or "").strip()
                            scope_types[vname] = vtype

        for child in node.get("children", []):
            ctype = child.get("type", "")

            # Variable declarations
            if ctype in ("local_variable_declaration", "field_declaration"):
                type_node = next((c for c in child.get("children", []) if c.get("type") in ("type_identifier", "scoped_type_identifier", "integral_type", "floating_point_type", "boolean_type", "array_type")), None)
                vtype = (type_node.get("text") or "").strip() if type_node else ""
                for vdecl in child.get("children", []):
                    if vdecl.get("type") == "variable_declarator":
                        vkids = vdecl.get("children", [])
                        if vkids and vkids[0].get("type") == "identifier":
                            vname = (vkids[0].get("text") or "").strip()
                            scope_types[vname] = vtype
                    elif vdecl.get("type") == "identifier":
                        vname = (vdecl.get("text") or "").strip()
                        scope_types[vname] = vtype

            elif ctype == "binary_expression":
                yield from self._check_binary(child, scope_types, file_path, source_lines)
            else:
                yield from self._analyze_scope(child, scope_types, file_path, source_lines)

    def _check_binary(
        self,
        node: dict,
        scope_types: Dict[str, str],
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:
        children = node.get("children", [])
        if len(children) < 3:
            return

        op = (children[1].get("text") or "").strip()
        if op not in ("==", "!="):
            return

        left = children[0]
        right = children[2]

        # 1. Null comparisons are safe
        if _is_null_node(left) or _is_null_node(right):
            self.record_suppression("null_comparison")
            return

        # 2. Primitive or class literals are safe
        if _is_primitive_or_class_literal(left) or _is_primitive_or_class_literal(right):
            self.record_suppression("primitive_or_class_literal")
            return

        # 3. Enum constants are safe
        if _is_enum_constant(left) or _is_enum_constant(right):
            self.record_suppression("enum_comparison")
            return

        # Check if either side is a String (literal, String variable, or String-returning method)
        left_is_str = _is_string_node(left, scope_types)
        right_is_str = _is_string_node(right, scope_types)

        if left_is_str or right_is_str:
            snippet = self._snippet(node, source_lines)
            self.record_syntax_match()
            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"String comparison using reference equality `{op}`. "
                    f"Use `.equals()` for value equality in Java."
                ),
                evidence={
                    "operator": op,
                    "left_operand": (left.get("text") or "").strip(),
                    "right_operand": (right.get("text") or "").strip(),
                    "expression": snippet,
                    "confidence": "high",
                },
                confidence="high",
            )
        else:
            self.record_suppression("non_string_reference_or_unknown")
