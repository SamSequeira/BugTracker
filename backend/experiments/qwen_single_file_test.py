"""Run independent local-Ollama Qwen experiments against source files.

This module is deliberately standalone: it does not import application services,
write database records, call API endpoints, or participate in repository scans.

Usage:
    python -m experiments.qwen_single_file_test file1.py file2.py
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:3b-instruct-q4_K_M"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
FAILED_RESPONSE_REPLAY_PATH = RESULTS_DIR / "qwen_experiment_20260926T053035660522Z.json"


def build_prompt(source: str) -> str:
    """Build the conservative full-file analysis prompt without truncation."""
    return f'''You are a senior software bug analyst.

Analyze the ENTIRE source file below.

Your task is to identify REAL programming bugs, incorrect behavior, logical
errors, unsafe assumptions, incorrect API usage, resource problems,
exception-handling problems, state/data-flow problems, and other defects that
could cause incorrect runtime behavior.

Do NOT report:
- style issues
- formatting issues
- naming preferences
- documentation suggestions
- refactoring suggestions
- theoretical improvements
- code that is merely unusual
- code that could theoretically be improved but is not actually incorrect

Report definite bugs and suspected/likely bugs separately. For every finding, provide:
{{
  "title": "...",
  "category": "...",
  "severity": "low|medium|high|critical",
  "confidence": 0.0,
  "line_start": 0,
  "line_end": 0,
  "code": "exact relevant code excerpt",
  "explanation": "Why this is a bug",
  "consequence": "Concrete runtime consequence",
  "suggested_fix": "Minimal correction"
}}

Do not invent bugs. Do not report style preferences as bugs. Only report issues
supported by the supplied source code. If uncertain, classify the issue as
suspected rather than definite. Do not invent functions, variables, imports,
APIs, or runtime behavior not present in the supplied source. Analyze the
entire file before producing the final answer.

Return ONLY valid JSON:
{{
  "definite_bugs": [],
  "suspected_bugs": []
}}

SOURCE FILE:
{source}
'''


def _validate_structured_result(value: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Accept only the requested definite/suspected finding schema."""
    if not isinstance(value, dict):
        return None, "Expected a top-level JSON object."
    if "definite_bugs" not in value and "suspected_bugs" not in value:
        return None, "Expected definite_bugs and/or suspected_bugs arrays."
    normalized = dict(value)
    normalized.setdefault("definite_bugs", [])
    normalized.setdefault("suspected_bugs", [])
    if not isinstance(normalized["definite_bugs"], list):
        return None, "Missing or invalid definite_bugs array."
    if not isinstance(normalized["suspected_bugs"], list):
        return None, "Missing or invalid suspected_bugs array."
    return normalized, None


def _balanced_json_candidates(text: str) -> list[str]:
    """Extract brace-balanced JSON objects while respecting JSON strings."""
    candidates: list[str] = []
    for start, character in enumerate(text):
        if character != "{":
            continue
        brace_depth = 1
        in_string = False
        escaped = False
        for end in range(start + 1, len(text)):
            current = text[end]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                brace_depth += 1
            elif current == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    candidates.append(text[start : end + 1])
                    break
                if brace_depth < 0:
                    break
    return candidates


def _markdown_fence_candidates(text: str) -> list[str]:
    """Return Markdown fence contents without using a JSON-extraction regex."""
    candidates: list[str] = []
    fence_content: list[str] | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if fence_content is None:
            if stripped.startswith("```"):
                fence_content = []
            continue
        if stripped.startswith("```"):
            candidates.append("".join(fence_content))
            fence_content = None
        else:
            fence_content.append(line)
    return candidates


def _unwrap_ollama_response(value: Any) -> tuple[str | None, str | None]:
    """Accept a model string or an Ollama response envelope without double-decoding."""
    decoded = value
    if isinstance(decoded, str):
        stripped = decoded.strip()
        if not stripped:
            return None, "Model returned an empty response."
        try:
            possible_envelope = json.loads(stripped)
        except json.JSONDecodeError:
            return decoded, None
        if isinstance(possible_envelope, dict) and isinstance(possible_envelope.get("response"), str):
            decoded = possible_envelope["response"]
        elif isinstance(possible_envelope, str):
            decoded = possible_envelope
        else:
            return decoded, None
    elif isinstance(decoded, dict):
        decoded = decoded.get("response")

    if not isinstance(decoded, str):
        return None, "Expected a model response string or an Ollama envelope with a response string."
    if not decoded.strip():
        return None, "Model returned an empty response."
    return decoded, None


def _is_json_string_terminator(text: str, quote_index: int) -> bool:
    """Return whether a quote can legally end a JSON string at this position."""
    next_index = quote_index + 1
    while next_index < len(text) and text[next_index].isspace():
        next_index += 1
    return next_index == len(text) or text[next_index] in ":,}]"


def _escape_unescaped_quotes_in_json_strings(text: str) -> str:
    """Repair only quotes that cannot terminate a JSON string.

    Some models emit source excerpts such as ``"x = \"a\" + value"`` with
    the inner source-code quote left unescaped.  A quote is preserved only when
    the next non-space character is a legal JSON delimiter; otherwise it is
    escaped so normal ``json.loads`` remains the final authority.
    """
    repaired: list[str] = []
    in_string = False
    escaped = False
    for index, character in enumerate(text):
        if not in_string:
            repaired.append(character)
            if character == '"':
                in_string = True
            continue
        if escaped:
            repaired.append(character)
            escaped = False
        elif character == "\\":
            repaired.append(character)
            escaped = True
        elif character == '"':
            if _is_json_string_terminator(text, index):
                repaired.append(character)
                in_string = False
            else:
                repaired.append('\\"')
        else:
            repaired.append(character)
    return "".join(repaired)


def parse_model_response(value: Any) -> tuple[dict[str, Any] | None, str, str, str | None]:
    """Parse model JSON from a response string or Ollama API envelope."""
    text, unwrap_error = _unwrap_ollama_response(value)
    if unwrap_error:
        return None, "empty" if value is None or value == "" else "invalid", "failed", unwrap_error
    assert text is not None

    errors: list[str] = []

    def try_candidate(candidate: str, *, allow_quote_repair: bool = False) -> dict[str, Any] | None:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError as exc:
            errors.append(f"{exc.msg} at line {exc.lineno}, column {exc.colno}")
            if not allow_quote_repair:
                return None
            repaired_candidate = _escape_unescaped_quotes_in_json_strings(candidate)
            if repaired_candidate == candidate:
                return None
            try:
                value = json.loads(repaired_candidate)
            except json.JSONDecodeError as repaired_exc:
                errors.append(f"After quote repair: {repaired_exc.msg} at line {repaired_exc.lineno}, column {repaired_exc.colno}")
                return None
        parsed, validation_error = _validate_structured_result(value)
        if validation_error:
            errors.append(validation_error)
        return parsed

    direct = try_candidate(text.strip())
    if direct is not None:
        return direct, "json", "success", None

    fenced_candidates = _markdown_fence_candidates(text)
    fenced_objects = [
        candidate
        for fenced_content in fenced_candidates
        for candidate in _balanced_json_candidates(fenced_content)
    ]
    fenced_results = [(candidate, try_candidate(candidate, allow_quote_repair=True)) for candidate in fenced_objects]
    valid_fenced = [item for item in fenced_results if item[1] is not None]
    if valid_fenced:
        _, parsed = max(valid_fenced, key=lambda item: len(item[0]))
        return parsed, "fenced_json", "success", None

    balanced_results = [(candidate, try_candidate(candidate, allow_quote_repair=True)) for candidate in _balanced_json_candidates(text)]
    valid_balanced = [item for item in balanced_results if item[1] is not None]
    if valid_balanced:
        _, parsed = max(valid_balanced, key=lambda item: len(item[0]))
        return parsed, "embedded_json", "success", None

    response_format = "fenced_json" if fenced_candidates else "malformed_json" if any(char in text for char in "{[") else "text"
    detail = "; ".join(dict.fromkeys(errors)) or "No valid structured JSON object was found."
    return None, response_format, "failed", detail


def run_local_parser_tests() -> bool:
    """Exercise response parsing only; this function never calls Ollama."""
    tests = [
        ("TEST 1", '{"definite_bugs":[],"suspected_bugs":[]}', "success", 0, 0),
        ("TEST 2", '''```json
{
  "definite_bugs": [],
  "suspected_bugs": []
}
```''', "success", 0, 0),
        ("TEST 3", '''Here is the result:

```json
{
  "definite_bugs": [
    {
      "title": "Division by zero"
    }
  ],
  "suspected_bugs": []
}
```''', "success", 1, 0),
        ("TEST 4", '''Some text before JSON.

{
"definite_bugs": [
{
"title": "Test bug"
}
],
"suspected_bugs": [
{
"title": "Possible bug"
}
]
}

Some text after JSON.''', "success", 1, 1),
        ("TEST 5", "This response contains no valid JSON.", "failed", None, None),
        ("TEST 6", '''The answer is:
```json
{
  "definite_bugs": [
    {
      "title": "Nested object test",
      "explanation": "Object contains { braces } inside a string"
    }
  ],
  "suspected_bugs": []
}
```''', "success", 1, 0),
        (
            "TEST 7",
            json.dumps({"model": "test", "response": '```\n{"definite_bugs": [], "suspected_bugs": []}\n```', "done": True}),
            "success",
            0,
            0,
        ),
    ]
    all_passed = True
    for name, response, expected_status, expected_definite, expected_suspected in tests:
        parsed, _, status, _ = parse_model_response(response)
        _, definite, suspected = _finding_counts(parsed)
        passed = (status, definite, suspected) == (expected_status, expected_definite, expected_suspected)
        print(f"{name}: {'PASS' if passed else 'FAIL'}")
        all_passed &= passed
    print(f"PARSER TESTS: {'PASS' if all_passed else 'FAIL'}")
    return all_passed


def run_failed_response_replay(result_path: Path = FAILED_RESPONSE_REPLAY_PATH) -> bool:
    """Replay the stored failed response locally; this never calls Ollama."""
    try:
        stored_result = json.loads(result_path.read_text(encoding="utf-8"))
        raw_response = stored_result["response"]["raw_response"]
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as exc:
        print(f"REAL FAILED RESPONSE REPLAY: FAIL ({type(exc).__name__}: {exc})")
        return False

    parsed, response_format, parse_status, parse_error = parse_model_response(raw_response)
    total, definite, suspected = _finding_counts(parsed)
    passed = (
        parse_status == "success"
        and parsed is not None
        and ("definite_bugs" in parsed or "suspected_bugs" in parsed)
    )
    print(f"Replay response format: {response_format}")
    print(f"Replay parse status: {parse_status}")
    if parse_error:
        print(f"Replay parse error: {parse_error}")
    print(f"Definite bugs: {definite}")
    print(f"Suspected bugs: {suspected}")
    print(f"Total findings: {total}")
    if parsed is not None:
        print("Finding titles:")
        for finding in parsed["definite_bugs"] + parsed["suspected_bugs"]:
            title = finding.get("title") if isinstance(finding, dict) else None
            print(f"- {title if title else '<untitled finding>'}")
    print(f"REAL FAILED RESPONSE REPLAY: {'PASS' if passed else 'FAIL'}")
    return passed


def request_ollama(host: str, model: str, prompt: str, timeout_seconds: float) -> tuple[str | None, int | None, str | None]:
    """Call local Ollama and preserve an HTTP error body when it is available."""
    endpoint = f"{host.rstrip('/')}/api/generate"
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode("utf-8")
    request = Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 -- local endpoint chosen by caller
            return response.read().decode("utf-8", errors="replace"), response.status, None
    except HTTPError as exc:
        return exc.read().decode("utf-8", errors="replace"), exc.code, f"HTTPError: {exc.code} {exc.reason}"
    except (URLError, TimeoutError, OSError) as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def _finding_counts(parsed_result: dict[str, Any] | None) -> tuple[int | None, int | None, int | None]:
    """Return null counts for any unparseable response, never a false zero."""
    if parsed_result is None:
        return None, None, None
    definite = len(parsed_result["definite_bugs"])
    suspected = len(parsed_result["suspected_bugs"])
    return definite + suspected, definite, suspected


def _flatten_findings(parsed_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Keep all model finding fields and make definite/suspected classification explicit."""
    if parsed_result is None:
        return []
    findings: list[dict[str, Any]] = []
    for classification, key in (("definite", "definite_bugs"), ("suspected", "suspected_bugs")):
        for finding in parsed_result[key]:
            if isinstance(finding, dict):
                findings.append({"classification": classification, **finding})
            else:
                findings.append({"classification": classification, "raw_finding": finding})
    return findings


def save_experiment(experiment: dict[str, Any], started_at: datetime) -> Path:
    """Persist exactly one complete standalone result without overwriting prior runs."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = started_at.strftime("%Y%m%dT%H%M%S%fZ")
    sequence = 0
    while True:
        suffix = "" if sequence == 0 else f"_{sequence}"
        output_path = RESULTS_DIR / f"qwen_experiment_{timestamp}{suffix}.json"
        try:
            with output_path.open("x", encoding="utf-8") as output_file:
                json.dump(experiment, output_file, indent=2, ensure_ascii=False)
            return output_path
        except FileExistsError:
            sequence += 1


def run_experiment(file_path: Path, host: str, model: str, timeout_seconds: float) -> dict[str, Any]:
    """Analyze one complete file; all errors remain isolated to this result."""
    started_at = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    result: dict[str, Any] = {
        "file": {
            "absolute_path": str(file_path.resolve()),
            "filename": file_path.name,
            "line_count": None,
            "character_count": None,
            "file_size_bytes": None,
        },
        "request": {"host": host, "endpoint": f"{host.rstrip('/')}/api/generate", "timeout_seconds": timeout_seconds, "prompt": None},
        "model": {"name": model, "prompt_eval_count": None, "eval_count": None, "total_duration": None, "load_duration": None, "prompt_eval_duration": None, "eval_duration": None},
        "timing": {"file_read_time_seconds": None, "request_started_at": None, "request_completed_at": None, "request_time_seconds": None, "total_time_seconds": None},
        "response": {"raw_response": None, "raw_ollama_api_response": None, "response_format": "unavailable", "parse_status": "not_attempted", "parse_error": None},
        "parsed_result": None,
        "findings": [],
        "summary": {"total_findings": None, "definite_bugs": None, "suspected_bugs": None},
        "error": None,
    }

    try:
        file_read_started = time.monotonic()
        source_bytes = file_path.read_bytes()
        source = source_bytes.decode("utf-8", errors="replace")
        result["timing"]["file_read_time_seconds"] = round(time.monotonic() - file_read_started, 6)
        result["file"].update({"line_count": len(source.splitlines()), "character_count": len(source), "file_size_bytes": len(source_bytes)})
        prompt = build_prompt(source)
        result["request"]["prompt"] = prompt
        result["request"]["prompt_characters"] = len(prompt)
        request_started = time.monotonic()
        result["timing"]["request_started_at"] = datetime.now(timezone.utc).isoformat()
        raw_api_response, http_status, request_error = request_ollama(host, model, prompt, timeout_seconds)
        result["timing"]["request_completed_at"] = datetime.now(timezone.utc).isoformat()
        result["timing"]["request_time_seconds"] = round(time.monotonic() - request_started, 6)
        result["request"]["http_status"] = http_status
        result["response"]["raw_ollama_api_response"] = raw_api_response
        if request_error:
            result["error"] = request_error
            return result
        if raw_api_response is None:
            result["error"] = "Ollama returned no HTTP response body."
            return result
        response = json.loads(raw_api_response)
        if not isinstance(response, dict):
            raise ValueError("Ollama returned a non-object JSON response.")
        raw_response = response.get("response")
        if not isinstance(raw_response, str):
            raise ValueError("Ollama response did not contain a string model response.")
        result["response"]["raw_response"] = raw_response
        result["response"]["response_characters"] = len(raw_response)
        for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
            result["model"][key] = response.get(key)
        parsed, response_format, parse_status, parse_error = parse_model_response(raw_response)
        result["response"].update({"response_format": response_format, "parse_status": parse_status, "parse_error": parse_error})
        result["parsed_result"] = parsed
        result["findings"] = _flatten_findings(parsed)
        total, definite, suspected = _finding_counts(parsed)
        result["summary"] = {"total_findings": total, "definite_bugs": definite, "suspected_bugs": suspected}
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        result["timing"]["total_time_seconds"] = round(time.monotonic() - started_monotonic, 6)
    return result


def print_comparison(results: list[dict[str, Any]]) -> None:
    """Print one comparison row per independently analyzed input file."""
    headers = ["File", "Lines", "Characters", "Time", "Findings", "Definite Bugs", "Suspected Bugs"]
    rows = []
    for result in results:
        summary = result["summary"]
        rows.append([
            result["file"]["filename"],
            str(result["file"]["line_count"] if result["file"]["line_count"] is not None else "N/A"),
            str(result["file"]["character_count"] if result["file"]["character_count"] is not None else "N/A"),
            f"{result['timing']['total_time_seconds']:.2f}s",
            str(summary["total_findings"] if summary["total_findings"] is not None else "unknown"),
            str(summary["definite_bugs"] if summary["definite_bugs"] is not None else "unknown"),
            str(summary["suspected_bugs"] if summary["suspected_bugs"] is not None else "unknown"),
        ])
    widths = [max(len(header), *(len(row[index]) for row in rows)) for index, header in enumerate(headers)]
    separator = "+".join("-" * (width + 2) for width in widths)
    format_row = lambda row: "|".join(f" {cell:<{widths[index]}} " for index, cell in enumerate(row))
    print("\nQWEN MULTI-FILE COMPARISON")
    print(separator)
    print(format_row(headers))
    print(separator)
    for row in rows:
        print(format_row(row))
    print(separator)


def print_file_summary(result: dict[str, Any]) -> None:
    """Print only concise per-file metrics; detailed evidence stays in JSON."""
    file_info = result["file"]
    summary = result["summary"]
    response = result["response"]
    print("\nQWEN SINGLE FILE EXPERIMENT")
    print(f"File: {file_info['filename']}")
    print(f"Lines: {file_info['line_count'] if file_info['line_count'] is not None else 'N/A'}")
    print(f"Characters: {file_info['character_count'] if file_info['character_count'] is not None else 'N/A'}")
    print(f"Model: {result['model']['name']}")
    print(f"Response received: {result['timing']['request_time_seconds'] if result['timing']['request_time_seconds'] is not None else 'N/A'}s")
    print(f"Response format: {response['response_format']}")
    print(f"Parse status: {response['parse_status'].upper()}")
    if result["error"]:
        print(f"  Error: {result['error']}")
    elif response["parse_status"] == "failed":
        print("WARNING: Qwen responded, but structured findings could not be parsed.")
        print("This is NOT a zero-bug result; the complete raw response is in the result JSON.")
    else:
        print(f"Findings: {summary['total_findings']}")
        print(f"Definite: {summary['definite_bugs']}")
        print(f"Suspected: {summary['suspected_bugs']}")


def build_experiment_payload(
    results: list[dict[str, Any]],
    started_at: datetime,
    total_time_seconds: float,
    model: str,
    host: str,
) -> dict[str, Any]:
    """Use the requested single-file shape, retaining multi-file support in one result."""
    experiment_metadata = {
        "timestamp": started_at.isoformat(),
        "model": model,
        "ollama_host": host,
        "total_files": len(results),
        "total_duration_seconds": total_time_seconds,
    }
    if len(results) == 1:
        result = results[0]
        return {
            "experiment": experiment_metadata,
            "file": result["file"],
            "request": result["request"],
            "model": result["model"],
            "timing": result["timing"],
            "response": result["response"],
            "parsed_result": result["parsed_result"],
            "findings": result["findings"],
            "summary": result["summary"],
            "error": result["error"],
        }

    summaries = [result["summary"] for result in results]
    counts_known = all(summary["total_findings"] is not None for summary in summaries)
    comparison = {
        "total_findings": sum(summary["total_findings"] for summary in summaries) if counts_known else None,
        "total_definite_bugs": sum(summary["definite_bugs"] for summary in summaries) if counts_known else None,
        "total_suspected_bugs": sum(summary["suspected_bugs"] for summary in summaries) if counts_known else None,
    }
    return {"experiment": experiment_metadata, "files": results, "comparison": comparison}


def main() -> int:
    parser = argparse.ArgumentParser(description="Standalone local-Qwen multi-file experiment.")
    parser.add_argument("files", nargs="*", type=Path, help="Source files to send independently and in full to local Qwen.")
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST))
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL))
    parser.add_argument("--timeout", type=float, default=1800, help="Local model request timeout in seconds.")
    parser.add_argument("--parser-tests", action="store_true", help="Run local parser tests without making an Ollama request.")
    parser.add_argument(
        "--replay-failed-result",
        action="store_true",
        help="Replay the stored failed response locally without making an Ollama request.",
    )
    args = parser.parse_args()
    if args.parser_tests:
        return 0 if run_local_parser_tests() else 1
    if args.replay_failed_result:
        return 0 if run_failed_response_replay() else 1
    if not args.files:
        parser.error("at least one source file is required unless --parser-tests is used")
    experiment_started_at = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    results: list[dict[str, Any]] = []
    for file_path in args.files:
        result = run_experiment(file_path, args.host, args.model, args.timeout)
        results.append(result)
        print_file_summary(result)
    experiment = build_experiment_payload(
        results,
        experiment_started_at,
        round(time.monotonic() - started_monotonic, 6),
        args.model,
        args.host,
    )
    output_path = save_experiment(experiment, experiment_started_at)
    if len(results) > 1:
        print_comparison(results)
    print(f"Detailed result saved: {output_path}")
    return 1 if any(result["error"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
