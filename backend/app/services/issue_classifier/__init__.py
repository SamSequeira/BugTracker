"""
Issue Classifier Module (Multi-Task DistilBERT).
=================================================
Predicts Severity (critical, high, medium, low) and Priority (p1, p2, p3, p4)
for candidate issues detected by the static analyzer.
"""
from .classifier import IssueClassifier
from .config import (
    InferenceConfig,
    ModelConfig,
    NormalizationConfig,
    PRIORITY_LABELS,
    PRIORITY_TO_ID,
    SEVERITY_LABELS,
    SEVERITY_TO_ID,
    TrainingConfig,
)
from .dataset import DatasetPipeline, IssueDataset
from .error_analysis import ErrorAnalyzer
from .evaluator import MultiTaskEvaluator
from .model import MultiTaskDistilBertClassifier
from .normalizer import IssueNormalizer
from .service import IssueClassificationService, issue_classification_service
from .trainer import MultiTaskTrainer

__all__ = [
    "MultiTaskDistilBertClassifier",
    "IssueNormalizer",
    "DatasetPipeline",
    "IssueDataset",
    "MultiTaskTrainer",
    "MultiTaskEvaluator",
    "ErrorAnalyzer",
    "IssueClassifier",
    "IssueClassificationService",
    "issue_classification_service",
    "ModelConfig",
    "TrainingConfig",
    "InferenceConfig",
    "NormalizationConfig",
    "SEVERITY_LABELS",
    "PRIORITY_LABELS",
    "SEVERITY_TO_ID",
    "PRIORITY_TO_ID",
]
