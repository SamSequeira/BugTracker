"""
Metrics tracking wrapper for the LLM bug detection pipeline.

Provides detailed tracking of rejections at each stage without modifying
the core detector. This enables reporting on:
- Stage 1 rejections (not a semantic bug candidate)
- Stage 2 rejections (source grounding validation failed)
- Stage 3 rejections (adversarial verification failed)
- Deduplication rejections (duplicate of rule finding)
"""

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DetectionMetrics:
    """Metrics for a single function's detection attempt."""

    function_name: str
    file_path: str
    stage1_candidate: Optional[dict] = None  # Result from Stage 1 LLM
    stage2_rejected: bool = False  # Failed source grounding
    stage3_rejected: bool = False  # Failed adversarial verification
    final_finding: Optional[dict] = None  # Passed all stages
    dedup_rejected: bool = False  # Duplicate of rule finding
    dedup_match: Optional[dict] = None  # Which rule it duplicated


class MetricsCollector:
    """Collects and aggregates detection metrics across a scan."""

    def __init__(self):
        self.metrics = []

    def record_stage1_rejection(self, function_name: str, file_path: str):
        """Record that Stage 1 LLM didn't find a candidate."""
        self.metrics.append(DetectionMetrics(
            function_name=function_name,
            file_path=file_path,
        ))

    def record_stage1_candidate(self, function_name: str, file_path: str, candidate: dict):
        """Record that Stage 1 LLM detected a candidate."""
        self.metrics.append(DetectionMetrics(
            function_name=function_name,
            file_path=file_path,
            stage1_candidate=candidate,
        ))

    def record_stage2_rejection(self, function_name: str, file_path: str):
        """Record that Stage 2 source grounding rejected the candidate."""
        # Find the most recent metric for this function
        for m in reversed(self.metrics):
            if m.function_name == function_name and m.file_path == file_path:
                m.stage2_rejected = True
                break

    def record_stage3_rejection(self, function_name: str, file_path: str):
        """Record that Stage 3 adversarial verification rejected the candidate."""
        for m in reversed(self.metrics):
            if m.function_name == function_name and m.file_path == file_path:
                m.stage3_rejected = True
                break

    def record_final_finding(self, function_name: str, file_path: str, finding: dict):
        """Record that a finding passed all stages and was saved."""
        for m in reversed(self.metrics):
            if m.function_name == function_name and m.file_path == file_path:
                m.final_finding = finding
                break

    def record_dedup_rejection(self, function_name: str, file_path: str, rule_finding: dict):
        """Record that a finding was rejected as duplicate of rule finding."""
        for m in reversed(self.metrics):
            if m.function_name == function_name and m.file_path == file_path:
                m.dedup_rejected = True
                m.dedup_match = rule_finding
                break

    def get_summary(self) -> dict:
        """Get summary statistics."""
        stage1_rejections = sum(1 for m in self.metrics if m.stage1_candidate is None)
        stage1_candidates = sum(1 for m in self.metrics if m.stage1_candidate is not None)
        stage2_rejections = sum(1 for m in self.metrics if m.stage2_rejected)
        stage3_rejections = sum(1 for m in self.metrics if m.stage3_rejected)
        dedup_rejections = sum(1 for m in self.metrics if m.dedup_rejected)
        final_findings = sum(1 for m in self.metrics if m.final_finding is not None)

        return {
            "total_functions_checked": len(self.metrics),
            "stage1_rejections": stage1_rejections,
            "stage1_candidates": stage1_candidates,
            "stage2_rejections": stage2_rejections,
            "stage3_rejections": stage3_rejections,
            "dedup_rejections": dedup_rejections,
            "final_unique_findings": final_findings,
        }

    def get_detailed_report(self) -> str:
        """Get detailed report of all metrics."""
        summary = self.get_summary()

        lines = []
        lines.append("=" * 90)
        lines.append("DETECTION PIPELINE METRICS")
        lines.append("=" * 90)
        lines.append("")
        lines.append(f"Functions checked:               {summary['total_functions_checked']}")
        lines.append("")
        lines.append("STAGE 1: LLM Detection")
        lines.append(f"  Γ£ô Candidates detected:         {summary['stage1_candidates']}")
        lines.append(f"  Γ£ù Stage 1 rejections:          {summary['stage1_rejections']}")
        lines.append("")
        lines.append("STAGE 2: Source Grounding (AST)")
        lines.append(f"  Γ£ù Stage 2 rejections:          {summary['stage2_rejections']}")
        lines.append("")
        lines.append("STAGE 3: Adversarial Verification")
        lines.append(f"  Γ£ù Stage 3 rejections:          {summary['stage3_rejections']}")
        lines.append("")
        lines.append("DEDUPLICATION: Rule/LLM Overlap Check")
        lines.append(f"  Γ£ù Duplicate rejections:        {summary['dedup_rejections']}")
        lines.append("")
        lines.append("FINAL RESULTS")
        lines.append(f"  Γ£ô Unique LLM findings saved:   {summary['final_unique_findings']}")
        lines.append("=" * 90)

        return "\n".join(lines)


# Global metrics collector
_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector instance."""
    return _collector


def reset_metrics():
    """Reset metrics collector (for new runs)."""
    global _collector
    _collector = MetricsCollector()
