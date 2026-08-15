"""
JAVA_RES_001 — Resource opened outside try-with-resources (Java)
-----------------------------------------------------------------
Detects object_creation_expression nodes for well-known I/O / JDBC
resource types that are NOT inside a try_with_resources_statement.
Resources not wrapped in try-with-resources leak handles when an
exception is thrown.

Java AST pattern (tree-sitter):
  local_variable_declaration
    └─ object_creation_expression
         └─ type_identifier  ← text matches a known resource class name

The rule walks ancestors: if none is a try_with_resources_statement the
creation is flagged.

Covered resource types (common Java I/O and JDBC classes):
  FileReader, FileWriter, FileInputStream, FileOutputStream,
  BufferedReader, BufferedWriter, InputStreamReader, OutputStreamWriter,
  PrintWriter, RandomAccessFile, Connection, Statement, PreparedStatement,
  ResultSet, Socket, ServerSocket
"""

from typing import Iterator, List, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_RESOURCE_TYPES: Set[str] = {
    "FileReader", "FileWriter",
    "FileInputStream", "FileOutputStream",
    "BufferedReader", "BufferedWriter",
    "InputStreamReader", "OutputStreamWriter",
    "PrintWriter", "RandomAccessFile",
    "Connection", "Statement", "PreparedStatement", "ResultSet",
    "Socket", "ServerSocket",
}


def _type_name(object_creation: dict) -> str:
    """
    Extract the simple class name from an object_creation_expression.
    tree-sitter may represent 'new java.io.FileReader(p)' with a
    scoped type or a plain type_identifier — handle both.
    """
    for child in object_creation.get("children", []):
        if child["type"] == "type_identifier":
            return child.get("text", "")
        # Qualified name: last segment after the final '.'
        if child["type"] in ("scoped_type_identifier",):
            text = child.get("text", "")
            return text.split(".")[-1] if "." in text else text
        # Some versions represent it as an identifier chain directly in text
        if child["type"] == "identifier":
            text = child.get("text", "")
            if text[0].isupper():
                return text
    # Fallback: parse from node text
    text = object_creation.get("text", "")
    # 'new java.io.FileReader(p)' → take word after last '.' before '('
    import re
    m = re.search(r'new\s+(?:[\w.]*\.)?(\w+)\s*\(', text)
    return m.group(1) if m else ""


class JavaUnclosedResource(BaseRule):

    LANGUAGES = ["Java"]

    @property
    def rule_id(self) -> str:
        return "JAVA_RES_001"

    @property
    def issue_type(self) -> str:
        return "unclosed_resource"

    @property
    def severity(self) -> str:
        return "high"

    def analyze(
        self,
        ast: dict,
        file_path: str,
        source_lines: List[str],
    ) -> Iterator[CandidateIssue]:

        parent_map: dict = {}
        self._build_parent_map(ast, parent_map)

        for node in self._walk(ast):
            if node["type"] != "object_creation_expression":
                continue

            class_name = _type_name(node)
            if class_name not in _RESOURCE_TYPES:
                continue

            if self._inside_try_with_resources(node, parent_map):
                continue

            yield self._make_issue(
                node=node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"`{class_name}` created outside a try-with-resources statement. "
                    f"Use `try ({class_name} r = new {class_name}(...))` to ensure "
                    f"the resource is closed even when an exception occurs."
                ),
                evidence={"resource_type": class_name},
            )

    # ------------------------------------------------------------------
    def _build_parent_map(self, node: dict, mapping: dict) -> None:
        for child in node.get("children", []):
            mapping[id(child)] = node
            self._build_parent_map(child, mapping)

    def _inside_try_with_resources(self, node: dict, parent_map: dict) -> bool:
        current = node
        while id(current) in parent_map:
            current = parent_map[id(current)]
            if current["type"] == "try_with_resources_statement":
                return True
        return False
