"""
source_context.py — Source Code Context Retrieval Service.
==========================================================
Safely extracts surrounding lines of code around candidate issue line numbers
from repository files on disk, without mutating state or crashing if files
are missing after temporary clones.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import tempfile

backend_dir = Path(__file__).resolve().parent.parent.parent
workspace_dir = backend_dir.parent

ALLOWED_ROOTS = [
    backend_dir.resolve(),
    workspace_dir.resolve(),
    (backend_dir / "repositories").resolve(),
    (workspace_dir / "repositories").resolve(),
    Path.cwd().resolve(),
    Path(tempfile.gettempdir()).resolve(),
]


def _is_allowed_path(path: Path) -> bool:
    """Ensure path resolves within workspace, repositories, or system temp dirs."""
    try:
        resolved = path.resolve()
        return any(root == resolved or root in resolved.parents for root in ALLOWED_ROOTS)
    except Exception:
        return False


def get_structured_source_context(
    file_path: str,
    line_number: Optional[int],
    context_lines: int = 15,
) -> Dict[str, Any]:
    """
    Retrieve structured source code context around a flagged line number.
    Returns dictionary with found status, formatted text, and line items.
    """
    if not file_path:
        return {
            "found": False,
            "message": "Source context unavailable: No file path recorded for this candidate issue.",
            "formatted_text": "[Notice] No file path recorded for this candidate issue.",
            "file_path": "",
            "line_number": line_number,
            "lines": [],
        }

    # Reject obvious traversal attempts before disk probing
    norm_path = file_path.replace("\\", "/")
    if norm_path.startswith(("/etc", "/root", "/var", "/usr", "/proc", "/sys")) or (len(norm_path) >= 2 and norm_path[1] == ":" and not any(str(r).lower() in str(Path(file_path).resolve()).lower() for r in ALLOWED_ROOTS)):
        target_path = None
    else:
        target_path = Path(file_path)

    if not target_path or not target_path.exists() or not _is_allowed_path(target_path):
        temp_base = Path(tempfile.gettempdir())
        temp_repo_paths = list(temp_base.glob(f"repo_*/{file_path}")) if file_path else []

        # Check standard relative search locations within project
        alt_paths = [
            backend_dir / file_path,
            workspace_dir / file_path,
            backend_dir / "repositories" / file_path,
            workspace_dir / "repositories" / file_path,
            Path.cwd() / file_path,
        ] + temp_repo_paths

        found_path = None
        for p in alt_paths:
            if p.exists() and p.is_file() and _is_allowed_path(p):
                found_path = p
                break
        if found_path:
            target_path = found_path
        else:
            return {
                "found": False,
                "message": (
                    "The original repository file is not currently available on disk. "
                    "The flagged code snippet above was retrieved from the persisted "
                    "PostgreSQL analysis record and can still be used to review this issue."
                ),
                "formatted_text": (
                    "[Notice] Source file not accessible on disk at '{file_path}'. "
                    "The persisted PostgreSQL code snippet can still be used for review."
                ),
                "file_path": file_path,
                "line_number": line_number,
                "lines": [],
            }

    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            raw_lines = f.readlines()

        if not raw_lines:
            return {
                "found": True,
                "message": "File is empty",
                "formatted_text": "[File is empty]",
                "file_path": str(target_path),
                "line_number": line_number,
                "lines": [],
            }

        total_lines = len(raw_lines)
        line_no = line_number if (line_number and line_number > 0) else 1
        start_line = max(1, line_no - context_lines)
        end_line = min(total_lines, line_no + context_lines)

        output_lines = []
        structured_lines: List[Dict[str, Any]] = []
        output_lines.append(f"--- Context: {target_path.name} (Lines {start_line}-{end_line} of {total_lines}) ---")

        for curr in range(start_line, end_line + 1):
            content = raw_lines[curr - 1].rstrip("\r\n")
            is_target = (curr == line_no)
            marker = ">" if is_target else " "
            output_lines.append(f"{marker} {curr:5d} | {content}")
            structured_lines.append({
                "line_number": curr,
                "content": content,
                "is_target": is_target,
            })
        output_lines.append("-" * 60)

        return {
            "found": True,
            "message": "Source context retrieved successfully",
            "formatted_text": "\n".join(output_lines),
            "file_path": str(target_path),
            "line_number": line_no,
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "lines": structured_lines,
        }
    except Exception as e:
        return {
            "found": False,
            "message": f"Error reading source file '{target_path}': {e}",
            "formatted_text": f"[Error reading source file '{target_path}': {e}]",
            "file_path": file_path,
            "line_number": line_number,
            "lines": [],
        }


def get_source_context(
    file_path: str,
    line_number: Optional[int],
    context_lines: int = 15,
) -> Tuple[bool, str]:
    """Compatibility tuple helper: returns (success, formatted_text)."""
    res = get_structured_source_context(file_path, line_number, context_lines)
    return res["found"], res["formatted_text"]
