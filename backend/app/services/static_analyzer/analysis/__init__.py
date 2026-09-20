"""
Reusable Static Analysis Infrastructure for BugTracker Static Analyzer V2.
"""

from .constant_evaluator import evaluate_constant, ConstantEvaluator
from .variable_tracker import VariableStateTracker, ScopeEnvironment, VarState
from .guard_analyzer import GuardAnalyzer, GuardInfo, GuardType
from .reachability_analyzer import ReachabilityAnalyzer
from .resource_tracker import ResourceLifecycleTracker, ResourceState
from .loop_analyzer import LoopAnalyzer, LoopExitStatus

__all__ = [
    "evaluate_constant",
    "ConstantEvaluator",
    "VariableStateTracker",
    "ScopeEnvironment",
    "VarState",
    "GuardAnalyzer",
    "GuardInfo",
    "GuardType",
    "ReachabilityAnalyzer",
    "ResourceLifecycleTracker",
    "ResourceState",
    "LoopAnalyzer",
    "LoopExitStatus",
]
