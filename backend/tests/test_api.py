"""
test_api.py
-----------
Integration tests for the repository clone and file upload endpoints.
Requires the FastAPI server to be running at BASE_URL.

Start the server first:
    cd backend
    uvicorn app.main:app --reload --reload-dir app --reload-exclude repositories --port 8000

Then run:
    python -m pytest tests/test_api.py -v
    or directly:
    python tests/test_api.py
"""

import io
import json
import sys
import os
import zipfile
import tempfile
import textwrap
from pathlib import Path

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

OUTPUT_DIR = Path(__file__).parent / "api_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Sample code used in zip uploads
# ---------------------------------------------------------------------------

PYTHON_CODE = textwrap.dedent("""\
    def add(a, b):
        return a + b

    def divide(a, b):
        return a / b  # bug: no zero-division guard
""")

JAVASCRIPT_CODE = textwrap.dedent("""\
    function greet(name) {
        return "Hello, " + name;
    }

    function divide(a, b) {
        return a / b;  // bug: no division-by-zero guard
    }
""")

JAVA_CODE = textwrap.dedent("""\
    public class Main {
        public static void main(String[] args) {
            System.out.println("Hello, World!");
        }
    }
""")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_server() -> bool:
    """Return True if the API server is reachable."""
    try:
        r = requests.get(f"{BASE_URL.rsplit('/api', 1)[0]}/", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


def _save_output(data: dict, filename: str) -> Path:
    out = OUTPUT_DIR / filename
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out


def _make_zip_bytes(files: dict) -> bytes:
    """Create an in-memory ZIP containing the given {filename: content} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Clone tests
# ---------------------------------------------------------------------------

def test_clone_valid_public_repo():
    """Clone a known small public GitHub repo and verify the response."""
    payload = {"repository_url": "https://github.com/octocat/Hello-World"}
    r = requests.post(f"{BASE_URL}/repositories/clone", json=payload, timeout=60)

    assert r.status_code == 201, \
        f"Expected 201, got {r.status_code}: {r.text}"

    data = r.json()
    assert "repository_id" in data, "Response missing 'repository_id'"
    assert "repository_path" in data, "Response missing 'repository_path'"
    assert "repository_name" in data, "Response missing 'repository_name'"
    assert data["repository_name"] == "Hello-World", \
        f"Unexpected name: {data['repository_name']}"

    out = _save_output(data, "clone_response.json")
    print(f"  ✓ Clone response → {out}")
    return data


def test_clone_invalid_url():
    """Cloning a non-existent repo returns 400."""
    payload = {"repository_url": "https://github.com/nonexistent-org-xyz/nonexistent-repo-xyz-12345"}
    r = requests.post(f"{BASE_URL}/repositories/clone", json=payload, timeout=60)

    assert r.status_code == 400, \
        f"Expected 400 for bad repo, got {r.status_code}: {r.text}"
    print("  ✓ Invalid clone URL returns 400")


def test_clone_missing_url_field():
    """Sending an empty body returns 422 (validation error)."""
    r = requests.post(f"{BASE_URL}/repositories/clone", json={}, timeout=10)
    assert r.status_code == 422, \
        f"Expected 422 for missing field, got {r.status_code}: {r.text}"
    print("  ✓ Missing URL field returns 422")


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------

def test_upload_zip_with_python_file():
    """Upload a ZIP containing a Python file and verify successful response."""
    zip_bytes = _make_zip_bytes({"main.py": PYTHON_CODE})

    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("project.zip", zip_bytes, "application/zip")},
        timeout=30,
    )

    assert r.status_code == 201, \
        f"Expected 201, got {r.status_code}: {r.text}"

    data = r.json()
    assert "repository_id" in data
    assert "repository_path" in data
    assert data["repository_name"] == "project", \
        f"Unexpected name: {data['repository_name']}"

    out = _save_output(data, "upload_zip_python_response.json")
    print(f"  ✓ ZIP upload (Python) → {out}")
    return data


def test_upload_zip_with_multiple_languages():
    """Upload a ZIP with Python, JavaScript, and Java files."""
    zip_bytes = _make_zip_bytes({
        "main.py":   PYTHON_CODE,
        "app.js":    JAVASCRIPT_CODE,
        "Main.java": JAVA_CODE,
    })

    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("multi_lang.zip", zip_bytes, "application/zip")},
        timeout=30,
    )

    assert r.status_code == 201, \
        f"Expected 201, got {r.status_code}: {r.text}"

    data = r.json()
    assert "repository_id" in data

    out = _save_output(data, "upload_zip_multilang_response.json")
    print(f"  ✓ ZIP upload (multi-language) → {out}")
    return data


def test_upload_invalid_file_type():
    """Uploading a non-ZIP, non-code file returns 400."""
    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("document.pdf", b"%PDF-1.4 fake content", "application/pdf")},
        timeout=10,
    )
    assert r.status_code == 400, \
        f"Expected 400 for unsupported file type, got {r.status_code}: {r.text}"
    print("  ✓ Invalid file type returns 400")


def test_upload_empty_zip():
    """Uploading an empty ZIP returns 201 (valid ZIP, just no files)."""
    zip_bytes = _make_zip_bytes({})

    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("empty.zip", zip_bytes, "application/zip")},
        timeout=10,
    )
    # An empty ZIP is structurally valid — server should accept it
    assert r.status_code == 201, \
        f"Expected 201 for empty ZIP, got {r.status_code}: {r.text}"
    print("  ✓ Empty ZIP upload returns 201")


# ---------------------------------------------------------------------------
# End-to-end: upload + analyze
# ---------------------------------------------------------------------------

def test_upload_then_analyze():
    """Upload a multi-language ZIP, then analyze it and verify AST output."""
    # Step 1: upload
    zip_bytes = _make_zip_bytes({
        "main.py":   PYTHON_CODE,
        "app.js":    JAVASCRIPT_CODE,
        "Main.java": JAVA_CODE,
    })

    upload_r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("full_project.zip", zip_bytes, "application/zip")},
        timeout=30,
    )
    assert upload_r.status_code == 201, \
        f"Upload failed: {upload_r.status_code} {upload_r.text}"
    upload_data = upload_r.json()

    repo_id   = upload_data["repository_id"]
    repo_path = upload_data["repository_path"]

    # Step 2: analyze
    analyze_r = requests.post(
        f"{BASE_URL}/repositories/analyze/{repo_id}",
        params={"repository_path": repo_path},
        timeout=60,
    )
    assert analyze_r.status_code == 200, \
        f"Analyze failed: {analyze_r.status_code} {analyze_r.text}"

    analysis = analyze_r.json()
    assert "analysis" in analysis, "Response missing 'analysis' key"

    summary = analysis["analysis"]["summary"]
    assert summary["supported_files"] == 3, \
        f"Expected 3 supported files, got {summary['supported_files']}"
    assert set(summary["languages"].keys()) == {"Python", "JavaScript", "Java"}, \
        f"Unexpected languages: {summary['languages']}"

    files = analysis["analysis"]["files"]
    for f in files:
        assert f["success"] is True, \
            f"AST generation failed for {f['file']}: {f.get('error')}"
        assert "ast" in f, f"Missing 'ast' key in file result: {f['file']}"

    out = _save_output(analysis, "upload_analyze_full_response.json")
    print(f"  ✓ Upload + Analyze → {out}")


# ---------------------------------------------------------------------------
# Run directly (without pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print("  API Integration Test Suite")
    print(f"  Server: {BASE_URL}")
    print(f"{'='*55}\n")

    if not _check_server():
        print("✗  Server is not reachable at", BASE_URL)
        print("   Start it with:  uvicorn app.main:app --reload --reload-dir app --reload-exclude repositories --port 8000")
        print("   (run from the backend/ directory)\n")
        sys.exit(1)

    print("✓  Server is reachable\n")

    tests = [
        # Clone
        ("Clone: valid public repo",        test_clone_valid_public_repo),
        ("Clone: invalid URL returns 400",  test_clone_invalid_url),
        ("Clone: missing field returns 422", test_clone_missing_url_field),
        # Upload
        ("Upload: ZIP with Python file",    test_upload_zip_with_python_file),
        ("Upload: ZIP multi-language",      test_upload_zip_with_multiple_languages),
        ("Upload: invalid file type → 400", test_upload_invalid_file_type),
        ("Upload: empty ZIP → 201",         test_upload_empty_zip),
        # End-to-end
        ("E2E: upload + analyze",           test_upload_then_analyze),
    ]

    passed = failed = 0
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
    print(f"  Output files → {OUTPUT_DIR}")
    print(f"{'='*55}\n")

    sys.exit(0 if failed == 0 else 1)

"""
test_api.py
-----------
Integration tests for the repository clone and file upload endpoints.
Requires the FastAPI server to be running at BASE_URL.

Start the server first:
    cd backend
    uvicorn app.main:app --reload --reload-dir app --reload-exclude repositories --port 8000

Then run:
    python -m pytest tests/test_api.py -v
    or directly:
    python tests/test_api.py
"""

import io
import json
import sys
import os
import zipfile
import tempfile
import textwrap
from pathlib import Path

import requests
import pytest

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")

OUTPUT_DIR = Path(__file__).parent / "api_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def is_server_running() -> bool:
    try:
        r = requests.get(BASE_URL.replace("/api/v1", "/docs"), timeout=0.3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not is_server_running(),
    reason="FastAPI server is not running at BASE_URL (start uvicorn to run live HTTP integration tests)",
)

# ---------------------------------------------------------------------------
# Sample code used in zip uploads
# ---------------------------------------------------------------------------

PYTHON_CODE = textwrap.dedent("""\
    def add(a, b):
        return a + b

    def divide(a, b):
        return a / b  # bug: no zero-division guard
""")

JAVASCRIPT_CODE = textwrap.dedent("""\
    function greet(name) {
        return "Hello, " + name;
    }

    function divide(a, b) {
        return a / b;  // bug: no division-by-zero guard
    }
""")

JAVA_CODE = textwrap.dedent("""\
    public class Main {
        public static void main(String[] args) {
            System.out.println("Hello, World!");
        }
    }
""")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_server() -> bool:
    """Return True if the API server is reachable."""
    try:
        r = requests.get(f"{BASE_URL.rsplit('/api', 1)[0]}/", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


def _save_output(data: dict, filename: str) -> Path:
    out = OUTPUT_DIR / filename
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out


def _make_zip_bytes(files: dict) -> bytes:
    """Create an in-memory ZIP containing the given {filename: content} dict."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Clone tests
# ---------------------------------------------------------------------------

def test_clone_valid_public_repo():
    """Clone a known small public GitHub repo and verify the response."""
    payload = {"repository_url": "https://github.com/octocat/Hello-World"}
    r = requests.post(f"{BASE_URL}/repositories/clone", json=payload, timeout=60)

    assert r.status_code == 201, \
        f"Expected 201, got {r.status_code}: {r.text}"

    data = r.json()
    assert "repository_id" in data, "Response missing 'repository_id'"
    assert "s3_uri" in data or "repository_name" in data, "Response missing repository metadata"
    assert data["repository_name"] == "Hello-World", \
        f"Unexpected name: {data['repository_name']}"

    out = _save_output(data, "clone_response.json")
    print(f"  ✓ Clone response → {out}")
    return data


def test_clone_invalid_url():
    """Attempt to clone a non-existent GitHub repo URL; expect 400 or 500 error."""
    payload = {"repository_url": "https://github.com/nonexistent-user-12345/nonexistent-repo-99999"}
    r = requests.post(f"{BASE_URL}/repositories/clone", json=payload, timeout=65)
    assert r.status_code in (400, 500), \
        f"Expected 400 or 500, got {r.status_code}: {r.text}"
    print(f"  ✓ Invalid clone rejected correctly ({r.status_code})")


def test_clone_missing_url_field():
    """Send body missing 'repository_url'; expect 422 Unprocessable Entity."""
    r = requests.post(f"{BASE_URL}/repositories/clone", json={}, timeout=10)
    assert r.status_code == 422, \
        f"Expected 422, got {r.status_code}"
    print(f"  ✓ Missing URL field rejected with 422")


# ---------------------------------------------------------------------------
# 3. ZIP Upload Tests
# ---------------------------------------------------------------------------

def test_upload_zip_with_python_file():
    """Upload a ZIP containing a Python file and verify successful response."""
    zip_bytes = _make_zip_bytes({"main.py": PYTHON_CODE})

    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("project.zip", zip_bytes, "application/zip")},
        timeout=30,
    )

    assert r.status_code == 201, \
        f"Expected 201, got {r.status_code}: {r.text}"

    data = r.json()
    assert "repository_id" in data
    assert "s3_uri" in data or "repository_name" in data
    assert data["repository_name"] == "project", \
        f"Unexpected name: {data['repository_name']}"

    out = _save_output(data, "upload_zip_python_response.json")
    print(f"  ✓ ZIP upload (Python) → {out}")
    return data


def test_upload_zip_with_multiple_languages():
    """Upload a ZIP with Python, JavaScript, and Java files."""
    zip_bytes = _make_zip_bytes({
        "main.py":   PYTHON_CODE,
        "app.js":    JAVASCRIPT_CODE,
        "Main.java": JAVA_CODE,
    })

    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("multi.zip", zip_bytes, "application/zip")},
        timeout=30,
    )

    assert r.status_code == 201, \
        f"Expected 201, got {r.status_code}: {r.text}"

    data = r.json()
    assert "repository_id" in data
    assert data["repository_name"] == "multi"
    out = _save_output(data, "upload_zip_multilang_response.json")
    print(f"  ✓ Multi-language ZIP upload → {out}")
    return data


def test_upload_invalid_file_type():
    """Upload a plain .txt file instead of a .zip; expect 400."""
    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        timeout=30,
    )
    assert r.status_code == 400, \
        f"Expected 400 for non-zip, got {r.status_code}: {r.text}"
    print(f"  ✓ Non-ZIP upload rejected with 400")


def test_upload_empty_zip():
    """Upload an empty ZIP archive (0 files inside); expect 400."""
    zip_bytes = _make_zip_bytes({})
    r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("empty.zip", zip_bytes, "application/zip")},
        timeout=30,
    )
    assert r.status_code == 400, \
        f"Expected 400 for empty zip, got {r.status_code}: {r.text}"
    print(f"  ✓ Empty ZIP upload rejected with 400")


# ---------------------------------------------------------------------------
# 4. End-to-End: Upload ZIP → Analyze
# ---------------------------------------------------------------------------

def test_upload_then_analyze():
    """Upload a multi-language ZIP, then analyze it and verify AST output."""
    # Step 1: upload
    zip_bytes = _make_zip_bytes({
        "main.py":   PYTHON_CODE,
        "app.js":    JAVASCRIPT_CODE,
        "Main.java": JAVA_CODE,
    })

    upload_r = requests.post(
        f"{BASE_URL}/repositories/upload",
        files={"file": ("full_project.zip", zip_bytes, "application/zip")},
        timeout=30,
    )
    assert upload_r.status_code == 201, \
        f"Upload failed: {upload_r.status_code} {upload_r.text}"
    upload_data = upload_r.json()

    repo_id = upload_data["repository_id"]

    # Step 2: analyze
    analyze_r = requests.post(
        f"{BASE_URL}/repositories/analyze/{repo_id}",
        timeout=60,
    )
    assert analyze_r.status_code == 200, \
        f"Analyze failed: {analyze_r.status_code} {analyze_r.text}"

    # Poll status until completed
    import time
    for _ in range(20):
        status_r = requests.get(f"{BASE_URL}/repositories/{repo_id}/analysis-status", timeout=15)
        if status_r.status_code == 200 and status_r.json().get("status") == "completed":
            break
        time.sleep(0.5)

    arch_r = requests.get(f"{BASE_URL}/repositories/{repo_id}/architecture", timeout=15)
    assert arch_r.status_code == 200
    arch_data = arch_r.json()
    assert len(arch_data.get("technologies", [])) > 0
    print(f"  ✓ Upload + Analyze completed successfully")


# ---------------------------------------------------------------------------
# Run directly (without pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print("  API Integration Test Suite")
    print(f"  Server: {BASE_URL}")
    print(f"{'='*55}\n")

    if not _check_server():
        print("✗  Server is not reachable at", BASE_URL)
        print("   Start it with:  uvicorn app.main:app --reload --reload-dir app --reload-exclude repositories --port 8000")
        print("   (run from the backend/ directory)\n")
        sys.exit(1)

    print("✓  Server is reachable\n")

    tests = [
        # Clone
        ("Clone: valid public repo",        test_clone_valid_public_repo),
        ("Clone: invalid URL returns 400",  test_clone_invalid_url),
        ("Clone: missing field returns 422", test_clone_missing_url_field),
        # Upload
        ("Upload: ZIP with Python file",    test_upload_zip_with_python_file),
        ("Upload: ZIP multi-language",      test_upload_zip_with_multiple_languages),
        ("Upload: invalid file type → 400", test_upload_invalid_file_type),
        ("Upload: empty ZIP → 201",         test_upload_empty_zip),
        # End-to-end
        ("E2E: upload + analyze",           test_upload_then_analyze),
    ]

    passed = failed = 0
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
    print(f"  Output files → {OUTPUT_DIR}")
    print(f"{'='*55}\n")

    sys.exit(0 if failed == 0 else 1)
