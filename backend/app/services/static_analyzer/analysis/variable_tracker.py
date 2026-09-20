"""
variable_tracker.py
-------------------
Scope-aware data-flow and variable state tracker across Python, JavaScript, and Java.
Tracks variable assignments, constant values, zero/non-zero status, nullness, and resource handles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Union

from .constant_evaluator import ConstantEvaluator, evaluate_constant


class VarState(Enum):
    DEFINITELY_ZERO     = auto()
    DEFINITELY_NON_ZERO = auto()
    DEFINITELY_NULL     = auto()
    DEFINITELY_NON_NULL = auto()
    GUARDED_NON_ZERO    = auto()
    GUARDED_NON_NULL    = auto()
    RESOURCE_OPEN       = auto()
    UNKNOWN             = auto()


@dataclass
class VarInfo:
    name: str
    state: VarState = VarState.UNKNOWN
    constant_value: Optional[Union[int, float, bool, str]] = None
    node_assigned: Optional[dict] = None
    resource_type: Optional[str] = None

    @property
    def is_definitely_zero(self) -> bool:
        if self.state == VarState.DEFINITELY_ZERO:
            return True
        if self.constant_value is not None and isinstance(self.constant_value, (int, float, bool)):
            return self.constant_value == 0
        return False

    @property
    def is_definitely_non_zero(self) -> bool:
        if self.state in (VarState.DEFINITELY_NON_ZERO, VarState.GUARDED_NON_ZERO):
            return True
        if self.constant_value is not None and isinstance(self.constant_value, (int, float, bool)):
            return self.constant_value != 0
        return False

    @property
    def is_definitely_null(self) -> bool:
        return self.state == VarState.DEFINITELY_NULL

    @property
    def is_definitely_non_null(self) -> bool:
        return self.state in (VarState.DEFINITELY_NON_NULL, VarState.GUARDED_NON_NULL, VarState.RESOURCE_OPEN)


class ScopeEnvironment:
    """Represents a lexical scope with symbol table and parent link."""

    def __init__(self, parent: Optional[ScopeEnvironment] = None, scope_type: str = "block") -> None:
        self.parent = parent
        self.scope_type = scope_type  # "module", "function", "class", "block", "loop"
        self.symbols: Dict[str, VarInfo] = {}

    def get(self, name: str) -> Optional[VarInfo]:
        if name in self.symbols:
            return self.symbols[name]
        if self.parent:
            return self.parent.get(name)
        return None

    def set(self, name: str, info: VarInfo) -> None:
        self.symbols[name] = info

    def update_state(
        self,
        name: str,
        state: VarState,
        constant_value: Optional[Union[int, float, bool, str]] = None,
        node: Optional[dict] = None,
        resource_type: Optional[str] = None,
    ) -> None:
        self.symbols[name] = VarInfo(
            name=name,
            state=state,
            constant_value=constant_value,
            node_assigned=node,
            resource_type=resource_type,
        )

    def kill(self, name: str) -> None:
        """Mark variable as dynamic / unknown when mutated or reassigned dynamically."""
        self.symbols[name] = VarInfo(name=name, state=VarState.UNKNOWN)

    def fork(self, scope_type: str = "block") -> ScopeEnvironment:
        """Create a child scope."""
        child = ScopeEnvironment(parent=self, scope_type=scope_type)
        # Deepcopy symbols to allow local branching
        for k, v in self.symbols.items():
            child.symbols[k] = VarInfo(
                name=v.name,
                state=v.state,
                constant_value=v.constant_value,
                node_assigned=v.node_assigned,
                resource_type=v.resource_type,
            )
        return child


class VariableStateTracker:
    """High-level analyzer for tracking variable facts in Python, JS, and Java."""

    @staticmethod
    def classify_expression(node: Optional[dict], env: ScopeEnvironment) -> VarInfo:
        if not node or not isinstance(node, dict):
            return VarInfo(name="<anon>", state=VarState.UNKNOWN)

        ntype = node.get("type", "")
        text = (node.get("text") or "").strip()

        # 1. Direct variable lookup
        if ntype == "identifier":
            existing = env.get(text)
            if existing:
                return existing
            return VarInfo(name=text, state=VarState.UNKNOWN)

        # 2. Check constant evaluation
        const_val = evaluate_constant(node)
        if const_val is not None:
            if isinstance(const_val, (int, float, bool)):
                state = VarState.DEFINITELY_ZERO if const_val == 0 else VarState.DEFINITELY_NON_ZERO
            elif isinstance(const_val, str):
                state = VarState.DEFINITELY_NON_NULL
            else:
                state = VarState.UNKNOWN
            return VarInfo(name="<const>", state=state, constant_value=const_val, node_assigned=node)

        # 3. Check null / None
        if ConstantEvaluator.is_static_none_or_null(node):
            return VarInfo(name="<null>", state=VarState.DEFINITELY_NULL, node_assigned=node)

        # 4. Object / Collection / Function instantiation is definitely non-null
        if ntype in (
            "object_creation_expression", "dictionary", "list", "set",
            "array", "object", "lambda", "function_expression", "arrow_function",
        ):
            return VarInfo(name="<object>", state=VarState.DEFINITELY_NON_NULL, node_assigned=node)

        # 5. String concatenation / Template string
        if ntype in ("template_string", "string", "string_literal", "character_literal"):
            return VarInfo(name="<string>", state=VarState.DEFINITELY_NON_NULL, node_assigned=node)

        return VarInfo(name="<expr>", state=VarState.UNKNOWN, node_assigned=node)

    @classmethod
    def process_assignment(
        cls,
        lhs_node: dict,
        rhs_node: Optional[dict],
        env: ScopeEnvironment,
        resource_type: Optional[str] = None,
    ) -> Optional[VarInfo]:
        """Record an assignment lhs = rhs in env."""
        var_name = cls.extract_target_name(lhs_node)
        if not var_name:
            return None

        if rhs_node is None:
            info = VarInfo(name=var_name, state=VarState.UNKNOWN)
            env.set(var_name, info)
            return info

        info = cls.classify_expression(rhs_node, env)
        if resource_type:
            info.state = VarState.RESOURCE_OPEN
            info.resource_type = resource_type

        # Re-tag with actual variable name
        stored_info = VarInfo(
            name=var_name,
            state=info.state,
            constant_value=info.constant_value,
            node_assigned=rhs_node,
            resource_type=info.resource_type,
        )
        env.set(var_name, stored_info)
        return stored_info

    @staticmethod
    def extract_target_name(lhs_node: dict) -> Optional[str]:
        if not lhs_node or not isinstance(lhs_node, dict):
            return None
        ntype = lhs_node.get("type", "")
        if ntype == "identifier":
            return (lhs_node.get("text") or "").strip() or None
        if ntype == "variable_declarator":
            children = lhs_node.get("children", [])
            if children and children[0].get("type") == "identifier":
                return (children[0].get("text") or "").strip() or None
        return None
