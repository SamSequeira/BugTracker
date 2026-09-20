"""
resource_tracker.py
-------------------
Lifecycle and disposal tracker for I/O, network, and database resources.
Tracks resource allocations, context management, explicit close calls, aliases, and leak paths.
"""

from __future__ import annotations

import re
from enum import Enum, auto
from typing import Dict, Iterator, List, Optional, Set, Tuple, Union

# Well-known Java resource types that must be closed
JAVA_RESOURCE_CLASSES: Set[str] = {
    # java.io streams & readers
    "FileInputStream", "FileOutputStream", "FileReader", "FileWriter",
    "InputStreamReader", "OutputStreamWriter", "BufferedReader", "BufferedWriter",
    "PrintWriter", "PrintStream", "BufferedInputStream", "BufferedOutputStream",
    "DataInputStream", "DataOutputStream", "ObjectInputStream", "ObjectOutputStream",
    "InputStream", "OutputStream", "RandomAccessFile", "Reader", "Writer",
    # java.util & archives
    "Scanner", "ZipInputStream", "ZipOutputStream", "GZIPInputStream", "GZIPOutputStream",
    "JarInputStream", "JarOutputStream",
    # java.net
    "Socket", "ServerSocket", "HttpURLConnection", "URLConnection",
    # java.sql (JDBC)
    "Connection", "Statement", "PreparedStatement", "CallableStatement", "ResultSet",
}


class ResourceState(Enum):
    DEFINITELY_CLOSED   = auto()
    DEFINITELY_LEAKED   = auto()
    POTENTIALLY_LEAKED  = auto()
    TRANSFERRED         = auto()  # returned or passed to manager
    UNKNOWN             = auto()


class ResourceLifecycleTracker:
    """Analyzes resource acquisition and closure across method/function bodies."""

    @classmethod
    def is_java_resource_type(cls, type_name: str) -> bool:
        if not type_name:
            return False
        clean = type_name.split(".")[-1].split("<")[0].strip()
        return clean in JAVA_RESOURCE_CLASSES

    @classmethod
    def is_python_open_call(cls, call_node: dict) -> bool:
        """Detects calls to builtin `open(...)` or `io.open(...)`."""
        if call_node.get("type") != "call":
            return False
        children = call_node.get("children", [])
        if not children:
            return False
        func_node = children[0]
        func_type = func_node.get("type", "")
        func_text = (func_node.get("text") or "").strip()

        if func_type == "identifier" and func_text == "open":
            return True
        if func_type == "attribute" and func_text in ("io.open", "os.open"):
            return True
        return False

    @classmethod
    def is_inside_python_with(cls, node: dict, parent_map: dict) -> bool:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") == "with_statement":
                return True
        return False

    @classmethod
    def is_inside_java_try_with_resources(cls, node: dict, parent_map: dict) -> bool:
        curr = node
        while id(curr) in parent_map:
            curr = parent_map[id(curr)]
            if curr.get("type") == "try_with_resources_statement":
                return True
        return False

    @classmethod
    def _collect_aliases_in_scope(cls, scope_root: dict, var_name: str) -> Set[str]:
        """Track local variable alias chains for var_name in scope_root."""
        aliases: Set[str] = {var_name}
        for n in cls._walk(scope_root):
            ntype = n.get("type", "")
            # Python assignment / JS & Java assignment_expression / variable_declarator
            if ntype in ("assignment", "assignment_expression", "variable_declarator"):
                kids = n.get("children", [])
                if len(kids) >= 3:
                    lhs_node, rhs_node = kids[0], kids[-1]
                    lhs_name = (lhs_node.get("text") or "").strip()
                    rhs_name = (rhs_node.get("text") or "").strip()
                    if rhs_name in aliases:
                        aliases.add(lhs_name)
                    elif lhs_name in aliases and lhs_name != var_name:
                        aliases.remove(lhs_name)
        return aliases

    @classmethod
    def _is_close_node(cls, node: dict, aliases: Set[str]) -> bool:
        """Determines if AST node is an explicit close() call on an alias."""
        ntype = node.get("type", "")

        # Python: call node
        if ntype == "call":
            kids = node.get("children", [])
            if kids:
                func_node = kids[0]
                if func_node.get("type") == "attribute":
                    attr_kids = func_node.get("children", [])
                    if len(attr_kids) >= 2:
                        obj_name = (attr_kids[0].get("text") or "").strip()
                        method_name = (attr_kids[-1].get("text") or "").strip()
                        if method_name == "close" and obj_name in aliases:
                            return True
                elif (func_node.get("text") or "").strip() in ("close", "closeQuietly"):
                    args_node = next((c for c in kids if c.get("type") == "argument_list"), None)
                    if args_node and any((c.get("text") or "").strip() in aliases for c in args_node.get("children", [])):
                        return True

        # Java: method_invocation node
        if ntype == "method_invocation":
            kids = node.get("children", [])
            if kids:
                target_node = kids[0]
                target_name = (target_node.get("text") or "").strip()
                # Find method name
                ident_nodes = [c for c in kids if c.get("type") == "identifier" and c is not target_node]
                method_name = (ident_nodes[0].get("text") or "").strip() if ident_nodes else ""
                if not method_name and "." in (node.get("text") or ""):
                    text_parts = (node.get("text") or "").split("(")[0].split(".")
                    if len(text_parts) >= 2:
                        target_name = text_parts[-2].strip()
                        method_name = text_parts[-1].strip()

                if method_name == "close" and target_name in aliases:
                    return True
                if target_name in ("close", "closeQuietly"):
                    args_node = next((c for c in kids if c.get("type") == "argument_list"), None)
                    if args_node and any((c.get("text") or "").strip() in aliases for c in args_node.get("children", [])):
                        return True

        return False

    @classmethod
    def analyze_scope_for_var(
        cls,
        scope_root: dict,
        var_name: str,
    ) -> ResourceState:
        """
        Scans statements in scope_root to determine if var_name is
        safely closed (.close()), returned (return var), or leaked.
        """
        if not var_name or not scope_root:
            return ResourceState.UNKNOWN

        aliases = cls._collect_aliases_in_scope(scope_root, var_name)

        has_unconditional_close = False
        has_finally_close = False
        has_conditional_close = False
        has_return = False

        # Scan for explicit close and return statements on exact AST nodes
        for node in cls._walk(scope_root):
            ntype = node.get("type", "")

            # Check return statement
            if ntype == "return_statement":
                kids = [c.get("text", "").strip() for c in node.get("children", [])]
                text = (node.get("text") or "").strip()
                if any(a in kids for a in aliases) or any(text in (f"return {a};", f"return {a}") for a in aliases):
                    has_return = True

            # Check explicit close on leaf call/invocation node
            if cls._is_close_node(node, aliases):
                if cls._is_inside_finally(node, scope_root):
                    has_finally_close = True
                elif cls._is_inside_conditional(node, scope_root):
                    has_conditional_close = True
                else:
                    has_unconditional_close = True

        if has_return:
            return ResourceState.TRANSFERRED
        if has_finally_close or has_unconditional_close:
            return ResourceState.DEFINITELY_CLOSED
        if has_conditional_close:
            return ResourceState.POTENTIALLY_LEAKED
        return ResourceState.DEFINITELY_LEAKED

    @classmethod
    def analyze_scope_for_allocation(
        cls,
        scope_root: dict,
        alloc_node: dict,
        initial_var: Optional[str],
    ) -> ResourceState:
        """
        Analyzes the lifecycle of a specific resource allocation instance within scope_root.
        Tracks alias additions and handle overwrites from the allocation point forward.
        """
        if not initial_var or not scope_root:
            return ResourceState.UNKNOWN

        alloc_start_byte = (alloc_node.get("start") or {}).get("byte", 0)

        live_aliases: Set[str] = {initial_var}
        has_unconditional_close = False
        has_finally_close = False
        has_conditional_close = False
        has_return = False

        # Flatten all nodes in scope_root sorted in document order by start byte
        nodes = list(cls._walk(scope_root))
        nodes.sort(key=lambda n: ((n.get("start") or {}).get("byte", 0), -(n.get("end") or {}).get("byte", 0)))

        for node in nodes:
            n_start_byte = (node.get("start") or {}).get("byte", 0)
            if n_start_byte < alloc_start_byte:
                continue

            ntype = node.get("type", "")

            # 1. Return statement
            if ntype == "return_statement":
                kids = [c.get("text", "").strip() for c in node.get("children", [])]
                text = (node.get("text") or "").strip()
                if any(a in kids for a in live_aliases) or any(text in (f"return {a};", f"return {a}") for a in live_aliases):
                    has_return = True

            # 2. Explicit close call
            if cls._is_close_node(node, live_aliases):
                if cls._is_inside_finally(node, scope_root):
                    has_finally_close = True
                elif cls._is_inside_conditional(node, scope_root):
                    has_conditional_close = True
                else:
                    has_unconditional_close = True

            # 3. Variable assignment / aliasing / overwrite
            if ntype in ("assignment", "assignment_expression", "variable_declarator"):
                # If this assignment is the allocation itself, skip
                if cls._contains_node(node, alloc_node):
                    continue

                kids = node.get("children", [])
                if len(kids) >= 3:
                    lhs_node, rhs_node = kids[0], kids[-1]
                    lhs_name = (lhs_node.get("text") or "").strip()
                    rhs_name = (rhs_node.get("text") or "").strip() if rhs_node.get("type") == "identifier" else ""

                    if rhs_name and rhs_name in live_aliases:
                        live_aliases.add(lhs_name)
                    elif lhs_name in live_aliases:
                        # Reassigned to non-alias value -> remove handle
                        live_aliases.remove(lhs_name)

        if has_return:
            return ResourceState.TRANSFERRED
        if has_finally_close or has_unconditional_close:
            return ResourceState.DEFINITELY_CLOSED
        if has_conditional_close:
            return ResourceState.POTENTIALLY_LEAKED
        return ResourceState.DEFINITELY_LEAKED

    @classmethod
    def _is_inside_finally(cls, node: dict, root: dict) -> bool:
        for fin in cls._find_nodes_of_type(root, "finally_clause"):
            if cls._contains_node(fin, node):
                return True
        return False

    @classmethod
    def _is_inside_conditional(cls, node: dict, root: dict) -> bool:
        for cond_node in cls._find_nodes_of_type(root, {"if_statement", "switch_statement", "switch_block"}):
            if cls._contains_node(cond_node, node):
                return True
        return False

    @classmethod
    def _walk(cls, node: dict) -> Iterator[dict]:
        yield node
        for child in node.get("children", []):
            yield from cls._walk(child)

    @classmethod
    def _find_nodes_of_type(cls, root: dict, target_types: Union[str, Set[str]]) -> List[dict]:
        targets = {target_types} if isinstance(target_types, str) else target_types
        found = []
        for n in cls._walk(root):
            if n.get("type") in targets:
                found.append(n)
        return found

    @classmethod
    def _contains_node(cls, parent: dict, target: dict) -> bool:
        # Byte-precise bounding box check with line/column fallback
        p_start_b = (parent.get("start") or {}).get("byte", 0)
        p_end_b = (parent.get("end") or {}).get("byte", 0)
        t_start_b = (target.get("start") or {}).get("byte", 0)
        t_end_b = (target.get("end") or {}).get("byte", 0)
        if p_start_b != 0 or p_end_b != 0 or t_start_b != 0 or t_end_b != 0:
            return p_start_b <= t_start_b and t_end_b <= p_end_b

        p_start = (parent.get("start") or {}).get("line", 0)
        p_end = (parent.get("end") or {}).get("line", 0)
        t_start = (target.get("start") or {}).get("line", 0)
        t_end = (target.get("end") or {}).get("line", 0)
        return p_start <= t_start and t_end <= p_end
