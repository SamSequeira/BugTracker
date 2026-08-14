"""
test_ast.py
-----------
Tests AST generation for Python, JavaScript, and Java.
Saves generated AST JSON files to tests/output/.

Run from the backend/ directory:
    python -m pytest tests/test_ast.py -v
    or directly:
    python tests/test_ast.py
"""

import json
import sys
import os
import tempfile
import textwrap
from pathlib import Path

# Make sure backend/app is importable when run from backend/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ast_generator import ASTGenerator, ASTGenerationError

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Sample source code for each language (intentionally includes bug patterns)
# ---------------------------------------------------------------------------

PYTHON_CODE = textwrap.dedent("""\
    def divide(a, b):
        return a / b          # bug: no zero-division guard

    def read_file(path):
        f = open(path, "r")   # bug: file not closed
        return f.read()

    def get_user(data, key):
        return data[key]      # bug: no key existence check

    class Calculator:
        def __init__(self):
            self.history = []

        def add(self, x, y):
            result = x + y
            self.history.append(result)
            return result
""")

JAVASCRIPT_CODE = textwrap.dedent("""\
    function divide(a, b) {
        return a / b;          // bug: no division-by-zero guard
    }

    function getUser(obj, key) {
        return obj[key].name;  // bug: obj[key] may be undefined
    }

    async function fetchData(url) {
        const res = await fetch(url);
        const data = await res.json();
        return data;           // bug: no error handling
    }

    class Stack {
        constructor() {
            this.items = [];
        }
        push(item) { this.items.push(item); }
        pop()  { return this.items.pop(); }
    }
""")

JAVA_CODE = textwrap.dedent("""\
    public class Calculator {

        public int divide(int a, int b) {
            return a / b;  // bug: no division-by-zero guard
        }

        public String getElement(String[] arr, int index) {
            return arr[index];  // bug: no bounds check
        }

        public void readFile(String path) throws Exception {
            java.io.FileReader fr = new java.io.FileReader(path);  // bug: never closed
            int ch;
            while ((ch = fr.read()) != -1) {
                System.out.print((char) ch);
            }
        }
    }
""")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_temp_file(content: str, suffix: str) -> Path:
    """Write content to a named temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    )
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def save_ast_output(ast_result: dict, filename: str) -> Path:
    """Pretty-print AST JSON to the output directory."""
    out_path = OUTPUT_DIR / filename
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ast_result, f, indent=2)
    return out_path


def assert_valid_ast(result: dict, language: str) -> None:
    """Validate the structure of an AST result dict."""
    assert result["success"] is True, \
        f"{language} AST failed: {result.get('error', 'unknown error')}"

    ast = result["ast"]
    assert isinstance(ast, dict), f"{language}: ast is not a dict"
    assert "type" in ast, f"{language}: ast missing 'type'"
    assert "start" in ast, f"{language}: ast missing 'start'"
    assert "end" in ast, f"{language}: ast missing 'end'"
    assert "children" in ast, f"{language}: ast missing 'children'"
    assert isinstance(ast["children"], list), \
        f"{language}: ast['children'] is not a list"

    # Must have parsed at least some nodes
    assert len(ast["children"]) > 0, \
        f"{language}: AST root has no children — likely a parse failure"

    # start/end must have line, column, byte
    for pos_key in ("start", "end"):
        pos = ast[pos_key]
        for field in ("line", "column", "byte"):
            assert field in pos, \
                f"{language}: ast['{pos_key}'] missing '{field}'"


# ---------------------------------------------------------------------------
# Test functions  (also runnable as plain functions, not just via pytest)
# ---------------------------------------------------------------------------

def test_python_ast():
    """AST generation works for Python source code."""
    gen = ASTGenerator()
    tmp = write_temp_file(PYTHON_CODE, ".py")
    try:
        result = gen.generate_ast(str(tmp), "Python")
        assert_valid_ast(result, "Python")

        out = save_ast_output(result, "python_ast.json")
        print(f"  ✓ Python AST → {out}")

        # Language-specific: root node for python is 'module'
        assert result["ast"]["type"] == "module", \
            f"Expected root type 'module', got '{result['ast']['type']}'"
    finally:
        tmp.unlink(missing_ok=True)


def test_javascript_ast():
    """AST generation works for JavaScript source code."""
    gen = ASTGenerator()
    tmp = write_temp_file(JAVASCRIPT_CODE, ".js")
    try:
        result = gen.generate_ast(str(tmp), "JavaScript")
        assert_valid_ast(result, "JavaScript")

        out = save_ast_output(result, "javascript_ast.json")
        print(f"  ✓ JavaScript AST → {out}")

        assert result["ast"]["type"] == "program", \
            f"Expected root type 'program', got '{result['ast']['type']}'"
    finally:
        tmp.unlink(missing_ok=True)


def test_java_ast():
    """AST generation works for Java source code."""
    gen = ASTGenerator()
    tmp = write_temp_file(JAVA_CODE, ".java")
    try:
        result = gen.generate_ast(str(tmp), "Java")
        assert_valid_ast(result, "Java")

        out = save_ast_output(result, "java_ast.json")
        print(f"  ✓ Java AST → {out}")

        assert result["ast"]["type"] == "program", \
            f"Expected root type 'program', got '{result['ast']['type']}'"
    finally:
        tmp.unlink(missing_ok=True)


def test_language_detection_from_extension():
    """detect_language() maps file extensions to the right language."""
    gen = ASTGenerator()
    cases = {
        "main.py":   "Python",
        "app.js":    "JavaScript",
        "App.jsx":   "JavaScript",
        "Main.java": "Java",
        "style.css": None,
        "README.md": None,
    }
    for filename, expected in cases.items():
        detected = gen.detect_language(filename)
        assert detected == expected, \
            f"{filename}: expected '{expected}', got '{detected}'"
    print("  ✓ Language detection from extension")


def test_unsupported_language_raises():
    """generate_ast() raises ASTGenerationError for unsupported languages."""
    gen = ASTGenerator()
    tmp = write_temp_file("body { color: red; }", ".css")
    try:
        try:
            gen.generate_ast(str(tmp), "CSS")
            raise AssertionError("Expected ASTGenerationError but nothing was raised")
        except ASTGenerationError as exc:
            assert "not supported" in str(exc).lower(), \
                f"Unexpected error message: {exc}"
        print("  ✓ Unsupported language raises ASTGenerationError")
    finally:
        tmp.unlink(missing_ok=True)


def test_missing_file_raises():
    """generate_ast() raises ASTGenerationError when the file doesn't exist."""
    gen = ASTGenerator()
    try:
        gen.generate_ast(str(Path.cwd() / "nonexistent_file_xyz.py"), "Python")
        raise AssertionError("Expected ASTGenerationError but nothing was raised")
    except ASTGenerationError as exc:
        assert "not found" in str(exc).lower() or "nonexistent" in str(exc).lower(), \
            f"Unexpected error message: {exc}"
    print("  ✓ Missing file raises ASTGenerationError")


def test_repository_scan():
    """generate_ast_for_repository() scans all supported files in a folder."""
    gen = ASTGenerator()

    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)

        # Write one file of each supported language
        (repo / "script.py").write_text(PYTHON_CODE, encoding="utf-8")
        (repo / "app.js").write_text(JAVASCRIPT_CODE, encoding="utf-8")
        (repo / "Main.java").write_text(JAVA_CODE, encoding="utf-8")
        (repo / "README.md").write_text("# test", encoding="utf-8")  # unsupported

        result = gen.generate_ast_for_repository(str(repo))

        assert result["total_files"] == 4, \
            f"Expected 4 total files, got {result['total_files']}"
        assert result["supported_files"] == 3, \
            f"Expected 3 supported files, got {result['supported_files']}"
        assert set(result["languages_detected"].keys()) == {"Python", "JavaScript", "Java"}, \
            f"Unexpected languages: {result['languages_detected']}"
        assert len(result["files_analyzed"]) == 3

        # Save combined repo scan output
        out = save_ast_output(result, "repository_scan_ast.json")
        print(f"  ✓ Repository scan AST → {out}")


# ---------------------------------------------------------------------------
# Run directly (without pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("Language detection",       test_language_detection_from_extension),
        ("Python AST",               test_python_ast),
        ("JavaScript AST",           test_javascript_ast),
        ("Java AST",                 test_java_ast),
        ("Unsupported language",     test_unsupported_language_raises),
        ("Missing file",             test_missing_file_raises),
        ("Repository scan",          test_repository_scan),
    ]

    passed = failed = 0
    print(f"\n{'='*55}")
    print("  AST Generation Test Suite")
    print(f"{'='*55}\n")

    for name, fn in tests:
        try:
            print(f"[RUN] {name}")
            fn()
            passed += 1
        except Exception as exc:
            print(f"  ✗ FAILED: {exc}")
            failed += 1

    print(f"\n{'='*55}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"  AST output files → {OUTPUT_DIR}")
    print(f"{'='*55}\n")

    sys.exit(0 if failed == 0 else 1)
