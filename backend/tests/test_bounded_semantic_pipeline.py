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
