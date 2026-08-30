"""
service.py — Dataset Preparation Pipeline Orchestration Service.
================================================================
Orchestrates retrieving verified records from PostgreSQL, validation,
provenance classification, deduplication, feature construction,
group-aware splitting, readiness scoring, and controlled export.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.candidate_issue_repo import candidate_issue_repository
from .deduplicator import DatasetDeduplicator
from .exporter import DatasetExporter
from .readiness import evaluate_dataset_readiness
from .splitter import DatasetSplitter
from .validator import DatasetValidator


class DatasetPreparationService:
    """Orchestrates end-to-end dataset quality validation, feature construction, and export."""

    def __init__(self, default_output_dir: str = "data/prepared") -> None:
        self.default_output_dir = Path(default_output_dir)
        self.deduplicator = DatasetDeduplicator()
        self.exporter = DatasetExporter(base_output_dir=default_output_dir)

    async def evaluate_readiness(
        self,
        db: AsyncSession,
    ) -> Dict[str, Any]:
        """
        Evaluate dataset readiness against real PostgreSQL verified records.
        """
        raw_records = await candidate_issue_repository.get_verified_training_dataset(db)
        validator = DatasetValidator(min_samples_per_class=1, exclude_test_synthetic=True)
        valid_records, val_report = validator.validate_records(raw_records)
        unique_records, dedup_stats = self.deduplicator.deduplicate(valid_records)

        splitter = DatasetSplitter(train_ratio=0.70, val_ratio=0.15, test_ratio=0.15, random_seed=42)
        _, _, _, split_meta = splitter.split(unique_records)

        readiness = evaluate_dataset_readiness(
            records=unique_records,
            deduplication_stats=dedup_stats,
            validation_report=val_report,
            split_metadata=split_meta,
        )

        return {
            "total_candidate_issues_in_db": len(raw_records),
            "unique_verified_records": len(unique_records),
            "readiness": readiness,
            "provenance_breakdown": val_report.get("provenance_breakdown", {}),
            "missingness_statistics": val_report.get("missingness_statistics", {}),
            "severity_distribution": val_report.get("severity_distribution", {}),
            "priority_distribution": val_report.get("priority_distribution", {}),
        }

    async def prepare_dataset(
        self,
        db: AsyncSession,
        dataset_version: str = "dataset_v1",
        random_seed: int = 42,
        train_ratio: float = 0.70,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
        min_samples_per_class: int = 1,
        exclude_test_synthetic: bool = True,
        export_dir: Optional[str] = None,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute the full dataset preparation pipeline from PostgreSQL verified records.
        """
        # 1. Retrieve fully verified candidate issues from DB
        raw_records = await candidate_issue_repository.get_verified_training_dataset(db)

        if not raw_records:
            out_dir = Path(export_dir) if export_dir else (self.default_output_dir / dataset_version)
            return {
                "dataset_version": dataset_version,
                "status": "empty_dataset",
                "export_directory": str(out_dir),
                "total_verified_records": 0,
                "records_after_deduplication": 0,
                "train_records": 0,
                "validation_records": 0,
                "test_records": 0,
                "quality_report": {
                    "status": "empty",
                    "total_verified_records": 0,
                    "warnings": [{"type": "no_data", "message": "No fully verified candidate issues found in database."}],
                    "errors": [],
                },
                "metadata": {
                    "dataset_version": dataset_version,
                    "total_verified_records": 0,
                },
                "readiness": {
                    "dataset_status": "NOT READY FOR TRAINING",
                    "status": "NOT READY",
                    "readiness_score": 0.0,
                },
            }

        # 2. Quality Validation & Provenance Classification
        validator = DatasetValidator(
            min_samples_per_class=min_samples_per_class,
            exclude_test_synthetic=exclude_test_synthetic,
        )
        valid_records, val_report = validator.validate_records(raw_records)

        # 3. Deduplication for ML export
        unique_records, dedup_stats = self.deduplicator.deduplicate(valid_records)

        # 4. Group-aware, stratified splitting
        splitter = DatasetSplitter(
            train_ratio=train_ratio,
            val_ratio=validation_ratio,
            test_ratio=test_ratio,
            random_seed=random_seed,
            min_samples_per_class=min_samples_per_class,
        )
        train_recs, val_recs, test_recs, split_meta = splitter.split(unique_records)

        # 5. Readiness Evaluation
        readiness = evaluate_dataset_readiness(
            records=unique_records,
            deduplication_stats=dedup_stats,
            validation_report=val_report,
            split_metadata=split_meta,
        )

        # 6. Export JSONL, metadata, and quality report
        val_report["readiness"] = readiness
        export_result = self.exporter.export(
            dataset_version=dataset_version,
            train_records=train_recs,
            val_records=val_recs,
            test_records=test_recs,
            validation_report=val_report,
            deduplication_stats=dedup_stats,
            split_metadata=split_meta,
            custom_output_dir=Path(export_dir) if export_dir else None,
            overwrite=overwrite,
        )

        return {
            "dataset_version": dataset_version,
            "status": "prepared",
            "export_directory": export_result["export_directory"],
            "total_verified_records": len(raw_records),
            "records_after_deduplication": len(unique_records),
            "train_records": len(train_recs),
            "validation_records": len(val_recs),
            "test_records": len(test_recs),
            "quality_report": export_result["quality_report"],
            "metadata": export_result["metadata"],
            "readiness": readiness,
        }

    def get_dataset_metadata(
        self, dataset_version: str, custom_dir: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Read metadata.json for a prepared dataset version."""
        target_dir = Path(custom_dir) if custom_dir else (self.default_output_dir / dataset_version)
        meta_file = target_dir / "metadata.json"
        if not meta_file.exists():
            return None
        with open(meta_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_dataset_quality_report(
        self, dataset_version: str, custom_dir: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Read quality_report.json for a prepared dataset version."""
        target_dir = Path(custom_dir) if custom_dir else (self.default_output_dir / dataset_version)
        report_file = target_dir / "quality_report.json"
        if not report_file.exists():
            return None
        with open(report_file, "r", encoding="utf-8") as f:
            return json.load(f)


dataset_preparation_service = DatasetPreparationService()
