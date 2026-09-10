"""
architecture_summary_generator.py
---------------------------------
Deterministic architecture summary generator for repositories.
Synthesizes repository intent, architecture overview, health assessment,
and parser version from actual analysis findings, components, and technologies.
"""

import uuid
from typing import Any, Dict, List, Optional

from app.models.analysis_technology import AnalysisTechnology
from app.models.architecture_component import ArchitectureComponent
from app.models.architecture_summary import ArchitectureSummary
from app.models.candidate_issues import CandidateIssue
from app.models.source_file import SourceFile
from app.services.static_analyzer.severity import normalize_scanner_severity

PARSER_VERSION = "Tree-Sitter 0.22 / BugTracker AST Engine v1.0.0"


class ArchitectureSummaryGenerator:
    """Deterministically generates architecture summary data for an analysis run."""

    def generate_summary(
        self,
        analysis_run_id: str,
        technologies: List[AnalysisTechnology],
        components: List[ArchitectureComponent],
        source_files: List[SourceFile],
        candidate_issues: List[CandidateIssue],
    ) -> ArchitectureSummary:
        """
        Generate deterministic ArchitectureSummary ORM object from analysis entities.
        """
        # 1. Synthesize Intent
        # Extract primary frameworks & database technologies
        frameworks = [t.name for t in technologies if t.category in ("Framework", "Frontend")]
        databases = [t.name for t in technologies if t.category in ("Database", "Database/ORM")]
        languages = [t.name for t in technologies if t.category in ("Programming Language", "Language/Runtime")]

        intent_parts = []
        if frameworks:
            fw_str = ", ".join(frameworks[:3])
            intent_parts.append(f"built with {fw_str}")
        elif languages:
            lang_str = ", ".join(languages[:2])
            intent_parts.append(f"built primarily in {lang_str}")

        layer_names = [c.name for c in components if c.component_type != "general_module"]
        if layer_names:
            layers_str = ", ".join(layer_names[:3])
            intent_parts.append(f"structured across {layers_str}")

        if intent_parts:
            intent = f"The codebase implements a software application {' '.join(intent_parts)}."
        else:
            intent = "The repository implements a structured codebase with modular components and automated static validation."

        # 2. Synthesize Architecture Overview
        total_files = len(source_files)
        total_lines = sum((sf.line_count or 0) for sf in source_files)
        comp_summaries = []
        for c in components:
            count = sum(1 for sf in source_files if sf.component_id == c.id)
            comp_summaries.append(f"{c.name} ({count} files)")

        overview_parts = [
            f"The codebase contains {total_files} analyzed source files (~{total_lines} total lines of code) organized into {len(components)} logical architectural components: {', '.join(comp_summaries)}."
        ]

        # Prioritize primary technologies for the summary text
        primary_techs = [
            t.name for t in technologies
            if t.category in (
                "Programming Language",
                "Framework",
                "Frontend",
                "Database",
                "Database/ORM",
                "Infrastructure",
                "Testing",
                "Build Tool",
                "State Management",
            )
        ]
        display_techs = primary_techs if primary_techs else [t.name for t in technologies]
        if display_techs:
            overview_parts.append(f"Identified technology stack: {', '.join(display_techs[:6])}.")

        architecture_overview = " ".join(overview_parts)

        # 3. Synthesize Health Assessment
        total_issues = len(candidate_issues)
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for issue in candidate_issues:
            sev = normalize_scanner_severity(issue.severity)
            if sev in severity_counts:
                severity_counts[sev] += 1
            else:
                severity_counts["medium"] += 1

        if total_issues == 0:
            health_assessment = "No static analysis issues or critical vulnerabilities were detected. The codebase exhibits strong architectural hygiene."
        else:
            sev_details = []
            if severity_counts["high"] > 0:
                sev_details.append(f"{severity_counts['high']} high-severity")
            if severity_counts["medium"] > 0:
                sev_details.append(f"{severity_counts['medium']} medium-severity")
            if severity_counts["low"] > 0:
                sev_details.append(f"{severity_counts['low']} low-severity")

            sev_str = ", ".join(sev_details) if sev_details else f"{total_issues} issues"
            health_assessment = (
                f"Static analysis identified {total_issues} candidate issues ({sev_str}). "
                "Architectural components are cleanly partitioned, but highlighted findings require inspection and recommended remediation."
            )

        return ArchitectureSummary(
            id=str(uuid.uuid4()),
            analysis_run_id=analysis_run_id,
            intent=intent,
            architecture_overview=architecture_overview,
            health_assessment=health_assessment,
            parser_version=PARSER_VERSION,
        )


architecture_summary_generator = ArchitectureSummaryGenerator()
