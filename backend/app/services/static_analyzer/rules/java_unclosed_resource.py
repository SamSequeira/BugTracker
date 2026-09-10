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

Root-cause note (F-13, F-14)
-----------------------------
The original list was missing several very common Java resource types.
Added: Scanner, DataInputStream, DataOutputStream, InputStream,
OutputStream, ObjectInputStream, ObjectOutputStream, ZipInputStream,
ZipOutputStream, GZIPInputStream, GZIPOutputStream, JarInputStream,
HttpURLConnection, URLConnection.

Covered resource types (common Java I/O, NIO, and JDBC classes):
  (see _RESOURCE_TYPES set below)
"""

from typing import Iterator, List, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

_RESOURCE_TYPES: Set[str] = {
    # java.io — character streams
    "FileReader", "FileWriter",
    "InputStreamReader", "OutputStreamWriter",
    "BufferedReader", "BufferedWriter",
    "PrintWriter", "PrintStream",
    # java.io — byte streams
    "FileInputStream", "FileOutputStream",
    "BufferedInputStream", "BufferedOutputStream",
    "DataInputStream", "DataOutputStream",       # F-13/F-14 fix
    "ObjectInputStream", "ObjectOutputStream",
    "InputStream", "OutputStream",               # F-13/F-14 fix
    "RandomAccessFile",
    # java.util — Scanner reads a resource
    "Scanner",                                   # F-13 fix
    # java.util.zip / java.util.jar
    "ZipInputStream", "ZipOutputStream",
    "GZIPInputStream", "GZIPOutputStream",
    "JarInputStream", "JarOutputStream",
    # java.net
    "Socket", "ServerSocket",
    "HttpURLConnection", "URLConnection",
    # java.sql (JDBC)
    "Connection", "Statement", "PreparedStatement",
    "CallableStatement", "ResultSet",
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

"""
JAVA_RES_001 — Resource opened outside try-with-resources (Java)
-----------------------------------------------------------------
Detects `object_creation_expression` nodes for genuine I/O and JDBC
resources that are NOT managed by a `try-with-resources` statement and
lack explicit lifecycle cleanup.

Suppression criteria (provably safe / intentional):
- Inside `try_with_resources_statement`
- Non-closable test classes (e.g. JUnit `org.junit.runners.model.Statement`)
- In-memory stream classes (`ByteArrayInputStream`, `ByteArrayOutputStream`, `StringReader`, `StringWriter`)
- Resource returned directly or returned via variable (`return stream;`)
- Explicit `.close()` call in the same method/block or in a `finally` block

Confidence calibration:
- HIGH: Direct OS/network/JDBC resources (`FileInputStream`, `FileReader`, `Socket`, `Connection`, `ResultSet`) unclosed in production code.
- MEDIUM: Wrapper streams (`BufferedReader`, `Scanner`) where underlying stream management is ambiguous.
- LOW: Test helper methods or complex factory patterns.
"""

from typing import Iterator, List, Optional, Set

from ..base_rule import BaseRule
from ..models import CandidateIssue

# Real OS / External Closeable Resources
_EXTERNAL_RESOURCE_TYPES: Set[str] = {
    # File I/O
    "FileInputStream", "FileOutputStream",
    "FileReader", "FileWriter",
    "RandomAccessFile",
    # Network I/O
    "Socket", "ServerSocket",
    # JDBC Database
    "Connection", "PreparedStatement", "CallableStatement", "ResultSet",
}

# Wrapper Stream Types (hold references to inner resources)
_WRAPPER_RESOURCE_TYPES: Set[str] = {
    "BufferedReader", "BufferedWriter",
    "InputStreamReader", "OutputStreamWriter",
    "BufferedInputStream", "BufferedOutputStream",
    "DataInputStream", "DataOutputStream",
    "ObjectInputStream", "ObjectOutputStream",
    "ZipInputStream", "ZipOutputStream",
    "GZIPInputStream", "GZIPOutputStream",
    "JarInputStream", "JarOutputStream",
    "PrintWriter", "PrintStream",
    "Scanner",
}

# In-memory non-OS resources that do not leak system file handles
_IN_MEMORY_NON_RESOURCES: Set[str] = {
    "ByteArrayInputStream", "ByteArrayOutputStream",
    "StringReader", "StringWriter",
    "CharArrayReader", "CharArrayWriter",
}


def _type_name(object_creation: dict) -> str:
    for child in object_creation.get("children", []):
        if child.get("type") == "type_identifier":
            return child.get("text", "")
        if child.get("type") == "scoped_type_identifier":
            text = child.get("text", "")
            return text.split(".")[-1] if "." in text else text
        if child.get("type") == "identifier":
            text = child.get("text", "")
            if text and text[0].isupper():
                return text
    text = object_creation.get("text", "")
    import re
    m = re.search(r'new\s+(?:[\w.]*\.)?(\w+)\s*\(', text)
    return m.group(1) if m else ""


def _is_junit_statement(object_creation: dict, file_path: str) -> bool:
    """Detect if 'Statement' is a JUnit TestRule Statement rather than JDBC Statement."""
    text = (object_creation.get("text") or "").strip()
    if "evaluate()" in text or "base.evaluate" in text or "runners.model.Statement" in text:
        return True
    if object_creation.get("type") == "object_creation_expression":
        # Check anonymous class body with evaluate() method
        for child in object_creation.get("children", []):
            if child.get("type") == "class_body":
                if "evaluate" in (child.get("text") or ""):
                    return True
    return False


def _find_enclosing_method(node: dict, parent_map: dict) -> Optional[dict]:
    curr = node
    while id(curr) in parent_map:
        curr = parent_map[id(curr)]
        if curr.get("type") in ("method_declaration", "constructor_declaration", "lambda_expression"):
            return curr
    return None


def _check_method_lifecycle(method_node: dict, var_name: str) -> str:
    """Check if var_name is closed or returned in method scope."""
    if not var_name or not method_node:
        return "UNCLOSED"

    is_closed = False
    is_returned = False

    def _walk_tree(curr: dict):
        nonlocal is_closed, is_returned
        import re
        ntype = curr.get("type", "")
        text = (curr.get("text") or "").strip()

        if ntype == "method_invocation" and (text.startswith(f"{var_name}.close(") or f"{var_name}.close()" in text):
            is_closed = True

        if ntype == "return_statement":
            ret_expr = text[6:].strip().rstrip(";") if text.startswith("return") else text
            if not ret_expr.startswith(f"{var_name}.") and re.search(rf'\b{re.escape(var_name)}\b', ret_expr):
                is_returned = True

        for child in curr.get("children", []):
            _walk_tree(child)

    _walk_tree(method_node)


    if is_returned:
        return "RETURNED"
    if is_closed:
        return "CLOSED"
    return "UNCLOSED"



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
        is_test = self._is_test_file(file_path)

        for node in self._walk(ast):
            if node.get("type") != "object_creation_expression":
                continue

            class_name = _type_name(node)
            if not class_name:
                continue

            # 1. Skip known in-memory streams
            if class_name in _IN_MEMORY_NON_RESOURCES:
                continue

            # 2. Check if this is a real resource class
            is_external = class_name in _EXTERNAL_RESOURCE_TYPES
            is_wrapper = class_name in _WRAPPER_RESOURCE_TYPES

            if not (is_external or is_wrapper):
                continue

            self.record_syntax_match()

            # 3. Check for JUnit Statement false positive
            if class_name == "Statement" and _is_junit_statement(node, file_path):
                self.record_suppression("junit_test_rule_statement")
                continue

            # 4. Check try-with-resources
            if self._inside_try_with_resources(node, parent_map):
                self.record_suppression("managed_by_try_with_resources")
                continue

            # 5. Check if returned directly: return new FileInputStream(...)
            parent = parent_map.get(id(node))
            ptype = parent.get("type", "") if parent else ""

            if ptype == "return_statement":
                self.record_suppression("returned_directly_to_caller")
                continue

            # 6. Extract assigned variable name if any: InputStream in = new FileInputStream(...)
            var_name = ""
            if parent and ptype in ("variable_declarator", "assignment_expression"):
                pchildren = parent.get("children", [])
                if pchildren and pchildren[0].get("type") == "identifier":
                    var_name = (pchildren[0].get("text") or "").strip()

            enclosing_method = _find_enclosing_method(node, parent_map)
            lifecycle = _check_method_lifecycle(enclosing_method, var_name) if enclosing_method and var_name else "UNCLOSED"

            if lifecycle == "RETURNED":
                self.record_suppression(f"resource_{var_name}_returned_to_caller")
                continue

            if lifecycle == "CLOSED":
                self.record_suppression(f"resource_{var_name}_explicitly_closed")
                continue

            confidence = "high" if is_external and not is_test else ("medium" if is_wrapper or is_test else "high")

            snippet_node = parent if ptype in ("variable_declarator", "local_variable_declaration") else node

            yield self._make_issue(
                node=snippet_node,
                file_path=file_path,
                source_lines=source_lines,
                message=(
                    f"`{class_name}` created outside try-with-resources and not guaranteed to be "
                    f"closed. Wrap in `try ({class_name} res = new {class_name}(...))` to prevent leaks."
                ),
                evidence={
                    "resource_type": class_name,
                    "assigned_variable": var_name or None,
                    "lifecycle_status": lifecycle,
                    "confidence": confidence,
                    "reason": f"Resource `{class_name}` created without try-with-resources; lifecycle status is {lifecycle}.",
                },
                confidence=confidence,
            )

    def _inside_try_with_resources(self, node: dict, parent_map: dict) -> bool:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") == "try_with_resources_statement":
                return True
        return False

