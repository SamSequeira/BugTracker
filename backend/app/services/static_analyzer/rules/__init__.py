"""
rules/__init__.py
-----------------
Central registry of all active static analysis rules in BugTracker Static Analyzer V2.
Contains 24 semantic rules across Python, JavaScript, and Java.
"""

# Existing 13 Rules
from .py_division_by_zero import PythonDivisionByZero
from .py_unclosed_resource import PythonUnclosedResource
from .py_bare_except import PythonBareExcept
from .py_assert_in_code import PythonAssertInCode
from .py_mutable_default_arg import PythonMutableDefaultArg
from .js_division_by_zero import JavaScriptDivisionByZero
from .js_triple_equals import JavaScriptTripleEquals
from .js_no_await_in_loop import JavaScriptNoAwaitInLoop
from .java_division_by_zero import JavaDivisionByZero
from .java_empty_catch import JavaEmptyCatch
from .java_string_equality import JavaStringEquality
from .java_unclosed_resource import JavaUnclosedResource
from .java_infinite_loop import JavaInfiniteLoop

# 11 New High-Confidence Semantic Rules
from .py_eval_usage import PythonEvalUsage
from .py_none_comparison import PythonNoneComparison
from .py_unreachable_code import PythonUnreachableCode
from .py_constant_condition import PythonConstantCondition
from .js_eval_usage import JavaScriptEvalUsage
from .js_unreachable_code import JavaScriptUnreachableCode
from .js_constant_condition import JavaScriptConstantCondition
from .js_unhandled_promise import JavaScriptUnhandledPromise
from .java_null_dereference import JavaNullDereference
from .java_unreachable_code import JavaUnreachableCode
from .java_constant_condition import JavaConstantCondition

ALL_RULES = [
    # Python (9 rules)
    PythonDivisionByZero(),
    PythonUnclosedResource(),
    PythonBareExcept(),
    PythonAssertInCode(),
    PythonMutableDefaultArg(),
    PythonEvalUsage(),
    PythonNoneComparison(),
    PythonUnreachableCode(),
    PythonConstantCondition(),

    # JavaScript (7 rules)
    JavaScriptDivisionByZero(),
    JavaScriptTripleEquals(),
    JavaScriptNoAwaitInLoop(),
    JavaScriptEvalUsage(),
    JavaScriptUnreachableCode(),
    JavaScriptConstantCondition(),
    JavaScriptUnhandledPromise(),

    # Java (8 rules)
    JavaDivisionByZero(),
    JavaEmptyCatch(),
    JavaStringEquality(),
    JavaUnclosedResource(),
    JavaInfiniteLoop(),
    JavaNullDereference(),
    JavaUnreachableCode(),
    JavaConstantCondition(),
]

__all__ = ["ALL_RULES"]
