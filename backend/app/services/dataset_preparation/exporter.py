"""
exporter.py — Controlled JSONL, Metadata, and Quality Report Export.
===================================================================
Exports prepared, label-encoded, leakage-free datasets into versioned directories.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List

from .feature_builder import build_training_text, generate_group_id
from .validator import (
    ID_TO_PRIORITY,
    ID_TO_SEVERITY,
    PRIORITY_LABELS,
    PRIORITY_TO_ID,
    SEVERITY_LABELS,
    SEVERITY_TO_ID,
    compute_distribution,
)


def format_ml_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """Format a single record for DistilBERT training dataset."""
    sev = str(record.get("verified_severity") or record.get("severity") or "").strip().lower()
    prio = str(record.get("verified_priority") or record.get("priority") or "").strip().lower()

    sev_id = SEVERITY_TO_ID.get(sev, -1)
    prio_id = PRIORITY_TO_ID.get(prio, -1)

    text_input = build_training_text(record)
    group_id = record.get("group_id") or generate_group_id(record)

    # Note: detector_severity holds the static analyzer baseline prediction
    detector_sev = str(record.get("detector_severity") or record.get("severity") or "").strip().lower()

    return {
        "id": str(record.get("id") or ""),
        "analysis_run_id": str(record.get("analysis_run_id") or ""),
        "text": text_input,
        "severity": sev,
        "severity_label": sev_id,
        "priority": prio,
        "priority_label": prio_id,
        "detector_severity": detector_sev,
        "group_id": group_id,
        "rule_id": str(record.get("rule_id") or ""),
        "issue_type": str(record.get("issue_type") or ""),
        "language": str(record.get("language") or ""),
        "file_path": str(record.get("file_path") or ""),
        "line_number": record.get("line_number"),
    }


class DatasetExporter:
    """Handles versioned export of prepared datasets to disk."""

    def __init__(self, base_output_dir: str = "data/prepared") -> None:
        self.base_output_dir = Path(base_output_dir)

    def export(
        self,
        dataset_version: str,
        train_records: List[Dict[str, Any]],
        val_records: List[Dict[str, Any]],
        test_records: List[Dict[str, Any]],
        validation_report: Dict[str, Any],
        deduplication_stats: Dict[str, int],
        split_metadata: Dict[str, Any],
        custom_output_dir: Path | None = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Export train/val/test JSONL files and metadata to a versioned directory.
        """
        out_dir = Path(custom_output_dir) if custom_output_dir else (self.base_output_dir / dataset_version)

        if out_dir.exists() and not overwrite and any(out_dir.iterdir()):
            raise FileExistsError(
                f"Dataset version directory '{out_dir}' already exists. "
                f"Specify a new version name or set overwrite=True."
            )

        out_dir.mkdir(parents=True, exist_ok=True)

        # 1. Format records
        formatted_train = [format_ml_record(r) for r in train_records]
        formatted_val = [format_ml_record(r) for r in val_records]
        formatted_test = [format_ml_record(r) for r in test_records]

        # 2. Write JSONL files
        train_file = out_dir / "train.jsonl"
        val_file = out_dir / "validation.jsonl"
        test_file = out_dir / "test.jsonl"

        with open(train_file, "w", encoding="utf-8") as f:
            for rec in formatted_train:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        with open(val_file, "w", encoding="utf-8") as f:
            for rec in formatted_val:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        with open(test_file, "w", encoding="utf-8") as f:
            for rec in formatted_test:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        # 3. Compute per-split class distributions
        train_sev_dist = compute_distribution([r["severity"] for r in formatted_train], SEVERITY_LABELS)
        train_prio_dist = compute_distribution([r["priority"] for r in formatted_train], PRIORITY_LABELS)

        val_sev_dist = compute_distribution([r["severity"] for r in formatted_val], SEVERITY_LABELS)
        val_prio_dist = compute_distribution([r["priority"] for r in formatted_val], PRIORITY_LABELS)

        test_sev_dist = compute_distribution([r["severity"] for r in formatted_test], SEVERITY_LABELS)
        test_prio_dist = compute_distribution([r["priority"] for r in formatted_test], PRIORITY_LABELS)

        # 4. Generate Metadata
        metadata = {
            "dataset_version": dataset_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "PostgreSQL candidate_issues",
            "random_seed": split_metadata.get("random_seed", 42),
            "split_ratios": {
                "train": round(len(formatted_train) / max(1, len(formatted_train) + len(formatted_val) + len(formatted_test)), 4),
                "validation": round(len(formatted_val) / max(1, len(formatted_train) + len(formatted_val) + len(formatted_test)), 4),
                "test": round(len(formatted_test) / max(1, len(formatted_train) + len(formatted_val) + len(formatted_test)), 4),
            },
            "split_strategy": split_metadata.get("strategy"),
            "strategy_details": split_metadata.get("strategy_details"),
            "total_verified_records": deduplication_stats.get("total_verified_records", 0),
            "records_after_deduplication": deduplication_stats.get("final_unique_records", 0),
            "train_records": len(formatted_train),
            "validation_records": len(formatted_val),
            "test_records": len(formatted_test),
            "severity_label_mapping": SEVERITY_TO_ID,
            "priority_label_mapping": PRIORITY_TO_ID,
            "id_to_severity_mapping": ID_TO_SEVERITY,
            "id_to_priority_mapping": ID_TO_PRIORITY,
            "files": {
                "train": str(train_file.resolve()),
                "validation": str(val_file.resolve()),
                "test": str(test_file.resolve()),
                "metadata": str((out_dir / "metadata.json").resolve()),
                "quality_report": str((out_dir / "quality_report.json").resolve()),
            },
        }

        # 5. Generate Quality Report
        quality_report = {
            "status": validation_report.get("status", "valid"),
            "dataset_version": dataset_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total_verified_records": deduplication_stats.get("total_verified_records", 0),
            "records_after_deduplication": deduplication_stats.get("final_unique_records", 0),
            "exact_duplicates_removed": deduplication_stats.get("records_removed_from_ml_export", 0),
            "missingness_statistics": validation_report.get("missingness_statistics", {}),
            "overall_distributions": {
                "severity": validation_report.get("severity_distribution", {}),
                "priority": validation_report.get("priority_distribution", {}),
            },
            "split_distributions": {
                "train": {"severity": train_sev_dist, "priority": train_prio_dist},
                "validation": {"severity": val_sev_dist, "priority": val_prio_dist},
                "test": {"severity": test_sev_dist, "priority": test_prio_dist},
            },
            "split_counts": {
                "train": len(formatted_train),
                "validation": len(formatted_val),
                "test": len(formatted_test),
            },
            "leakage_validation": {
                "cross_split_group_overlap": split_metadata.get("cross_split_group_overlap", 0),
                "leakage_check_passed": split_metadata.get("leakage_check_passed", True),
            },
            "warnings": validation_report.get("warnings", []),
            "errors": validation_report.get("errors", []),
        }

        # 6. Save JSON reports
        with open(out_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        with open(out_dir / "quality_report.json", "w", encoding="utf-8") as f:
            json.dump(quality_report, f, indent=2, ensure_ascii=False)

        return {
            "export_directory": str(out_dir.resolve()),
            "metadata": metadata,
            "quality_report": quality_report,
        }
