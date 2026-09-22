"""
report_exporter.py
------------------
Multi-format Bug Report Exporter.
Supports generating downloadable reports in PDF, CSV, JSON, Markdown (MD), and HTML.
Zero external dependencies — uses Python standard library for robust, high-performance exports.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union


class ReportExporter:
    """
    Exports bug reports into various file formats (PDF, CSV, JSON, Markdown, HTML).
    """

    SUPPORTED_FORMATS = {"pdf", "csv", "json", "md", "markdown", "html"}

    # =========================================================================
    # PUBLIC EXPORT DISPATCHER
    # =========================================================================

    def export(
        self,
        reports: List[Union[Dict[str, Any], Any]],
        format_type: str = "pdf",
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, str, str]:
        """
        Export bug reports to specified format.

        Returns:
            Tuple of (file_content_bytes, media_type, filename)
        """
        fmt = format_type.strip().lower()
        if fmt not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported export format '{format_type}'. "
                f"Supported formats are: {', '.join(sorted(self.SUPPORTED_FORMATS))}"
            )

        repo_name = (repo_info.get("name") if repo_info else None) or "BugReport"
        safe_repo_name = re.sub(r"[^\w\-]", "_", repo_name)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Normalize reports to dicts
        dict_reports = [self._to_dict(r) for r in reports]

        if fmt == "csv":
            content = self.export_csv(dict_reports, summary_stats, repo_info)
            media_type = "text/csv; charset=utf-8"
            filename = f"{safe_repo_name}_bugs_{timestamp}.csv"
        elif fmt == "json":
            content = self.export_json(dict_reports, summary_stats, repo_info)
            media_type = "application/json"
            filename = f"{safe_repo_name}_bugs_{timestamp}.json"
        elif fmt in ("md", "markdown"):
            content = self.export_markdown(dict_reports, summary_stats, repo_info)
            media_type = "text/markdown; charset=utf-8"
            filename = f"{safe_repo_name}_bugs_{timestamp}.md"
        elif fmt == "html":
            content = self.export_html(dict_reports, summary_stats, repo_info)
            media_type = "text/html; charset=utf-8"
            filename = f"{safe_repo_name}_bugs_{timestamp}.html"
        elif fmt == "pdf":
            content = self.export_pdf(dict_reports, summary_stats, repo_info)
            media_type = "application/pdf"
            filename = f"{safe_repo_name}_bugs_{timestamp}.pdf"
        else:
            raise ValueError(f"Unhandled format: {fmt}")

        return content, media_type, filename

    # =========================================================================
    # 1. CSV EXPORT
    # =========================================================================

    def export_csv(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate UTF-8 CSV with BOM for universal Excel compatibility."""
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header Row
        writer.writerow([
            "Bug ID",
            "Title",
            "Severity",
            "Priority",
            "Category",
            "File Path",
            "Line",
            "Column",
            "Function",
            "Class",
            "Language",
            "Rule ID",
            "Confidence",
            "Status",
            "Duplicate Of",
            "Similar Issues Count",
            "Description",
            "Remediation Note",
        ])

        for r in reports:
            loc = r.get("location", {})
            static = r.get("static_analysis", {})
            sim = r.get("similarity", {})
            fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}

            writer.writerow([
                r.get("id") or r.get("issue_id", ""),
                r.get("title", ""),
                str(r.get("severity", "")).upper(),
                r.get("priority_formatted") or str(r.get("priority", "")).upper(),
                r.get("category", ""),
                r.get("file_path") or r.get("file", ""),
                loc.get("line") or r.get("line", ""),
                loc.get("column") or r.get("column", 0),
                r.get("function_name", "") or "",
                r.get("class_name", "") or "",
                r.get("language", ""),
                static.get("rule_id", ""),
                f"{float(r.get('confidence', 1.0)):.2f}",
                r.get("status", "Open"),
                sim.get("duplicate_of") or r.get("duplicate_of") or "",
                len(sim.get("similar_issues", []) or r.get("similar_issues", [])),
                r.get("description", ""),
                fix.get("note", ""),
            ])

        # Encode with UTF-8 BOM so Excel opens special characters cleanly
        return output.getvalue().encode("utf-8-sig")

    # =========================================================================
    # 2. JSON EXPORT
    # =========================================================================

    def export_json(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate structured JSON document."""
        data = {
            "metadata": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "generator": "AI Bug Tracker & Triage System",
                "repository": repo_info or {},
                "total_bugs": len(reports),
            },
            "summary_stats": summary_stats or self._calculate_quick_stats(reports),
            "bug_reports": reports,
        }
        return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    # =========================================================================
    # 3. MARKDOWN EXPORT
    # =========================================================================

    def export_markdown(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate GitHub-Flavored Markdown report."""
        stats = summary_stats or self._calculate_quick_stats(reports)
        repo_name = (repo_info.get("name") if repo_info else None) or "Repository"
        repo_path = (repo_info.get("path") if repo_info else None) or "N/A"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"# Bug Triage & Security Audit Report",
            f"",
            f"**Repository:** `{repo_name}`  ",
            f"**Path:** `{repo_path}`  ",
            f"**Generated:** `{date_str}`  ",
            f"**Total Issues Detected:** `{len(reports)}`  ",
            f"",
            f"---",
            f"",
            f"## Executive Summary",
            f"",
            f"| Metric | Count | Priority Breakdown | Count |",
            f"| :--- | :--- | :--- | :--- |",
            f"| **Total Bugs** | **{stats.get('total_bugs', len(reports))}** | **P1 (Fix now)** | {stats.get('priority_p1', 0)} |",
            f"| **High** | {stats.get('high', 0)} | **P2 (Fix this week)** | {stats.get('priority_p2', 0)} |",
            f"| **Medium** | {stats.get('medium', 0)} | **P3 (Backlog)** | {stats.get('priority_p3', 0)} |",
            f"| **Low** | {stats.get('low', 0)} | **P4 (Low)** | {stats.get('priority_p4', 0)} |",
            f"| **Duplicates** | {stats.get('duplicates_count', 0)} | | |",
            f"",
            f"---",
            f"",
            f"## Detailed Bug Reports",
            f"",
        ]

        if not reports:
            lines.append("No issues detected in codebase. Clean scan!")
        else:
            for idx, r in enumerate(reports, start=1):
                bug_id = r.get("id") or r.get("issue_id", f"BUG-{idx:04d}")
                title = r.get("title", "Issue Detected")
                sev = str(r.get("severity", "medium")).upper()
                prio = r.get("priority_formatted") or str(r.get("priority", "P3")).upper()
                file_p = r.get("file_path") or r.get("file", "unknown")
                line_n = r.get("line", 0)
                scope = self._format_scope(r)
                static = r.get("static_analysis", {})
                rule_id = static.get("rule_id", "N/A")
                fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}
                exp = r.get("explanation", {})

                lines.extend([
                    f"### {idx}. [{bug_id}] {title}",
                    f"",
                    f"- **Severity:** `{sev}` | **Priority:** `{prio}` | **Status:** `{r.get('status', 'Open')}`",
                    f"- **Location:** `{file_p}:{line_n}` in `{scope}`",
                    f"- **Rule Triggered:** `{rule_id}` ({r.get('category', 'general')})",
                    f"",
                    f"**Description:**  ",
                    f"{r.get('description', '')}",
                    f"",
                ])

                # Code Snippet if available
                snippet = static.get("code_snippet") or r.get("code_snippet")
                if snippet:
                    lang = str(r.get("language", "")).lower()
                    lines.extend([
                        f"```python" if lang == "python" else f"```{lang}",
                        f"# Line {line_n}:",
                        f"{snippet}",
                        f"```",
                        f"",
                    ])

                # Suggested Fix if available
                if fix and (fix.get("note") or fix.get("add")):
                    lines.append(f"**Remediation:**  ")
                    if fix.get("note"):
                        lines.append(f"{fix.get('note')}  ")
                    if fix.get("add"):
                        lines.extend([
                            f"```diff",
                            f"{fix.get('remove') or ''}",
                            f"{fix.get('add') or ''}",
                            f"```",
                        ])
                    lines.append("")

                lines.append("---")
                lines.append("")

        return "\n".join(lines).encode("utf-8")

    # =========================================================================
    # 4. HTML EXPORT
    # =========================================================================

    def export_html(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate modern, standalone responsive HTML report with print styles."""
        stats = summary_stats or self._calculate_quick_stats(reports)
        repo_name = (repo_info.get("name") if repo_info else None) or "Repository"
        repo_path = (repo_info.get("path") if repo_info else None) or "N/A"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        cards_html = []
        for idx, r in enumerate(reports, start=1):
            bug_id = r.get("id") or r.get("issue_id", f"BUG-{idx:04d}")
            title = r.get("title", "Issue Detected")
            sev = str(r.get("severity", "medium")).lower()
            prio = r.get("priority_formatted") or str(r.get("priority", "P3")).upper()
            file_p = r.get("file_path") or r.get("file", "")
            line_n = r.get("line", 0)
            static = r.get("static_analysis", {})
            rule_id = static.get("rule_id", "")
            fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}
            snippet = static.get("code_snippet") or r.get("code_snippet", "")

            sev_color = {
                "critical": "#ef4444",
                "high": "#f97316",
                "medium": "#eab308",
                "low": "#3b82f6",
            }.get(sev, "#94a3b8")

            fix_html = ""
            if fix.get("note"):
                fix_html = f"""
                <div class="fix-box">
                    <strong>Remediation:</strong> {fix.get('note')}
                </div>
                """

            snippet_html = ""
            if snippet:
                snippet_html = f"""
                <pre class="code-block"><code># Line {line_n}: {snippet}</code></pre>
                """

            cards_html.append(f"""
            <div class="bug-card">
                <div class="card-header">
                    <div>
                        <span class="bug-id">{bug_id}</span>
                        <h3 class="bug-title">{title}</h3>
                    </div>
                    <div class="badges">
                        <span class="badge" style="background: {sev_color}20; color: {sev_color}; border: 1px solid {sev_color}60;">{sev.upper()}</span>
                        <span class="badge prio-badge">{prio}</span>
                    </div>
                </div>
                <div class="card-meta">
                    <span><strong>Location:</strong> <code>{file_p}:{line_n}</code></span>
                    <span><strong>Rule:</strong> <code>{rule_id}</code></span>
                    <span><strong>Category:</strong> {r.get('category', '')}</span>
                </div>
                <p class="bug-desc">{r.get('description', '')}</p>
                {snippet_html}
                {fix_html}
            </div>
            """)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bug Triage Report - {repo_name}</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --accent: #6366f1;
        }}
        @media print {{
            body {{ background: #fff !important; color: #000 !important; font-size: 12pt; }}
            .bug-card {{ page-break-inside: avoid; border: 1px solid #ccc !important; background: #fff !important; color: #000 !important; }}
            .btn-print {{ display: none; }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 30px 20px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; }}
        h1 {{ margin: 0 0 8px 0; font-size: 26px; color: #fff; }}
        .meta-text {{ color: var(--text-muted); font-size: 14px; margin: 2px 0; }}
        .btn-print {{ background: var(--accent); color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-bottom: 30px; }}
        .stat-box {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px; text-align: center; }}
        .stat-val {{ font-size: 24px; font-weight: bold; margin-bottom: 4px; }}
        .stat-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
        .bug-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 18px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
        .bug-id {{ font-size: 12px; font-weight: bold; color: var(--accent); font-family: monospace; }}
        .bug-title {{ margin: 4px 0 0 0; font-size: 18px; }}
        .badges {{ display: flex; gap: 8px; }}
        .badge {{ padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
        .prio-badge {{ background: #334155; color: #f1f5f9; }}
        .card-meta {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--text-muted); margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }}
        .bug-desc {{ margin: 0 0 14px 0; font-size: 14px; color: #cbd5e1; }}
        .code-block {{ background: #0b1120; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 13px; overflow-x: auto; color: #38bdf8; margin: 10px 0; }}
        .fix-box {{ background: #064e3b30; border-left: 4px solid #10b981; padding: 10px 14px; font-size: 13px; border-radius: 0 6px 6px 0; color: #a7f3d0; margin-top: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Bug Triage & Security Audit Report</h1>
                <p class="meta-text"><strong>Repository:</strong> {repo_name} ({repo_path})</p>
                <p class="meta-text"><strong>Generated:</strong> {date_str} | <strong>Total Issues:</strong> {len(reports)}</p>
            </div>
            <button class="btn-print" onclick="window.print()">Print / Save PDF</button>
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-val" style="color: #6366f1;">{stats.get('total_bugs', len(reports))}</div>
                <div class="stat-label">Total Bugs</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #f97316;">{stats.get('high', 0)}</div>
                <div class="stat-label">High</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #eab308;">{stats.get('medium', 0)}</div>
                <div class="stat-label">Medium</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #3b82f6;">{stats.get('low', 0)}</div>
                <div class="stat-label">Low</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #a855f7;">{stats.get('duplicates_count', 0)}</div>
                <div class="stat-label">Duplicates</div>
            </div>
        </div>

        <div class="bug-list">
            {"".join(cards_html) if cards_html else "<p>No bugs detected.</p>"}
        </div>
    </div>
</body>
</html>"""
        return html.encode("utf-8")

    # =========================================================================
    # 5. PDF EXPORT (Pure Python Standards-Compliant PDF 1.4)
    # =========================================================================

    def export_pdf(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate high-quality multi-page PDF document without external binaries."""
        stats = summary_stats or self._calculate_quick_stats(reports)
        repo_name = (repo_info.get("name") if repo_info else None) or "Repository"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        pdf = _PDFCanvas()

        # Page 1: Title & Executive Summary
        pdf.new_page()
        pdf.draw_header("BUG TRIAGE & SECURITY AUDIT REPORT", repo_name, date_str)

        # Summary Metrics Box
        pdf.draw_summary_box(
            total=stats.get("total_bugs", len(reports)),
            critical=stats.get("critical", 0),
            high=stats.get("high", 0),
            medium=stats.get("medium", 0),
            low=stats.get("low", 0),
            p1=stats.get("priority_p1", 0),
            p2=stats.get("priority_p2", 0),
            p3=stats.get("priority_p3", 0),
        )

        pdf.add_y_offset(20)
        pdf.draw_section_title("Detailed Findings")

        if not reports:
            pdf.draw_text("No issues detected in codebase. Repository scan is clean.", font_size=11)
        else:
            for idx, r in enumerate(reports, start=1):
                # Ensure space on page, else break
                if pdf.y_pos < 160:
                    pdf.new_page()
                    pdf.draw_header("BUG TRIAGE & AUDIT REPORT (CONT.)", repo_name, date_str)

                bug_id = r.get("id") or r.get("issue_id", f"BUG-{idx:04d}")
                title = r.get("title", "Issue Detected")
                sev = str(r.get("severity", "medium")).upper()
                prio = r.get("priority_formatted") or str(r.get("priority", "P3")).upper()
                file_p = r.get("file_path") or r.get("file", "unknown")
                line_n = r.get("line", 0)
                static = r.get("static_analysis", {})
                rule_id = static.get("rule_id", "N/A")
                fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}
                desc = r.get("description", "")
                snippet = static.get("code_snippet") or r.get("code_snippet", "")

                pdf.draw_bug_entry(
                    index=idx,
                    bug_id=bug_id,
                    title=title,
                    severity=sev,
                    priority=prio,
                    file_path=f"{file_p}:{line_n}",
                    rule_id=rule_id,
                    description=desc,
                    snippet=snippet,
                    fix_note=fix.get("note", ""),
                )

        return pdf.render()

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _to_dict(report: Any) -> Dict[str, Any]:
        if hasattr(report, "model_dump"):
            return report.model_dump(mode="json")
        if hasattr(report, "to_dict"):
            return report.to_dict()
        if isinstance(report, dict):
            return dict(report)
        return getattr(report, "__dict__", {})

    @staticmethod
    def _format_scope(r: Dict[str, Any]) -> str:
        cls = r.get("class_name")
        fn = r.get("function_name")
        if cls and fn:
            return f"{cls}.{fn}()"
        if fn:
            return f"{fn}()"
        if cls:
            return f"class {cls}"
        return "top-level module"

    @staticmethod
    def _calculate_quick_stats(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        stats = {
            "total_bugs": len(reports),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "priority_p1": 0,
            "priority_p2": 0,
            "priority_p3": 0,
            "priority_p4": 0,
            "duplicates_count": 0,
        }
        for r in reports:
            sev = str(r.get("severity", "medium")).lower()
            if sev in stats:
                stats[sev] += 1
            prio = str(r.get("priority", "p3")).lower()
            if f"priority_{prio}" in stats:
                stats[f"priority_{prio}"] += 1
            sim = r.get("similarity", {})
            if sim.get("is_duplicate") or r.get("duplicate_of"):
                stats["duplicates_count"] += 1
        return stats


# =============================================================================
# LIGHTWEIGHT PURE-PYTHON PDF 1.4 GENERATOR
# =============================================================================

class _PDFCanvas:
    """Lightweight vector PDF 1.4 canvas for report generation."""

    def __init__(self, width: float = 612, height: float = 792):
        self.width = width
        self.height = height
        self.pages_ops: List[List[str]] = []
        self.current_ops: List[str] = []
        self.y_pos = height - 50

    def new_page(self):
        if self.current_ops:
            self.pages_ops.append(self.current_ops)
        self.current_ops = []
        self.y_pos = self.height - 50

    def add_y_offset(self, offset: float):
        self.y_pos -= offset

    def draw_header(self, main_title: str, sub_title: str, date_str: str):
        # Top banner line
        self.current_ops.append("0.2 0.3 0.6 RG 2 w 50 745 m 562 745 l S")
        # Main Title
        self._text(main_title, 50, 755, font="/F2", size=16, r=0.1, g=0.15, b=0.3)
        # Subtitle & Date
        self._text(f"Repository: {self._sanitize(sub_title)} | Generated: {date_str}", 50, 730, font="/F1", size=9, r=0.4, g=0.4, b=0.4)
        self.y_pos = 710

    def draw_section_title(self, title: str):
        self._text(title, 50, self.y_pos, font="/F2", size=13, r=0.15, g=0.2, b=0.4)
        self.y_pos -= 16

    def draw_summary_box(self, total: int, critical: int, high: int, medium: int, low: int, p1: int, p2: int, p3: int):
        box_top = self.y_pos
        box_h = 55
        # Background box
        self.current_ops.append(f"0.95 0.96 0.98 rg 50 {box_top - box_h} 512 {box_h} re f")
        self.current_ops.append(f"0.8 0.85 0.9 RG 1 w 50 {box_top - box_h} 512 {box_h} re S")

        # Metric text
        self._text("SUMMARY METRICS", 62, box_top - 16, font="/F2", size=9, r=0.3, g=0.35, b=0.5)
        stats_line = f"Total Bugs: {total}   |   High: {high}   |   Medium: {medium}   |   Low: {low}"
        self._text(stats_line, 62, box_top - 32, font="/F2", size=10, r=0.1, g=0.1, b=0.1)
        prio_line = f"Triage Priority ->  P1 (Immediate): {p1}   |   P2 (High): {p2}   |   P3 (Normal): {p3}"
        self._text(prio_line, 62, box_top - 46, font="/F1", size=9, r=0.4, g=0.4, b=0.4)

        self.y_pos = box_top - box_h - 10

    def draw_bug_entry(
        self,
        index: int,
        bug_id: str,
        title: str,
        severity: str,
        priority: str,
        file_path: str,
        rule_id: str,
        description: str,
        snippet: str,
        fix_note: str,
    ):
        start_y = self.y_pos
        
        # Color coding for severity
        if severity == "CRITICAL":
            r, g, b = 0.85, 0.1, 0.1
        elif severity == "HIGH":
            r, g, b = 0.9, 0.4, 0.0
        elif severity == "MEDIUM":
            r, g, b = 0.8, 0.6, 0.0
        else:
            r, g, b = 0.2, 0.5, 0.8

        # Card Title Line
        header_text = f"{index}. [{bug_id}] {self._sanitize(title)}"
        self._text(header_text[:75], 50, start_y, font="/F2", size=11, r=0.1, g=0.1, b=0.2)
        
        # Badges
        badge_text = f"[{severity}] [{priority}]"
        self._text(badge_text, 440, start_y, font="/F2", size=9, r=r, g=g, b=b)
        start_y -= 14

        # Location & Rule
        meta_text = f"Location: {self._sanitize(file_path)}  |  Rule: {rule_id}"
        self._text(meta_text[:90], 50, start_y, font="/F1", size=9, r=0.4, g=0.4, b=0.4)
        start_y -= 13

        # Description (wrapped)
        desc_clean = self._sanitize(description)
        for line in self._wrap_text(desc_clean, 85)[:2]:
            self._text(line, 50, start_y, font="/F1", size=9, r=0.2, g=0.2, b=0.2)
            start_y -= 11

        # Code snippet if present
        if snippet:
            snip_clean = self._sanitize(snippet.strip().replace("\n", " "))
            self.current_ops.append(f"0.92 0.94 0.97 rg 50 {start_y - 12} 512 14 re f")
            self._text(f"Code: {snip_clean[:80]}", 56, start_y - 9, font="/F3", size=8, r=0.1, g=0.2, b=0.5)
            start_y -= 18

        # Fix note if present
        if fix_note:
            note_clean = self._sanitize(fix_note)
            self._text(f"Remediation: {note_clean[:85]}", 50, start_y, font="/F1", size=8, r=0.05, g=0.5, b=0.2)
            start_y -= 12

        # Separator line
        self.current_ops.append(f"0.88 0.88 0.88 RG 0.5 w 50 {start_y} m 562 {start_y} l S")
        start_y -= 14
        self.y_pos = start_y

    def draw_text(self, text: str, font_size: float = 10):
        self._text(self._sanitize(text), 50, self.y_pos, font="/F1", size=font_size, r=0.2, g=0.2, b=0.2)
        self.y_pos -= (font_size + 4)

    def _text(self, text: str, x: float, y: float, font: str = "/F1", size: float = 10, r: float = 0, g: float = 0, b: float = 0):
        safe = self._sanitize(text)
        op = f"BT {r} {g} {b} rg {font} {size} Tf {x:.1f} {y:.1f} Td ({safe}) Tj ET"
        self.current_ops.append(op)

    @staticmethod
    def _sanitize(text: str) -> str:
        if not text:
            return ""
        # Escape parenthesis and backslashes for PDF literal strings, map non-latin1
        clean = text.encode("latin1", "replace").decode("latin1")
        clean = clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        return clean

    @staticmethod
    def _wrap_text(text: str, max_chars: int = 80) -> List[str]:
        words = text.split()
        lines = []
        curr = []
        curr_len = 0
        for w in words:
            if curr_len + len(w) + 1 > max_chars:
                lines.append(" ".join(curr))
                curr = [w]
                curr_len = len(w)
            else:
                curr.append(w)
                curr_len += len(w) + 1
        if curr:
            lines.append(" ".join(curr))
        return lines

    def render(self) -> bytes:
        if self.current_ops:
            self.pages_ops.append(self.current_ops)
        if not self.pages_ops:
            self.pages_ops.append([])

        total_pages = len(self.pages_ops)
        objects = []

        # Object 1: Catalog
        objects.append("<< /Type /Catalog /Pages 2 0 R >>")

        # Object 2: Pages tree placeholder (computed after pages created)
        page_obj_ids = [3 + i * 2 for i in range(total_pages)]
        kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
        pages_obj = f"<< /Type /Pages /Kids [{kids_str}] /Count {total_pages} >>"
        objects.append(pages_obj)

        # Build Page and Content Stream objects
        for idx, ops in enumerate(self.pages_ops, start=1):
            # Add footer on each page
            ops.append(f"BT 0.5 0.5 0.5 rg /F1 8 Tf 270 25 Td (Page {idx} of {total_pages}) Tj ET")
            stream_content = "\n".join(ops)
            stream_bytes = stream_content.encode("latin1")
            stream_len = len(stream_bytes)

            stream_obj = f"<< /Length {stream_len} >>\nstream\n{stream_content}\nendstream"
            content_id = 3 + (idx - 1) * 2 + 1
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
                f"/Contents {content_id} 0 R "
                f"/Resources << /Font << "
                f"/F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> "
                f"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
                f"/F3 << /Type /Font /Subtype /Type1 /BaseFont /Courier >> "
                f">> >> >>"
            )
            objects.append(page_obj)
            objects.append(stream_obj)

        # Assemble PDF file structure
        out = b"%PDF-1.4\n"
        offsets = []
        for i, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin1")

        xref_offset = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin1")
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode("latin1")

        out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1")
        return out


# Global singleton instance
report_exporter = ReportExporter()
"""
report_exporter.py
------------------
Multi-format Bug Report Exporter.
Supports generating downloadable reports in PDF, CSV, JSON, Markdown (MD), and HTML.
Zero external dependencies — uses Python standard library for robust, high-performance exports.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union


class ReportExporter:
    """
    Exports bug reports into various file formats (PDF, CSV, JSON, Markdown, HTML).
    """

    SUPPORTED_FORMATS = {"pdf", "csv", "json", "md", "markdown", "html"}

    # =========================================================================
    # PUBLIC EXPORT DISPATCHER
    # =========================================================================

    def export(
        self,
        reports: List[Union[Dict[str, Any], Any]],
        format_type: str = "pdf",
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bytes, str, str]:
        """
        Export bug reports to specified format.

        Returns:
            Tuple of (file_content_bytes, media_type, filename)
        """
        fmt = format_type.strip().lower()
        if fmt not in self.SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported export format '{format_type}'. "
                f"Supported formats are: {', '.join(sorted(self.SUPPORTED_FORMATS))}"
            )

        repo_name = (repo_info.get("name") if repo_info else None) or "BugReport"
        safe_repo_name = re.sub(r"[^\w\-]", "_", repo_name)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Normalize reports to dicts
        dict_reports = [self._to_dict(r) for r in reports]

        if fmt == "csv":
            content = self.export_csv(dict_reports, summary_stats, repo_info)
            media_type = "text/csv; charset=utf-8"
            filename = f"{safe_repo_name}_bugs_{timestamp}.csv"
        elif fmt == "json":
            content = self.export_json(dict_reports, summary_stats, repo_info)
            media_type = "application/json"
            filename = f"{safe_repo_name}_bugs_{timestamp}.json"
        elif fmt in ("md", "markdown"):
            content = self.export_markdown(dict_reports, summary_stats, repo_info)
            media_type = "text/markdown; charset=utf-8"
            filename = f"{safe_repo_name}_bugs_{timestamp}.md"
        elif fmt == "html":
            content = self.export_html(dict_reports, summary_stats, repo_info)
            media_type = "text/html; charset=utf-8"
            filename = f"{safe_repo_name}_bugs_{timestamp}.html"
        elif fmt == "pdf":
            content = self.export_pdf(dict_reports, summary_stats, repo_info)
            media_type = "application/pdf"
            filename = f"{safe_repo_name}_bugs_{timestamp}.pdf"
        else:
            raise ValueError(f"Unhandled format: {fmt}")

        return content, media_type, filename

    # =========================================================================
    # 1. CSV EXPORT
    # =========================================================================

    def export_csv(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate UTF-8 CSV with BOM for universal Excel compatibility."""
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header Row
        writer.writerow([
            "Bug ID",
            "Title",
            "Severity",
            "Priority",
            "Category",
            "File Path",
            "Line",
            "Column",
            "Function",
            "Class",
            "Language",
            "Rule ID",
            "AI Confidence",
            "Validation Status",
            "Status",
            "Duplicate Of",
            "Similar Issues Count",
            "Description",
            "Remediation Note",
        ])

        for r in reports:
            loc = r.get("location", {})
            static = r.get("static_analysis", {})
            sim = r.get("similarity", {})
            fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}

            writer.writerow([
                r.get("id") or r.get("issue_id", ""),
                r.get("title", ""),
                str(r.get("severity", "")).upper(),
                r.get("priority_formatted") or str(r.get("priority", "")).upper(),
                r.get("category", ""),
                r.get("file_path") or r.get("file", ""),
                loc.get("line") or r.get("line", ""),
                loc.get("column") or r.get("column", 0),
                r.get("function_name", "") or "",
                r.get("class_name", "") or "",
                r.get("language", ""),
                static.get("rule_id", ""),
                f"{float(r.get('ai_confidence', r.get('confidence', 1.0))):.2f}",
                r.get("validation_status", "UNVERIFIED"),
                r.get("status", "Open"),
                sim.get("duplicate_of") or r.get("duplicate_of") or "",
                len(sim.get("similar_issues", []) or r.get("similar_issues", [])),
                r.get("description", ""),
                fix.get("note", ""),
            ])

        # Encode with UTF-8 BOM so Excel opens special characters cleanly
        return output.getvalue().encode("utf-8-sig")

    # =========================================================================
    # 2. JSON EXPORT
    # =========================================================================

    def export_json(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate structured JSON document."""
        data = {
            "metadata": {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "generator": "AI Bug Tracker & Triage System",
                "repository": repo_info or {},
                "total_bugs": len(reports),
                # Feature 2: surface aggregate validation counts in metadata
                "verified_count": sum(
                    1 for r in reports
                    if r.get("validation_status") == "VERIFIED"
                ),
                "unverified_count": sum(
                    1 for r in reports
                    if r.get("validation_status", "UNVERIFIED") != "VERIFIED"
                ),
            },
            "summary_stats": summary_stats or self._calculate_quick_stats(reports),
            "bug_reports": reports,
        }
        return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")

    # =========================================================================
    # 3. MARKDOWN EXPORT
    # =========================================================================

    def export_markdown(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate GitHub-Flavored Markdown report."""
        stats = summary_stats or self._calculate_quick_stats(reports)
        repo_name = (repo_info.get("name") if repo_info else None) or "Repository"
        repo_path = (repo_info.get("path") if repo_info else None) or "N/A"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        lines = [
            f"# Bug Triage & Security Audit Report",
            f"",
            f"**Repository:** `{repo_name}`  ",
            f"**Path:** `{repo_path}`  ",
            f"**Generated:** `{date_str}`  ",
            f"**Total Issues Detected:** `{len(reports)}`  ",
            f"",
            f"---",
            f"",
            f"## Executive Summary",
            f"",
            f"| Metric | Count | Priority Breakdown | Count |",
            f"| :--- | :--- | :--- | :--- |",
            f"| **Total Bugs** | **{stats.get('total_bugs', len(reports))}** | **P1 (Fix now)** | {stats.get('priority_p1', 0)} |",
            f"| **Critical** | {stats.get('critical', 0)} | **P2 (Fix this week)** | {stats.get('priority_p2', 0)} |",
            f"| **High** | {stats.get('high', 0)} | **P3 (Backlog)** | {stats.get('priority_p3', 0)} |",
            f"| **Medium** | {stats.get('medium', 0)} | **P4 (Low)** | {stats.get('priority_p4', 0)} |",
            f"| **Low** | {stats.get('low', 0)} | **Duplicates** | {stats.get('duplicates_count', 0)} |",
            f"",
            f"---",
            f"",
            f"## Detailed Bug Reports",
            f"",
        ]

        if not reports:
            lines.append("No issues detected in codebase. Clean scan!")
        else:
            for idx, r in enumerate(reports, start=1):
                bug_id = r.get("id") or r.get("issue_id", f"BUG-{idx:04d}")
                title = r.get("title", "Issue Detected")
                sev = str(r.get("severity", "medium")).upper()
                prio = r.get("priority_formatted") or str(r.get("priority", "P3")).upper()
                file_p = r.get("file_path") or r.get("file", "unknown")
                line_n = r.get("line", 0)
                scope = self._format_scope(r)
                static = r.get("static_analysis", {})
                rule_id = static.get("rule_id", "N/A")
                fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}
                exp = r.get("explanation", {})

                lines.extend([
                    f"### {idx}. [{bug_id}] {title}",
                    f"",
                    f"- **Severity:** `{sev}` | **Priority:** `{prio}` | **Status:** `{r.get('status', 'Open')}`",
                    f"- **Location:** `{file_p}:{line_n}` in `{scope}`",
                    f"- **Rule Triggered:** `{rule_id}` ({r.get('category', 'general')})",
                    f"- **AI Confidence:** `{float(r.get('ai_confidence', r.get('confidence', 1.0))):.0%}` | **Validation:** `{r.get('validation_status', 'UNVERIFIED')}`",
                    f"",
                    f"**Description:**  ",
                    f"{r.get('description', '')}",
                    f"",
                ])

                # Code Snippet if available
                snippet = static.get("code_snippet") or r.get("code_snippet")
                if snippet:
                    lang = str(r.get("language", "")).lower()
                    lines.extend([
                        f"```python" if lang == "python" else f"```{lang}",
                        f"# Line {line_n}:",
                        f"{snippet}",
                        f"```",
                        f"",
                    ])

                # Suggested Fix if available
                if fix and (fix.get("note") or fix.get("add")):
                    lines.append(f"**Remediation:**  ")
                    if fix.get("note"):
                        lines.append(f"{fix.get('note')}  ")
                    if fix.get("add"):
                        lines.extend([
                            f"```diff",
                            f"{fix.get('remove') or ''}",
                            f"{fix.get('add') or ''}",
                            f"```",
                        ])
                    lines.append("")

                lines.append("---")
                lines.append("")

        return "\n".join(lines).encode("utf-8")

    # =========================================================================
    # 4. HTML EXPORT
    # =========================================================================

    def export_html(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate modern, standalone responsive HTML report with print styles."""
        stats = summary_stats or self._calculate_quick_stats(reports)
        repo_name = (repo_info.get("name") if repo_info else None) or "Repository"
        repo_path = (repo_info.get("path") if repo_info else None) or "N/A"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        cards_html = []
        for idx, r in enumerate(reports, start=1):
            bug_id = r.get("id") or r.get("issue_id", f"BUG-{idx:04d}")
            title = r.get("title", "Issue Detected")
            sev = str(r.get("severity", "medium")).lower()
            prio = r.get("priority_formatted") or str(r.get("priority", "P3")).upper()
            file_p = r.get("file_path") or r.get("file", "")
            line_n = r.get("line", 0)
            static = r.get("static_analysis", {})
            rule_id = static.get("rule_id", "")
            fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}
            snippet = static.get("code_snippet") or r.get("code_snippet", "")

            sev_color = {
                "critical": "#ef4444",
                "high": "#f97316",
                "medium": "#eab308",
                "low": "#3b82f6",
            }.get(sev, "#94a3b8")

            # Feature 2: validation badge
            validation_status = r.get("validation_status", "UNVERIFIED")
            ai_conf = float(r.get("ai_confidence", r.get("confidence", 1.0)))
            val_color = "#10b981" if validation_status == "VERIFIED" else "#94a3b8"
            val_badge = f'<span class="badge" style="background:{val_color}20;color:{val_color};border:1px solid {val_color}60;">{validation_status}</span>'
            conf_badge = f'<span class="badge prio-badge">AI: {ai_conf:.0%}</span>'

            fix_html = ""
            if fix.get("note"):
                fix_html = f"""
                <div class="fix-box">
                    <strong>Remediation:</strong> {fix.get('note')}
                </div>
                """

            snippet_html = ""
            if snippet:
                snippet_html = f"""
                <pre class="code-block"><code># Line {line_n}: {snippet}</code></pre>
                """

            cards_html.append(f"""
            <div class="bug-card">
                <div class="card-header">
                    <div>
                        <span class="bug-id">{bug_id}</span>
                        <h3 class="bug-title">{title}</h3>
                    </div>
                    <div class="badges">
                        <span class="badge" style="background: {sev_color}20; color: {sev_color}; border: 1px solid {sev_color}60;">{sev.upper()}</span>
                        <span class="badge prio-badge">{prio}</span>
                        {val_badge}
                        {conf_badge}
                    </div>
                </div>
                <div class="card-meta">
                    <span><strong>Location:</strong> <code>{file_p}:{line_n}</code></span>
                    <span><strong>Rule:</strong> <code>{rule_id}</code></span>
                    <span><strong>Category:</strong> {r.get('category', '')}</span>
                </div>
                <p class="bug-desc">{r.get('description', '')}</p>
                {snippet_html}
                {fix_html}
            </div>
            """)

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bug Triage Report - {repo_name}</title>
    <style>
        :root {{
            --bg: #0f172a;
            --card-bg: #1e293b;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --border: #334155;
            --accent: #6366f1;
        }}
        @media print {{
            body {{ background: #fff !important; color: #000 !important; font-size: 12pt; }}
            .bug-card {{ page-break-inside: avoid; border: 1px solid #ccc !important; background: #fff !important; color: #000 !important; }}
            .btn-print {{ display: none; }}
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background: var(--bg);
            color: var(--text);
            margin: 0;
            padding: 30px 20px;
            line-height: 1.5;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; }}
        h1 {{ margin: 0 0 8px 0; font-size: 26px; color: #fff; }}
        .meta-text {{ color: var(--text-muted); font-size: 14px; margin: 2px 0; }}
        .btn-print {{ background: var(--accent); color: #fff; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 12px; margin-bottom: 30px; }}
        .stat-box {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 14px; text-align: center; }}
        .stat-val {{ font-size: 24px; font-weight: bold; margin-bottom: 4px; }}
        .stat-label {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }}
        .bug-card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 18px; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
        .bug-id {{ font-size: 12px; font-weight: bold; color: var(--accent); font-family: monospace; }}
        .bug-title {{ margin: 4px 0 0 0; font-size: 18px; }}
        .badges {{ display: flex; gap: 8px; }}
        .badge {{ padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
        .prio-badge {{ background: #334155; color: #f1f5f9; }}
        .card-meta {{ display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--text-muted); margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }}
        .bug-desc {{ margin: 0 0 14px 0; font-size: 14px; color: #cbd5e1; }}
        .code-block {{ background: #0b1120; border: 1px solid var(--border); border-radius: 6px; padding: 12px; font-family: monospace; font-size: 13px; overflow-x: auto; color: #38bdf8; margin: 10px 0; }}
        .fix-box {{ background: #064e3b30; border-left: 4px solid #10b981; padding: 10px 14px; font-size: 13px; border-radius: 0 6px 6px 0; color: #a7f3d0; margin-top: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>Bug Triage & Security Audit Report</h1>
                <p class="meta-text"><strong>Repository:</strong> {repo_name} ({repo_path})</p>
                <p class="meta-text"><strong>Generated:</strong> {date_str} | <strong>Total Issues:</strong> {len(reports)}</p>
            </div>
            <button class="btn-print" onclick="window.print()">Print / Save PDF</button>
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-val" style="color: #6366f1;">{stats.get('total_bugs', len(reports))}</div>
                <div class="stat-label">Total Bugs</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #ef4444;">{stats.get('critical', 0)}</div>
                <div class="stat-label">Critical</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #f97316;">{stats.get('high', 0)}</div>
                <div class="stat-label">High</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #eab308;">{stats.get('medium', 0)}</div>
                <div class="stat-label">Medium</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #3b82f6;">{stats.get('low', 0)}</div>
                <div class="stat-label">Low</div>
            </div>
            <div class="stat-box">
                <div class="stat-val" style="color: #a855f7;">{stats.get('duplicates_count', 0)}</div>
                <div class="stat-label">Duplicates</div>
            </div>
        </div>

        <div class="bug-list">
            {"".join(cards_html) if cards_html else "<p>No bugs detected.</p>"}
        </div>
    </div>
</body>
</html>"""
        return html.encode("utf-8")

    # =========================================================================
    # 5. PDF EXPORT (Pure Python Standards-Compliant PDF 1.4)
    # =========================================================================

    def export_pdf(
        self,
        reports: List[Dict[str, Any]],
        summary_stats: Optional[Dict[str, Any]] = None,
        repo_info: Optional[Dict[str, Any]] = None,
    ) -> bytes:
        """Generate high-quality multi-page PDF document without external binaries."""
        stats = summary_stats or self._calculate_quick_stats(reports)
        repo_name = (repo_info.get("name") if repo_info else None) or "Repository"
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        pdf = _PDFCanvas()

        # Page 1: Title & Executive Summary
        pdf.new_page()
        pdf.draw_header("BUG TRIAGE & SECURITY AUDIT REPORT", repo_name, date_str)

        # Summary Metrics Box
        pdf.draw_summary_box(
            total=stats.get("total_bugs", len(reports)),
            critical=stats.get("critical", 0),
            high=stats.get("high", 0),
            medium=stats.get("medium", 0),
            low=stats.get("low", 0),
            p1=stats.get("priority_p1", 0),
            p2=stats.get("priority_p2", 0),
            p3=stats.get("priority_p3", 0),
        )

        pdf.add_y_offset(20)
        pdf.draw_section_title("Detailed Findings")

        if not reports:
            pdf.draw_text("No issues detected in codebase. Repository scan is clean.", font_size=11)
        else:
            for idx, r in enumerate(reports, start=1):
                # Ensure space on page, else break
                if pdf.y_pos < 160:
                    pdf.new_page()
                    pdf.draw_header("BUG TRIAGE & AUDIT REPORT (CONT.)", repo_name, date_str)

                bug_id = r.get("id") or r.get("issue_id", f"BUG-{idx:04d}")
                title = r.get("title", "Issue Detected")
                sev = str(r.get("severity", "medium")).upper()
                prio = r.get("priority_formatted") or str(r.get("priority", "P3")).upper()
                file_p = r.get("file_path") or r.get("file", "unknown")
                line_n = r.get("line", 0)
                static = r.get("static_analysis", {})
                rule_id = static.get("rule_id", "N/A")
                fix = r.get("suggestedFix", {}) or r.get("suggested_fix", {}) or {}
                desc = r.get("description", "")
                snippet = static.get("code_snippet") or r.get("code_snippet", "")

                pdf.draw_bug_entry(
                    index=idx,
                    bug_id=bug_id,
                    title=title,
                    severity=sev,
                    priority=prio,
                    file_path=f"{file_p}:{line_n}",
                    rule_id=rule_id,
                    description=desc,
                    snippet=snippet,
                    fix_note=fix.get("note", ""),
                )

        return pdf.render()

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _to_dict(report: Any) -> Dict[str, Any]:
        if hasattr(report, "model_dump"):
            return report.model_dump(mode="json")
        if hasattr(report, "to_dict"):
            return report.to_dict()
        if isinstance(report, dict):
            return dict(report)
        return getattr(report, "__dict__", {})

    @staticmethod
    def _format_scope(r: Dict[str, Any]) -> str:
        cls = r.get("class_name")
        fn = r.get("function_name")
        if cls and fn:
            return f"{cls}.{fn}()"
        if fn:
            return f"{fn}()"
        if cls:
            return f"class {cls}"
        return "top-level module"

    @staticmethod
    def _calculate_quick_stats(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
        stats = {
            "total_bugs": len(reports),
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "priority_p1": 0,
            "priority_p2": 0,
            "priority_p3": 0,
            "priority_p4": 0,
            "duplicates_count": 0,
        }
        for r in reports:
            sev = str(r.get("severity", "medium")).lower()
            if sev in stats:
                stats[sev] += 1
            prio = str(r.get("priority", "p3")).lower()
            if f"priority_{prio}" in stats:
                stats[f"priority_{prio}"] += 1
            sim = r.get("similarity", {})
            if sim.get("is_duplicate") or r.get("duplicate_of"):
                stats["duplicates_count"] += 1
        return stats


# =============================================================================
# LIGHTWEIGHT PURE-PYTHON PDF 1.4 GENERATOR
# =============================================================================

class _PDFCanvas:
    """Lightweight vector PDF 1.4 canvas for report generation."""

    def __init__(self, width: float = 612, height: float = 792):
        self.width = width
        self.height = height
        self.pages_ops: List[List[str]] = []
        self.current_ops: List[str] = []
        self.y_pos = height - 50

    def new_page(self):
        if self.current_ops:
            self.pages_ops.append(self.current_ops)
        self.current_ops = []
        self.y_pos = self.height - 50

    def add_y_offset(self, offset: float):
        self.y_pos -= offset

    def draw_header(self, main_title: str, sub_title: str, date_str: str):
        # Top banner line
        self.current_ops.append("0.2 0.3 0.6 RG 2 w 50 745 m 562 745 l S")
        # Main Title
        self._text(main_title, 50, 755, font="/F2", size=16, r=0.1, g=0.15, b=0.3)
        # Subtitle & Date
        self._text(f"Repository: {self._sanitize(sub_title)} | Generated: {date_str}", 50, 730, font="/F1", size=9, r=0.4, g=0.4, b=0.4)
        self.y_pos = 710

    def draw_section_title(self, title: str):
        self._text(title, 50, self.y_pos, font="/F2", size=13, r=0.15, g=0.2, b=0.4)
        self.y_pos -= 16

    def draw_summary_box(self, total: int, critical: int, high: int, medium: int, low: int, p1: int, p2: int, p3: int):
        box_top = self.y_pos
        box_h = 55
        # Background box
        self.current_ops.append(f"0.95 0.96 0.98 rg 50 {box_top - box_h} 512 {box_h} re f")
        self.current_ops.append(f"0.8 0.85 0.9 RG 1 w 50 {box_top - box_h} 512 {box_h} re S")

        # Metric text
        self._text("SUMMARY METRICS", 62, box_top - 16, font="/F2", size=9, r=0.3, g=0.35, b=0.5)
        stats_line = f"Total Bugs: {total}   |   Critical: {critical}   |   High: {high}   |   Medium: {medium}   |   Low: {low}"
        self._text(stats_line, 62, box_top - 32, font="/F2", size=10, r=0.1, g=0.1, b=0.1)
        prio_line = f"Triage Priority ->  P1 (Immediate): {p1}   |   P2 (High): {p2}   |   P3 (Normal): {p3}"
        self._text(prio_line, 62, box_top - 46, font="/F1", size=9, r=0.4, g=0.4, b=0.4)

        self.y_pos = box_top - box_h - 10

    def draw_bug_entry(
        self,
        index: int,
        bug_id: str,
        title: str,
        severity: str,
        priority: str,
        file_path: str,
        rule_id: str,
        description: str,
        snippet: str,
        fix_note: str,
    ):
        start_y = self.y_pos
        
        # Color coding for severity
        if severity == "CRITICAL":
            r, g, b = 0.85, 0.1, 0.1
        elif severity == "HIGH":
            r, g, b = 0.9, 0.4, 0.0
        elif severity == "MEDIUM":
            r, g, b = 0.8, 0.6, 0.0
        else:
            r, g, b = 0.2, 0.5, 0.8

        # Card Title Line
        header_text = f"{index}. [{bug_id}] {self._sanitize(title)}"
        self._text(header_text[:75], 50, start_y, font="/F2", size=11, r=0.1, g=0.1, b=0.2)
        
        # Badges
        badge_text = f"[{severity}] [{priority}]"
        self._text(badge_text, 440, start_y, font="/F2", size=9, r=r, g=g, b=b)
        start_y -= 14

        # Location & Rule
        meta_text = f"Location: {self._sanitize(file_path)}  |  Rule: {rule_id}"
        self._text(meta_text[:90], 50, start_y, font="/F1", size=9, r=0.4, g=0.4, b=0.4)
        start_y -= 13

        # Description (wrapped)
        desc_clean = self._sanitize(description)
        for line in self._wrap_text(desc_clean, 85)[:2]:
            self._text(line, 50, start_y, font="/F1", size=9, r=0.2, g=0.2, b=0.2)
            start_y -= 11

        # Code snippet if present
        if snippet:
            snip_clean = self._sanitize(snippet.strip().replace("\n", " "))
            self.current_ops.append(f"0.92 0.94 0.97 rg 50 {start_y - 12} 512 14 re f")
            self._text(f"Code: {snip_clean[:80]}", 56, start_y - 9, font="/F3", size=8, r=0.1, g=0.2, b=0.5)
            start_y -= 18

        # Fix note if present
        if fix_note:
            note_clean = self._sanitize(fix_note)
            self._text(f"Remediation: {note_clean[:85]}", 50, start_y, font="/F1", size=8, r=0.05, g=0.5, b=0.2)
            start_y -= 12

        # Separator line
        self.current_ops.append(f"0.88 0.88 0.88 RG 0.5 w 50 {start_y} m 562 {start_y} l S")
        start_y -= 14
        self.y_pos = start_y

    def draw_text(self, text: str, font_size: float = 10):
        self._text(self._sanitize(text), 50, self.y_pos, font="/F1", size=font_size, r=0.2, g=0.2, b=0.2)
        self.y_pos -= (font_size + 4)

    def _text(self, text: str, x: float, y: float, font: str = "/F1", size: float = 10, r: float = 0, g: float = 0, b: float = 0):
        safe = self._sanitize(text)
        op = f"BT {r} {g} {b} rg {font} {size} Tf {x:.1f} {y:.1f} Td ({safe}) Tj ET"
        self.current_ops.append(op)

    @staticmethod
    def _sanitize(text: str) -> str:
        if not text:
            return ""
        # Escape parenthesis and backslashes for PDF literal strings, map non-latin1
        clean = text.encode("latin1", "replace").decode("latin1")
        clean = clean.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        return clean

    @staticmethod
    def _wrap_text(text: str, max_chars: int = 80) -> List[str]:
        words = text.split()
        lines = []
        curr = []
        curr_len = 0
        for w in words:
            if curr_len + len(w) + 1 > max_chars:
                lines.append(" ".join(curr))
                curr = [w]
                curr_len = len(w)
            else:
                curr.append(w)
                curr_len += len(w) + 1
        if curr:
            lines.append(" ".join(curr))
        return lines

    def render(self) -> bytes:
        if self.current_ops:
            self.pages_ops.append(self.current_ops)
        if not self.pages_ops:
            self.pages_ops.append([])

        total_pages = len(self.pages_ops)
        objects = []

        # Object 1: Catalog
        objects.append("<< /Type /Catalog /Pages 2 0 R >>")

        # Object 2: Pages tree placeholder (computed after pages created)
        page_obj_ids = [3 + i * 2 for i in range(total_pages)]
        kids_str = " ".join(f"{pid} 0 R" for pid in page_obj_ids)
        pages_obj = f"<< /Type /Pages /Kids [{kids_str}] /Count {total_pages} >>"
        objects.append(pages_obj)

        # Build Page and Content Stream objects
        for idx, ops in enumerate(self.pages_ops, start=1):
            # Add footer on each page
            ops.append(f"BT 0.5 0.5 0.5 rg /F1 8 Tf 270 25 Td (Page {idx} of {total_pages}) Tj ET")
            stream_content = "\n".join(ops)
            stream_bytes = stream_content.encode("latin1")
            stream_len = len(stream_bytes)

            stream_obj = f"<< /Length {stream_len} >>\nstream\n{stream_content}\nendstream"
            content_id = 3 + (idx - 1) * 2 + 1
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
                f"/Contents {content_id} 0 R "
                f"/Resources << /Font << "
                f"/F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> "
                f"/F2 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >> "
                f"/F3 << /Type /Font /Subtype /Type1 /BaseFont /Courier >> "
                f">> >> >>"
            )
            objects.append(page_obj)
            objects.append(stream_obj)

        # Assemble PDF file structure
        out = b"%PDF-1.4\n"
        offsets = []
        for i, obj in enumerate(objects, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin1")

        xref_offset = len(out)
        out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("latin1")
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode("latin1")

        out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("latin1")
        return out


# Global singleton instance
report_exporter = ReportExporter()


# ---------------------------------------------------------------------------
# Feature 3+LangGraph: Resolution trace export helpers
# These are module-level functions (not methods) to keep ReportExporter lean.
# ---------------------------------------------------------------------------

def export_resolution_trace_json(trace_state: Dict[str, Any]) -> bytes:
    """
    Export a full LangGraph resolution-trace state dict to JSON bytes.
    Suitable for attaching to /resolve responses or saving alongside reports.
    """
    data = {
        "trace_type": "resolution_pipeline",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "bug_id": trace_state.get("bug_id", ""),
        "terminal_status": trace_state.get("terminal_status", ""),
        "validation_status": trace_state.get("validation_status", "UNVERIFIED"),
        "ai_confidence": trace_state.get("ai_confidence", 0.0),
        "routing": {
            "decision": trace_state.get("routing_decision", ""),
            "rationale": trace_state.get("routing_rationale", ""),
        },
        "resolution": {
            "root_cause": trace_state.get("root_cause", ""),
            "fix_diff": trace_state.get("fix_diff") or {},
            "reviewer_critique": trace_state.get("reviewer_critique", ""),
            "crew_approved": trace_state.get("crew_approved", False),
        },
        "test_harness": {
            "test_source": trace_state.get("test_source", ""),
            "pre_fix_passed": trace_state.get("pre_fix_passed"),
            "post_fix_passed": trace_state.get("post_fix_passed"),
            "error": trace_state.get("test_error"),
        },
        "retry_count": trace_state.get("retry_count", 0),
        "trace_log": trace_state.get("trace", []),
    }
    return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")


def export_resolution_trace_markdown(trace_state: Dict[str, Any]) -> bytes:
    """
    Export a LangGraph resolution-trace state as GitHub-Flavored Markdown.
    """
    bug_id = trace_state.get("bug_id", "BUG")
    status_ = trace_state.get("terminal_status", "UNKNOWN")
    val_status = trace_state.get("validation_status", "UNVERIFIED")
    conf = float(trace_state.get("ai_confidence", 0.0))
    routing = trace_state.get("routing_decision", "")
    rationale = trace_state.get("routing_rationale", "")
    root_cause = trace_state.get("root_cause", "")
    fix = trace_state.get("fix_diff") or {}
    critique = trace_state.get("reviewer_critique", "")
    crew_ok = trace_state.get("crew_approved", False)
    test_src = (trace_state.get("test_source") or "")[:1000]
    pre = trace_state.get("pre_fix_passed")
    post = trace_state.get("post_fix_passed")
    retries = trace_state.get("retry_count", 0)
    trace_log = trace_state.get("trace", [])
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    val_icon = "✅" if val_status == "VERIFIED" else "⏳"
    lines = [
        f"# Resolution Trace — {bug_id}",
        f"",
        f"**Generated:** `{date_str}`  ",
        f"**Terminal Status:** `{status_}`  ",
        f"**Validation:** {val_icon} `{val_status}`  ",
        f"**AI Confidence:** `{conf:.0%}`  ",
        f"",
        f"---",
        f"",
        f"## Routing",
        f"",
        f"| Field | Value |",
        f"|-------|-------|",
        f"| Decision | `{routing}` |",
        f"| Rationale | {rationale} |",
        f"",
        f"---",
        f"",
        f"## Root Cause",
        f"",
        f"{root_cause}",
        f"",
        f"---",
        f"",
        f"## Proposed Fix",
        f"",
    ]

    if fix.get("remove") or fix.get("add"):
        lines += [
            "```diff",
            fix.get("remove") or "",
            fix.get("add") or "",
            "```",
            "",
        ]
    if fix.get("note"):
        lines += [f"_{fix['note']}_", ""]

    if critique:
        lines += [
            f"**Reviewer Critique:** {critique}  ",
            f"**Crew Approved:** `{crew_ok}`  ",
            "",
        ]

    lines += [
        f"---",
        f"",
        f"## Test Harness",
        f"",
        f"| Field | Result |",
        f"|-------|--------|",
        f"| Pre-fix passed | `{pre}` |",
        f"| Post-fix passed | `{post}` |",
        f"| Retries | `{retries}` |",
        f"",
    ]

    if test_src:
        lines += [
            "<details>",
            "<summary>Generated Test Source</summary>",
            "",
            "```python",
            test_src.strip(),
            "```",
            "",
            "</details>",
            "",
        ]

    if trace_log:
        lines += [
            "---",
            "",
            "## Execution Trace",
            "",
            "```",
        ]
        lines += [f"  {step}" for step in trace_log]
        lines += ["```", ""]

    return "\n".join(lines).encode("utf-8")

