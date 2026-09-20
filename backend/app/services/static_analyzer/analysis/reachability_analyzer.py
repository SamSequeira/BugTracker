"""
reachability_analyzer.py
------------------------
Control-flow termination and structural reachability analyzer.
Identifies terminating statements and structurally unreachable dead code.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Set, Tuple

# Terminating AST node types across Python, JS, Java
_TERMINATING_TYPES = {
    # Python
    "return_statement", "raise_statement", "break_statement", "continue_statement",
    # JavaScript
    "throw_statement",
    # Java (shares return_statement, throw_statement, break_statement, continue_statement)
}

# Block / statement list container node types
_BLOCK_CONTAINER_TYPES = {
    "block", "statement_block", "module", "program", "class_body",
    "switch_block_statement_group", "constructor_body",
}


class ReachabilityAnalyzer:
    """Analyzes control flow to detect terminating paths and unreachable statements."""

    @classmethod
    def is_terminating_statement(cls, stmt_node: Optional[dict]) -> bool:
        """Returns True if stmt_node unconditionally exits or diverts control flow."""
        if not stmt_node or not isinstance(stmt_node, dict):
            return False

        ntype = stmt_node.get("type", "")

        # 1. Direct terminating statement node
        if ntype in _TERMINATING_TYPES:
            return True

        # 2. Expression statement wrapping an exit call: sys.exit(), exit(), process.exit(), System.exit()
        if ntype == "expression_statement":
            text = (stmt_node.get("text") or "").replace(" ", "")
            if any(e in text for e in ("sys.exit(", "System.exit(", "process.exit(", "exit(", "quit(")):
                return True

        # 3. If-else statement where BOTH branches unconditionally terminate
        if ntype == "if_statement":
            return cls._is_terminating_if_else(stmt_node)

        # 4. Try statement where try block (or finally) terminates
        if ntype == "try_statement":
            return cls._is_terminating_try(stmt_node)

        return False

    @classmethod
    def find_unreachable_statements(cls, block_node: dict) -> Iterator[Tuple[dict, dict]]:
        """
        Walks sequential statements in block_node.
        Yields (unreachable_stmt, terminating_stmt) for every statement that cannot be reached.
        """
        children = block_node.get("children", [])
        if not children:
            return

        terminator: Optional[dict] = None

        for child in children:
            ntype = child.get("type", "")

            # Skip punctuation, comments, and empty blocks
            if ntype in ("{", "}", "(", ")", ":", ";", "empty_statement", "comment", "line_comment", "block_comment"):
                continue

            if terminator is not None:
                # This statement is structurally unreachable!
                yield (child, terminator)
                continue

            if cls.is_terminating_statement(child):
                terminator = child

    @classmethod
    def _is_terminating_if_else(cls, if_node: dict) -> bool:
        """
        Determines if an if-statement unconditionally terminates along all execution paths.
        Requires:
          1. Main then-branch unconditionally terminates.
          2. All intermediate elif branches (if any) unconditionally terminate.
          3. An else branch is present and unconditionally terminates.
        """
        children = if_node.get("children", [])

        # 1. Identify then-branch (block or direct statement)
        then_node = None
        elif_nodes: List[dict] = []
        else_branch_node = None

        seen_cond = False
        seen_else_token = False

        for c in children:
            ctype = c.get("type", "")

            if ctype in (":", "parenthesized_expression", "condition"):
                seen_cond = True
                continue

            if ctype == "elif_clause":
                elif_nodes.append(c)
                continue

            if ctype == "else_clause":
                else_branch_node = c
                continue

            if ctype == "else":
                seen_else_token = True
                continue

            # In Java: node immediately following 'else' token is the else branch
            if seen_else_token:
                if ctype not in (";", "line_comment", "block_comment"):
                    else_branch_node = c
                    seen_else_token = False
                continue

            # In Python / JS / Java: then-branch appears after condition
            if seen_cond and then_node is None:
                if ctype not in (";", "line_comment", "block_comment"):
                    then_node = c

        if not then_node or else_branch_node is None:
            return False

        # Check then-branch termination
        if not cls._node_or_block_terminates(then_node):
            return False

        # Check all elif branches termination (Python Tree-sitter AST)
        for elif_clause in elif_nodes:
            # Find the body of the elif_clause
            elif_body = None
            seen_colon = False
            for ec in elif_clause.get("children", []):
                ectype = ec.get("type", "")
                if ectype == ":":
                    seen_colon = True
                    continue
                if seen_colon and elif_body is None:
                    if ectype not in (";", "line_comment", "block_comment"):
                        elif_body = ec
            if not elif_body or not cls._node_or_block_terminates(elif_body):
                return False

        # Check else-branch termination
        # For Python/JS: else_clause contains the body child or an inner if_statement
        if else_branch_node.get("type") == "else_clause":
            inner_body = None
            seen_colon = False
            seen_else = False
            for ec in else_branch_node.get("children", []):
                ectype = ec.get("type", "")
                if ectype in ("else", ":"):
                    seen_else = True
                    continue
                if seen_else and inner_body is None:
                    if ectype not in (";", "line_comment", "block_comment"):
                        inner_body = ec
            if not inner_body or not cls._node_or_block_terminates(inner_body):
                return False
        else:
            # Direct Java else branch (block or statement or if_statement)
            if not cls._node_or_block_terminates(else_branch_node):
                return False

        return True

    @classmethod
    def _node_or_block_terminates(cls, node: dict) -> bool:
        ntype = node.get("type", "")
        if ntype in ("block", "statement_block"):
            return cls._block_unconditionally_terminates(node)
        return cls.is_terminating_statement(node)

    @classmethod
    def _is_terminating_try(cls, try_node: dict) -> bool:
        children = try_node.get("children", [])

        # 1. If finally block unconditionally terminates, the entire try terminates
        finally_clause = next((c for c in children if c.get("type") == "finally_clause"), None)
        if finally_clause:
            fin_block = next((k for k in finally_clause.get("children", []) if k.get("type") in ("block", "statement_block")), None)
            if fin_block and cls._block_unconditionally_terminates(fin_block):
                return True

        # 2. If try block unconditionally terminates and there are no catching clauses
        # (e.g. try...finally), control flow cannot continue past the try-finally structure.
        try_block = next((c for c in children if c.get("type") in ("block", "statement_block")), None)
        except_clauses = [c for c in children if c.get("type") in ("except_clause", "catch_clause")]

        if try_block and cls._block_unconditionally_terminates(try_block):
            if not except_clauses:
                return True
            # If catching clauses exist, check if all of them also terminate
            all_excepts_terminate = True
            for ec in except_clauses:
                ec_block = next((k for k in ec.get("children", []) if k.get("type") in ("block", "statement_block")), None)
                if not ec_block or not cls._block_unconditionally_terminates(ec_block):
                    all_excepts_terminate = False
                    break
            if all_excepts_terminate:
                return True

        return False

    @classmethod
    def _block_unconditionally_terminates(cls, block_node: dict) -> bool:
        for child in block_node.get("children", []):
            if cls.is_terminating_statement(child):
                return True
        return False
