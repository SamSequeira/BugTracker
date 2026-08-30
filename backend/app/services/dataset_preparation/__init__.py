"""
Dataset Preparation Package
===========================
Provides dataset quality validation, exact deduplication, feature building,
stratified group splitting, readiness assessment, review sampling,
and controlled export for DistilBERT training datasets.
"""

from .deduplicator import DatasetDeduplicator
from .exporter import DatasetExporter
from .feature_builder import build_training_text, generate_group_id, serialize_evidence
from .readiness import evaluate_dataset_readiness
from .sampler import ReviewSampler
from .service import DatasetPreparationService, dataset_preparation_service
from .splitter import DatasetSplitter
from .validator import (
    ID_TO_PRIORITY,
    ID_TO_SEVERITY,
    PRIORITY_LABELS,
    PRIORITY_TO_ID,
    SEVERITY_LABELS,
    SEVERITY_TO_ID,
    DatasetValidator,
    classify_provenance,
)

__all__ = [
    "DatasetPreparationService",
    "dataset_preparation_service",
    "DatasetValidator",
    "DatasetDeduplicator",
    "DatasetSplitter",
    "DatasetExporter",
    "ReviewSampler",
    "build_training_text",
    "generate_group_id",
    "serialize_evidence",
    "evaluate_dataset_readiness",
    "classify_provenance",
    "SEVERITY_LABELS",
    "PRIORITY_LABELS",
    "SEVERITY_TO_ID",
    "PRIORITY_TO_ID",
    "ID_TO_SEVERITY",
    "ID_TO_PRIORITY",
]
