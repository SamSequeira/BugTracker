"""
rules/__init__.py
-----------------
Central registry of all active analysis rules.

To add a new rule:
  1. Create MyRule(BaseRule) in a new file here.
  2. Import it below and add an instance to ALL_RULES.
  Nothing else needs changing.
"""

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

ALL_RULES = [
    PythonDivisionByZero(),
    PythonUnclosedResource(),
    PythonBareExcept(),
    PythonAssertInCode(),
    PythonMutableDefaultArg(),
    JavaScriptDivisionByZero(),
    JavaScriptTripleEquals(),
    JavaScriptNoAwaitInLoop(),
    JavaDivisionByZero(),
    JavaEmptyCatch(),
    JavaStringEquality(),
    JavaUnclosedResource(),
    JavaInfiniteLoop(),
]

__all__ = ["ALL_RULES"]
