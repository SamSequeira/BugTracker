"""
github_pr_bot.py
----------------
Feature 3: GitHub PR Analysis Bot.

Fetches a pull-request diff via the GitHub REST API, runs it through the
existing BugTracker analysis pipeline (static analysis + enrichment +
test harness), and posts a single structured comment on the PR.

The comment includes:
  • Root cause summary
  • Supporting evidence
  • Fix diff
  • AI Confidence
  • Validation Status (VERIFIED / UNVERIFIED)
  • Generated test pass/fail result

Auth: GITHUB_TOKEN env-var (personal access token or GitHub Actions token).
"""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

_GH_API = "https://api.github.com"


def _gh_headers(token: Optional[str] = None) -> Dict[str, str]:
    tok = token or os.environ.get("GITHUB_TOKEN", "")
    headers: Dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    return headers


def _parse_pr_url(pr_url: str) -> Tuple[str, str, int]:
    """
    Parse a GitHub PR URL into (owner, repo, pr_number).

    Accepts:
      https://github.com/owner/repo/pull/42
      https://github.com/owner/repo/pulls/42
    """
    m = re.search(r"github\.com/([^/]+)/([^/]+)/pulls?/(\d+)", pr_url)
    if not m:
        raise ValueError(
            f"Cannot parse PR URL: {pr_url!r}. "
            "Expected format: https://github.com/owner/repo/pull/<number>"
        )
    return m.group(1), m.group(2), int(m.group(3))


# ---------------------------------------------------------------------------
# Core bot logic
# ---------------------------------------------------------------------------

class GitHubPRBot:
    """
    Analyses a GitHub pull request and posts a structured review comment.
    """

    def __init__(self, github_token: Optional[str] = None) -> None:
        self._token = github_token or os.environ.get("GITHUB_TOKEN", "")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse_and_comment(
        self,
        pr_url: Optional[str] = None,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        pr_number: Optional[int] = None,
        post_comment: bool = True,
    ) -> Dict[str, Any]:
        """
        Main entry point.

        Either supply ``pr_url`` OR (``owner`` + ``repo`` + ``pr_number``).
        Returns a dict with keys: comment_body, reports, posted.
        """
        import urllib.request, urllib.error, json

        if pr_url:
            owner, repo, pr_number = _parse_pr_url(pr_url)

        if not (owner and repo and pr_number):
            raise ValueError(
                "Supply either pr_url or all of owner, repo, pr_number."
            )

        # 1. Fetch the PR diff
        diff_text = self._fetch_pr_diff(owner, repo, pr_number)

        # 2. Extract changed/added Python/JS files from the diff
        changed_files = self._extract_changed_files_from_diff(diff_text)

        # 3. Run analysis on each changed file (using the existing pipeline)
        all_reports: List[Dict[str, Any]] = []
        if changed_files:
            all_reports = self._analyse_diff_files(changed_files, diff_text)

        # 4. Build comment
        pr_meta = self._fetch_pr_meta(owner, repo, pr_number)
        comment_body = self._build_comment(
            pr_meta=pr_meta,
            reports=all_reports,
            diff_text=diff_text,
        )

        # 5. Post the comment
        posted = False
        if post_comment and self._token:
            posted = self._post_comment(owner, repo, pr_number, comment_body)
        elif post_comment and not self._token:
            logger.warning(
                "GITHUB_TOKEN not set — comment generated but not posted."
            )

        return {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "reports": all_reports,
            "comment_body": comment_body,
            "posted": posted,
        }

    # ------------------------------------------------------------------
    # GitHub REST calls (stdlib urllib, no requests dependency)
    # ------------------------------------------------------------------

    def _fetch_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        import urllib.request, urllib.error

        url = f"{_GH_API}/repos/{owner}/{repo}/pulls/{pr_number}"
        req = urllib.request.Request(
            url,
            headers={**_gh_headers(self._token), "Accept": "application/vnd.github.v3.diff"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"GitHub API error fetching diff for {owner}/{repo}#{pr_number}: "
                f"HTTP {exc.code} — {exc.reason}"
            ) from exc

    def _fetch_pr_meta(self, owner: str, repo: str, pr_number: int) -> Dict[str, Any]:
        import urllib.request, urllib.error, json

        url = f"{_GH_API}/repos/{owner}/{repo}/pulls/{pr_number}"
        req = urllib.request.Request(url, headers=_gh_headers(self._token))
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            logger.warning("Could not fetch PR metadata: %s", exc)
            return {"title": f"PR #{pr_number}", "html_url": ""}

    def _post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> bool:
        import urllib.request, urllib.error, json

        url = f"{_GH_API}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        payload = json.dumps({"body": body}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={**_gh_headers(self._token), "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.status in (200, 201)
        except Exception as exc:
            logger.error("Failed to post PR comment: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Diff parsing & file extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_changed_files_from_diff(diff_text: str) -> List[Dict[str, str]]:
        """
        Parse a unified diff and extract changed file names + their content hunks.
        Supports Python (.py) and JavaScript (.js / .ts) files.
        """
        SUPPORTED_EXTS = {".py", ".js", ".ts", ".jsx", ".tsx"}
        files: List[Dict[str, str]] = []
        current_file: Optional[str] = None
        current_lines: List[str] = []

        for line in diff_text.splitlines():
            if line.startswith("+++ b/"):
                if current_file and current_lines:
                    files.append({"path": current_file, "content": "\n".join(current_lines)})
                    current_lines = []
                path = line[6:].strip()
                ext = Path(path).suffix.lower()
                current_file = path if ext in SUPPORTED_EXTS else None
            elif current_file:
                # Collect added lines (strip the leading '+')
                if line.startswith("+") and not line.startswith("+++"):
                    current_lines.append(line[1:])
                elif not line.startswith("-") and not line.startswith("\\") and not line.startswith("@@"):
                    current_lines.append(line.lstrip(" "))

        if current_file and current_lines:
            files.append({"path": current_file, "content": "\n".join(current_lines)})

        return files

    # ------------------------------------------------------------------
    # Pipeline execution on extracted diff content
    # ------------------------------------------------------------------

    def _analyse_diff_files(
        self,
        changed_files: List[Dict[str, str]],
        diff_text: str,
    ) -> List[Dict[str, Any]]:
        """
        Write diff content to temp files, run static analysis + enrichment,
        return serialised bug reports.
        """
        from app.services.static_analyzer.analyzer import static_analyzer
        from app.services.ast_generator import ast_generator
        from app.services.bug_report_service import bug_report_service

        all_reports: List[Dict[str, Any]] = []

        with tempfile.TemporaryDirectory(prefix="bt_pr_") as tmpdir:
            tmp_path = Path(tmpdir)

            # Write each changed file to temp dir
            written: List[str] = []
            for cf in changed_files:
                dest = tmp_path / Path(cf["path"]).name
                try:
                    dest.write_text(cf["content"], encoding="utf-8")
                    written.append(str(dest))
                except Exception as exc:
                    logger.warning("Could not write temp file for %s: %s", cf["path"], exc)

            if not written:
                return []

            # Run AST + static analysis on the temp directory
            try:
                ast_result = ast_generator.generate_ast_for_repository(str(tmp_path))
                # Generate enriched bug reports via existing pipeline
                result = bug_report_service.generate_repository_reports(
                    ast_result=ast_result,
                    repository_id="pr_analysis",
                    repository_path=str(tmp_path),
                )
                raw_reports = result.get("bug_reports", [])
                for r in raw_reports:
                    if isinstance(r, dict):
                        all_reports.append(r)
                    elif hasattr(r, "model_dump"):
                        all_reports.append(r.model_dump(mode="json"))
            except Exception as exc:
                logger.exception("Pipeline execution failed for PR diff: %s", exc)

        return all_reports

    # ------------------------------------------------------------------
    # Comment builder
    # ------------------------------------------------------------------

    def _build_comment(
        self,
        pr_meta: Dict[str, Any],
        reports: List[Dict[str, Any]],
        diff_text: str,
    ) -> str:
        pr_title = pr_meta.get("title", "Pull Request")
        pr_url = pr_meta.get("html_url", "")

        lines = [
            "## 🤖 BugTracker Static Analysis Report",
            "",
            f"> **PR:** [{pr_title}]({pr_url})",
            f"> **Issues found:** {len(reports)}",
            "",
        ]

        if not reports:
            lines += [
                "✅ **No issues detected** in the changed files.",
                "",
                "_Static analysis, AST parsing, and ML triage found no candidate bugs in this diff._",
            ]
            return "\n".join(lines)

        # Summary table
        critical = sum(1 for r in reports if str(r.get("severity", "")).lower() == "critical")
        high = sum(1 for r in reports if str(r.get("severity", "")).lower() == "high")
        medium = sum(1 for r in reports if str(r.get("severity", "")).lower() == "medium")
        low = sum(1 for r in reports if str(r.get("severity", "")).lower() == "low")
        verified = sum(1 for r in reports if r.get("validation_status") == "VERIFIED")

        lines += [
            "### Summary",
            "",
            "| Severity | Count |",
            "|----------|-------|",
            f"| 🔴 Critical | {critical} |",
            f"| 🟠 High | {high} |",
            f"| 🟡 Medium | {medium} |",
            f"| 🔵 Low | {low} |",
            f"| ✅ Verified by test harness | {verified} |",
            "",
            "---",
            "",
            "### Detailed Findings",
            "",
        ]

        for idx, r in enumerate(reports, start=1):
            bug_id = r.get("id") or r.get("issue_id", f"BUG-{idx:04d}")
            title = r.get("title", "Issue Detected")
            sev = str(r.get("severity", "medium")).upper()
            prio = r.get("priority_formatted") or str(r.get("priority", "P3")).upper()
            file_p = r.get("file_path") or r.get("file", "unknown")
            line_n = r.get("line", 0)
            static = r.get("static_analysis", {})
            rule_id = static.get("rule_id", "N/A") if isinstance(static, dict) else "N/A"
            fix = r.get("suggestedFix") or r.get("suggested_fix") or {}
            if not isinstance(fix, dict):
                fix = {}
            exp = r.get("explanation") or {}
            if not isinstance(exp, dict):
                exp = {}
            ai_conf = float(r.get("ai_confidence", r.get("confidence", 1.0)))
            val_status = r.get("validation_status", "UNVERIFIED")
            val_icon = "✅" if val_status == "VERIFIED" else "⏳"

            # Root cause from explanation
            what = exp.get("what") or r.get("description", "")
            evidence_summary = exp.get("evidence_summary", "")

            # Test harness result
            harness = r.get("test_harness_result") or {}
            if not isinstance(harness, dict):
                harness = {}
            harness_line = ""
            if harness.get("validated"):
                pre_ok = "FAIL ✓" if harness.get("pre_fix_passed") is False else "—"
                post_ok = "PASS ✓" if harness.get("post_fix_passed") else "—"
                harness_line = f"| **Test Harness** | pre-fix: `{pre_ok}` → post-fix: `{post_ok}` |"
            elif harness.get("error"):
                harness_line = f"| **Test Harness** | ⚠ {harness.get('error', '')[:120]} |"
            else:
                harness_line = f"| **Test Harness** | Not executed |"

            lines += [
                f"#### {idx}. `{bug_id}` — {title}",
                "",
                f"| Field | Value |",
                f"|-------|-------|",
                f"| **Severity** | `{sev}` |",
                f"| **Priority** | `{prio}` |",
                f"| **Location** | `{file_p}:{line_n}` |",
                f"| **Rule** | `{rule_id}` |",
                f"| **AI Confidence** | `{ai_conf:.0%}` |",
                f"| **Validation** | {val_icon} `{val_status}` |",
                harness_line,
                "",
            ]

            # Root cause
            if what:
                lines += [
                    f"**Root Cause:**",
                    f"> {what}",
                    "",
                ]

            # Evidence
            if evidence_summary:
                lines += [
                    f"**Evidence:**",
                    f"> {evidence_summary}",
                    "",
                ]

            # Fix diff
            fix_add = fix.get("add", "")
            fix_rem = fix.get("remove", "")
            fix_note = fix.get("note", "")
            if fix_rem or fix_add:
                lines += [
                    "**Suggested Fix:**",
                    "```diff",
                ]
                if fix_rem:
                    lines.append(fix_rem)
                if fix_add:
                    lines.append(fix_add)
                lines += ["```", ""]
            if fix_note:
                lines += [f"_{fix_note}_", ""]

            # Generated test
            harness_src = (harness.get("generated_test_source") or "")[:800]
            if harness_src and harness_src.strip():
                lang_tag = "python" if r.get("language", "").lower() == "python" else "javascript"
                lines += [
                    "<details>",
                    f"<summary>📋 Generated Regression Test</summary>",
                    "",
                    f"```{lang_tag}",
                    harness_src.strip(),
                    "```",
                    "</details>",
                    "",
                ]

            lines.append("---")
            lines.append("")

        lines += [
            "<sub>Generated by [BugTracker](https://github.com/your-org/bugtracker) — "
            "AI-assisted static analysis & triage platform.</sub>",
        ]

        return "\n".join(lines)


# Global singleton
github_pr_bot = GitHubPRBot()
