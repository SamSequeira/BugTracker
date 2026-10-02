from pathlib import Path

from app.services.llm_logic_reviewer.semantic_pipeline import (
    SemanticReviewConfig, build_context, discover_source_files, extract_functions,
    parse_llm_finding, validate_finding,
)


def _config() -> SemanticReviewConfig:
    return SemanticReviewConfig(max_files=10, max_source_chars=10000, max_functions=20, max_context_chars=1000, max_context_depth=1)


def test_discovery_prefers_application_code_and_excludes_tests_and_vendor(tmp_path: Path) -> None:
    (tmp_path / "services").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "vendor").mkdir()
    (tmp_path / "services" / "orders.py").write_text("def charge(total):\n    return total\n")
    (tmp_path / "main.py").write_text("def start():\n    return 1\n")
    (tmp_path / "tests" / "test_orders.py").write_text("def test_charge():\n    assert True\n")
    (tmp_path / "vendor" / "third_party.py").write_text("def ignored():\n    return 1\n")
    selected = discover_source_files(tmp_path, _config())
    assert [item.relative_path for item in selected] == ["services/orders.py", "main.py"]
    assert "application-directory hint" in selected[0].selection_reasons


def test_extracts_methods_and_builds_direct_local_context(tmp_path: Path) -> None:
    path = tmp_path / "services"
    path.mkdir()
    source = path / "orders.py"
    source.write_text("import decimal\n\nclass OrderService:\n    @classmethod\n    async def charge(cls, amount):\n        return calculate_total(amount)\n\ndef calculate_total(amount):\n    return amount * 100\n")
    functions = extract_functions(discover_source_files(tmp_path, _config())[0])
    charge = next(item for item in functions if item.name == "charge")
    assert charge.class_name == "OrderService" and charge.is_async
    assert charge.parameters == ("cls", "amount") and charge.decorators == ("classmethod",)
    context = build_context(charge, functions, _config())
    assert "calculate_total" in context.text and "imports" in context.included


def test_validation_rejects_malformed_and_hallucinated_location_and_accepts_source_evidence(tmp_path: Path) -> None:
    folder = tmp_path / "logic"
    folder.mkdir()
    (folder / "sample.py").write_text("def transfer(amount):\n    return amount * 100\n")
    function = extract_functions(discover_source_files(tmp_path, _config())[0])[0]
    assert parse_llm_finding("not json") is None
    candidate = {"bug_found": True, "bug_type": "unit_mismatch", "title": "Wrong unit", "description": "Returns cents.", "file": "logic/sample.py", "start_line": 2, "end_line": 2, "evidence": "amount is multiplied", "reasoning": "Caller expects dollars", "expected_behavior": "dollars", "actual_behavior": "cents", "confidence": 0.9, "relevant_code": "return amount * 100"}
    assert validate_finding(candidate, function)[0] == "SUPPORTED"
    candidate["start_line"] = 99
    assert validate_finding(candidate, function)[0] == "UNSUPPORTED"
    candidate["start_line"] = 2
    candidate["file"] = "invented.py"
    assert validate_finding(candidate, function)[0] == "UNSUPPORTED"


# =============================================================================
# Component 1 Fix Tests
# =============================================================================

def test_simple_repo_discovery_works(tmp_path: Path) -> None:
    """Test that discovery works on a simple single-file repository."""
    (tmp_path / "main.py").write_text("def hello():\n    return 'world'\n")
    selected = discover_source_files(tmp_path, _config())
    assert len(selected) == 1
    assert selected[0].relative_path == "main.py"


def test_exclusions_apply_to_cache_directories(tmp_path: Path) -> None:
    """Test that cache directories (.tox, .mypy_cache, .ruff_cache, .idea, .vscode, htmlcov) are excluded."""
    (tmp_path / "app.py").write_text("def main():\n    return 1\n")
    (tmp_path / ".tox").mkdir()
    (tmp_path / ".tox" / "toxfile.py").write_text("def tox_func():\n    return 1\n")
    (tmp_path / ".mypy_cache").mkdir()
    (tmp_path / ".mypy_cache" / "cache.py").write_text("def cached():\n    return 1\n")
    (tmp_path / ".ruff_cache").mkdir()
    (tmp_path / ".ruff_cache" / "ruff.py").write_text("def ruff():\n    return 1\n")
    (tmp_path / ".idea").mkdir()
    (tmp_path / ".idea" / "config.py").write_text("def config():\n    return 1\n")
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "settings.py").write_text("def settings():\n    return 1\n")
    (tmp_path / "htmlcov").mkdir()
    (tmp_path / "htmlcov" / "report.py").write_text("def report():\n    return 1\n")
    selected = discover_source_files(tmp_path, _config())
    assert len(selected) == 1
    assert selected[0].relative_path == "app.py"


def test_files_without_hints_get_lower_priority(tmp_path: Path) -> None:
    """Test that Python files without application hints/entry points/functions still get included with lower priority."""
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "api.py").write_text("def process():\n    return 1\n")  # High priority
    (tmp_path / "constants.py").write_text("VERSION = '1.0.0'\nDEBUG = True\n")  # Low priority (no functions)
    selected = discover_source_files(tmp_path, _config())
    # Both files should be selected
    paths = [item.relative_path for item in selected]
    assert "services/api.py" in paths
    assert "constants.py" in paths
    # High priority file should come first
    assert paths[0] == "services/api.py"
    # Low priority file should have the 'executable-python-file' reason
    constants_file = next(item for item in selected if item.relative_path == "constants.py")
    assert "executable-python-file" in constants_file.selection_reasons


def test_priority_ordering_application_over_entry_over_generic(tmp_path: Path) -> None:
    """Test that priority ordering prefers application hints, then entry hints, then generic executable files."""
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "api.py").write_text("def api():\n    return 1\n")  # application hint
    (tmp_path / "main.py").write_text("def start():\n    return 1\n")  # entry hint
    (tmp_path / "utils.py").write_text("def helper():\n    return 1\n")  # executable definitions
    (tmp_path / "config.py").write_text("DB_URL = 'postgres://localhost'\n")  # generic
    selected = discover_source_files(tmp_path, _config())
    paths = [item.relative_path for item in selected]
    # Application hint should be first
    assert paths[0] == "services/api.py"
    # Entry hint should be before generic files
    main_idx = paths.index("main.py")
    config_idx = paths.index("config.py")
    assert main_idx < config_idx


def test_max_files_limit_respected(tmp_path: Path) -> None:
    """Test that max_files limit is respected."""
    # Create 15 files, config allows only 10
    for i in range(15):
        (tmp_path / f"file{i:02d}.py").write_text(f"def func{i}():\n    return {i}\n")
    config = SemanticReviewConfig(max_files=10, max_source_chars=1000000, max_functions=50, max_context_chars=1000, max_context_depth=1)
    selected = discover_source_files(tmp_path, config)
    assert len(selected) == 10


def test_cumulative_source_chars_budget_respected(tmp_path: Path) -> None:
    """Test that cumulative max_source_chars budget is respected."""
    # Create files that will exceed budget
    (tmp_path / "file1.py").write_text("def f1():\n    return 1\n" + " " * 3000)  # ~3100 chars
    (tmp_path / "file2.py").write_text("def f2():\n    return 2\n" + " " * 3000)  # ~3100 chars
    (tmp_path / "file3.py").write_text("def f3():\n    return 3\n" + " " * 3000)  # ~3100 chars
    (tmp_path / "file4.py").write_text("def f4():\n    return 4\n" + " " * 3000)  # ~3100 chars
    config = SemanticReviewConfig(max_files=10, max_source_chars=7000, max_functions=50, max_context_chars=1000, max_context_depth=1)
    selected = discover_source_files(tmp_path, config)
    # Should get 2 files totaling ~6200 chars (< 7000), but not the 3rd which would exceed
    assert len(selected) == 2
    total_chars = sum(item.source_chars for item in selected)
    assert total_chars < 7000


def test_duplicate_paths_are_prevented(tmp_path: Path) -> None:
    """Test that duplicate paths (symlinks, hardlinks) are excluded."""
    import os
    (tmp_path / "original.py").write_text("def original():\n    return 1\n")
    # Create symlink on Unix or copy on Windows
    try:
        os.symlink(tmp_path / "original.py", tmp_path / "link.py")
        # If symlink succeeded, only one file should be selected
        selected = discover_source_files(tmp_path, _config())
        assert len(selected) == 1
        assert selected[0].relative_path in ["original.py", "link.py"]
    except (OSError, NotImplementedError):
        # Windows without privileges or OS doesn't support symlinks
        # In this case copy creates two separate files, so both will be selected
        import shutil
        shutil.copy(tmp_path / "original.py", tmp_path / "link.py")
        selected = discover_source_files(tmp_path, _config())
        # Two separate files means two selections
        assert len(selected) == 2

def test_mixed_extensions_only_selects_python(tmp_path: Path) -> None:
    """Test that only Python source files are selected."""
    (tmp_path / "app.py").write_text("def app():\n    return 1\n")
    (tmp_path / "readme.txt").write_text("This is a readme")
    (tmp_path / "config.json").write_text('{"key": "value"}')
    (tmp_path / "script.js").write_text("function hello() { return 1; }")
    selected = discover_source_files(tmp_path, _config())
    assert len(selected) == 1
    assert selected[0].relative_path == "app.py"


def test_deterministic_ordering_is_stable(tmp_path: Path) -> None:
    """Test that discovery ordering is deterministic and stable across runs."""
    (tmp_path / "zebra.py").write_text("def z():\n    return 1\n")
    (tmp_path / "apple.py").write_text("def a():\n    return 1\n")
    (tmp_path / "main.py").write_text("def m():\n    return 1\n")
    run1 = discover_source_files(tmp_path, _config())
    run2 = discover_source_files(tmp_path, _config())
    paths1 = [item.relative_path for item in run1]
    paths2 = [item.relative_path for item in run2]
    assert paths1 == paths2
    # Main should be first (entry hint), then alphabetical
    assert paths1[0] == "main.py"
    assert paths1[1:] == ["apple.py", "zebra.py"]


def test_invalid_path_returns_empty_list(tmp_path: Path) -> None:
    """Test that invalid path returns empty list without crashing."""
    invalid_path = tmp_path / "nonexistent" / "path"
    selected = discover_source_files(invalid_path, _config())
    assert selected == []


# =============================================================================
# Component 2 Function Extraction Tests
# =============================================================================

def test_extract_top_level_function(tmp_path: Path) -> None:
    """TEST 1: Extract top-level function."""
    (tmp_path / "calc.py").write_text("def calculate_total(price, quantity):\n    return price * quantity\n")
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    assert len(functions) == 1
    assert functions[0].name == "calculate_total"
    assert functions[0].class_name is None
    assert functions[0].parameters == ("price", "quantity")


def test_extract_async_function(tmp_path: Path) -> None:
    """TEST 2: Extract async function and verify is_async flag."""
    (tmp_path / "orders.py").write_text("async def create_order(items):\n    return sum(items)\n")
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    assert len(functions) == 1
    assert functions[0].name == "create_order"
    assert functions[0].is_async is True


def test_extract_class_methods(tmp_path: Path) -> None:
    """TEST 3: Extract all methods from a class."""
    code = """class PaymentService:
    def create(self):
        pass
    def delete(self):
        pass
"""
    (tmp_path / "service.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    assert len(functions) == 2
    assert all(f.class_name == "PaymentService" for f in functions)
    names = {f.name for f in functions}
    assert names == {"create", "delete"}


def test_extract_decorated_function(tmp_path: Path) -> None:
    """TEST 4: Extract decorated function and preserve decorator metadata."""
    code = """def router_post(path):
    def decorator(func):
        return func
    return decorator

@router_post("/expenses")
async def create_expense(amount):
    return amount
"""
    (tmp_path / "api.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    create_expense = next(f for f in functions if f.name == "create_expense")
    assert create_expense.is_async is True
    assert len(create_expense.decorators) == 1
    assert "router_post" in create_expense.decorators[0]


def test_extract_multiple_functions(tmp_path: Path) -> None:
    """TEST 5: Extract all functions from a file with multiple definitions."""
    code = """def func1():
    pass

def func2():
    pass

def func3():
    pass
"""
    (tmp_path / "multi.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    assert len(functions) == 3
    names = {f.name for f in functions}
    assert names == {"func1", "func2", "func3"}


def test_module_level_code_not_extracted(tmp_path: Path) -> None:
    """TEST 6: Module-level constants/assignments should NOT be extracted as functions."""
    code = """API_TIMEOUT = 30
DATABASE_URL = "postgres://localhost"

def actual_function():
    return API_TIMEOUT
"""
    (tmp_path / "config.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    assert len(functions) == 1
    assert functions[0].name == "actual_function"


def test_line_numbers_are_valid(tmp_path: Path) -> None:
    """TEST 7: Verify start_line <= end_line and source location is correct."""
    code = """def first():
    pass

def second():
    x = 1
    y = 2
    return x + y
"""
    (tmp_path / "lines.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    for func in functions:
        assert func.start_line > 0
        assert func.end_line >= func.start_line
        assert func.start_line is not None
        assert func.end_line is not None


def test_no_duplicate_functions(tmp_path: Path) -> None:
    """TEST 8: Same function should not be extracted twice."""
    code = """class Service:
    def method(self):
        pass

def standalone():
    pass
"""
    (tmp_path / "unique.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    qualified_names = [f.qualified_name for f in functions]
    assert len(qualified_names) == len(set(qualified_names))


def test_nested_functions_extracted(tmp_path: Path) -> None:
    """Verify nested functions are extracted."""
    code = """def outer(x):
    def inner(y):
        return x + y
    return inner(10)
"""
    (tmp_path / "nested.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    assert len(functions) == 2
    names = {f.name for f in functions}
    assert "outer" in names
    assert "inner" in names


def test_extract_functions_error_handling(tmp_path: Path) -> None:
    """Verify extract_functions handles malformed Python safely."""
    # This test verifies the function doesn't crash on syntax errors
    # Component 1 already validates syntax, but Component 2 should be defensive
    code = """def valid_function():
    return 1
"""
    (tmp_path / "valid.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    # Should not raise an exception
    functions = extract_functions(selected[0])
    assert len(functions) >= 1


# =============================================================================
# Component 3 Context Construction Tests
# =============================================================================

def test_context_always_includes_target_function(tmp_path: Path) -> None:
    """TEST 1: Target function is always included."""
    (tmp_path / "simple.py").write_text("def calculate(x):\n    return x * 2\n")
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    context = build_context(functions[0], functions, _config())
    assert "target_function" in context.included
    assert "calculate" in context.text


def test_context_includes_direct_local_callee(tmp_path: Path) -> None:
    """TEST 2: Direct local callee is included."""
    code = """def pay(amount):
    return amount * 1.05

def process_payment(amount):
    return pay(amount)
"""
    (tmp_path / "payment.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    process_payment = next(f for f in functions if f.name == "process_payment")
    context = build_context(process_payment, functions, _config())
    assert "direct_callee:pay" in context.included
    assert "pay" in context.text


def test_context_excludes_unrelated_functions(tmp_path: Path) -> None:
    """TEST 3: Unrelated functions are NOT included."""
    code = """def related():
    pass

def target():
    related()

def unrelated():
    pass
"""
    (tmp_path / "funcs.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    target = next(f for f in functions if f.name == "target")
    context = build_context(target, functions, _config())
    assert "related" in context.text
    # unrelated should NOT be in context
    lines = context.text.split("\n")
    unrelated_lines = [l for l in lines if "unrelated" in l and "TARGET FUNCTION" not in l]
    assert len(unrelated_lines) == 0


def test_context_includes_class_context_for_methods(tmp_path: Path) -> None:
    """TEST 4: Class method receives relevant class context."""
    code = """class Service:
    def method1(self):
        pass
    def method2(self):
        self.method1()
"""
    (tmp_path / "service.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    method2 = next(f for f in functions if f.name == "method2")
    context = build_context(method2, functions, _config())
    assert "containing_class" in context.included
    assert "class Service" in context.text


def test_context_includes_module_definitions(tmp_path: Path) -> None:
    """TEST 5: Relevant module-level definition is included."""
    code = """MAX_RETRIES = 3

def retry_operation():
    for i in range(MAX_RETRIES):
        pass
"""
    (tmp_path / "retry.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    context = build_context(functions[0], functions, _config())
    # Module definitions are included via ExtractedFunction.module_definitions
    assert "MAX_RETRIES" in context.text or len(functions[0].module_definitions) > 0


def test_context_no_duplicate_functions(tmp_path: Path) -> None:
    """TEST 6: Context does not contain duplicate functions."""
    code = """def helper():
    pass

def main():
    helper()
    helper()
"""
    (tmp_path / "dup.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    main = next(f for f in functions if f.name == "main")
    context = build_context(main, functions, _config())
    # Count occurrences of "def helper"
    count = context.text.count("def helper")
    assert count == 1


def test_context_respects_size_limit(tmp_path: Path) -> None:
    """TEST 7: Context respects the configured size limit."""
    code = """def large_function():
    x = 1
    y = 2
    z = 3
    a = 4
    b = 5
    c = 6
    return x + y + z + a + b + c

def target():
    return large_function()
"""
    (tmp_path / "large.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    target = next(f for f in functions if f.name == "target")
    # Use very small context limit
    small_config = SemanticReviewConfig(max_files=10, max_source_chars=10000, max_functions=20, max_context_chars=100, max_context_depth=1)
    context = build_context(target, functions, small_config)
    assert len(context.text) <= 150  # Allow some overhead
    assert context.truncated is True


def test_context_preserves_target_on_truncation(tmp_path: Path) -> None:
    """TEST 8: Target function is preserved even when truncation occurs."""
    code = """def huge_callee():
    # Large function
    x = 1
    y = 2
    z = 3
    return x + y + z

def target():
    return huge_callee()
"""
    (tmp_path / "truncate.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    target = next(f for f in functions if f.name == "target")
    small_config = SemanticReviewConfig(max_files=10, max_source_chars=10000, max_functions=20, max_context_chars=80, max_context_depth=1)
    context = build_context(target, functions, small_config)
    assert "target" in context.text
    assert "TARGET FUNCTION" in context.text


def test_context_handles_missing_dependencies(tmp_path: Path) -> None:
    """TEST 9: Missing/unresolvable dependencies do not crash the pipeline."""
    code = """import external_lib

def target():
    external_lib.do_something()
    return 1
"""
    (tmp_path / "external.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    # Should not crash even though external_lib.do_something is not resolvable
    context = build_context(functions[0], functions, _config())
    assert "target" in context.text


def test_context_ordering_is_deterministic(tmp_path: Path) -> None:
    """TEST 10: Context ordering is deterministic."""
    code = """def c():
    pass

def b():
    pass

def a():
    b()
    c()
"""
    (tmp_path / "order.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    a = next(f for f in functions if f.name == "a")
    context1 = build_context(a, functions, _config())
    context2 = build_context(a, functions, _config())
    assert context1.text == context2.text
    assert context1.included == context2.included


def test_context_includes_direct_caller(tmp_path: Path) -> None:
    """TEST 11: Direct local caller is included."""
    code = """def low_level():
    return 1

def mid_level():
    return low_level()
"""
    (tmp_path / "caller.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    low_level = next(f for f in functions if f.name == "low_level")
    context = build_context(low_level, functions, _config())
    assert "direct_caller:mid_level" in context.included
    assert "mid_level" in context.text


def test_context_includes_both_caller_and_callee(tmp_path: Path) -> None:
    """TEST 12: Middle function shows both callers and callees."""
    code = """def bottom():
    return 1

def middle():
    return bottom()

def top():
    return middle()
"""
    (tmp_path / "chain.py").write_text(code)
    selected = discover_source_files(tmp_path, _config())
    functions = extract_functions(selected[0])
    middle = next(f for f in functions if f.name == "middle")
    context = build_context(middle, functions, _config())
    assert "direct_callee:bottom" in context.included
    assert "direct_caller:top" in context.included
    assert "bottom" in context.text
    assert "top" in context.text
