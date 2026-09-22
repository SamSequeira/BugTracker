"""
config.py — Configuration dataclasses and constants for the Issue Classifier.
=============================================================================
Defines label taxonomies, model parameters, training hyperparameters,
and inference configuration defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ===========================================================================
# Label Taxonomies & Mappings
# ===========================================================================

SEVERITY_LABELS: List[str] = ["high", "medium", "low"]
PRIORITY_LABELS: List[str] = ["p1", "p2", "p3", "p4"]

SEVERITY_TO_ID: Dict[str, int] = {label: idx for idx, label in enumerate(SEVERITY_LABELS)}
ID_TO_SEVERITY: Dict[int, str] = {idx: label for idx, label in enumerate(SEVERITY_LABELS)}

PRIORITY_TO_ID: Dict[str, int] = {label: idx for idx, label in enumerate(PRIORITY_LABELS)}
ID_TO_PRIORITY: Dict[int, str] = {idx: label for idx, label in enumerate(PRIORITY_LABELS)}

# Under-classification pairs (actual, predicted) representing serious dangerous errors
UNDERCLASSIFICATION_SEVERITY_PAIRS: List[Tuple[str, str]] = [
    ("high", "low"),
]

UNDERCLASSIFICATION_PRIORITY_PAIRS: List[Tuple[str, str]] = [
    ("p1", "p3"),
    ("p1", "p4"),
    ("p2", "p4"),
]


# ===========================================================================
# Configuration Dataclasses
# ===========================================================================

@dataclass
class ModelConfig:
    """Configuration for model architecture and tokenization."""
    pretrained_model_name: str = "distilbert-base-uncased"
    num_severity_classes: int = len(SEVERITY_LABELS)
    num_priority_classes: int = len(PRIORITY_LABELS)
    max_length: int = 256
    dropout_prob: float = 0.2


@dataclass
class NormalizationConfig:
    """Configuration for normalizing candidate issues into textual representations."""
    include_rule_id: bool = True
    include_language: bool = True
    include_issue_type: bool = True
    include_message: bool = True
    include_code_snippet: bool = True
    include_evidence: bool = True


@dataclass
class TrainingConfig:
    """Hyperparameters and settings for multi-task training."""
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    batch_size: int = 16
    epochs: int = 5
    severity_loss_weight: float = 0.5
    priority_loss_weight: float = 0.5
    use_class_weights: bool = True
    early_stopping_patience: int = 3
    warmup_ratio: float = 0.1
    max_grad_norm: float = 1.0
    seed: int = 42
    output_dir: str = "backend/app/models/issue_classifier"


@dataclass
class InferenceConfig:
    """Configuration for inference and post-processing."""
    confidence_threshold: float = 0.80
    model_dir: str = "backend/app/models/issue_classifier"
    device: str = "auto"  # "auto" | "cuda" | "cpu"
"""
config.py — Configuration dataclasses and constants for the Issue Classifier.
=============================================================================
Defines label taxonomies, model parameters, training hyperparameters,
and inference configuration defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# ===========================================================================
# Label Taxonomies & Mappings
# ===========================================================================

SEVERITY_LABELS: List[str] = ["critical", "high", "medium", "low"]
PRIORITY_LABELS: List[str] = ["p1", "p2", "p3", "p4"]

SEVERITY_TO_ID: Dict[str, int] = {label: idx for idx, label in enumerate(SEVERITY_LABELS)}
ID_TO_SEVERITY: Dict[int, str] = {idx: label for idx, label in enumerate(SEVERITY_LABELS)}

PRIORITY_TO_ID: Dict[str, int] = {label: idx for idx, label in enumerate(PRIORITY_LABELS)}
ID_TO_PRIORITY: Dict[int, str] = {idx: label for idx, label in enumerate(PRIORITY_LABELS)}

# Under-classification pairs (actual, predicted) representing serious dangerous errors
UNDERCLASSIFICATION_SEVERITY_PAIRS: List[Tuple[str, str]] = [
    ("critical", "low"),
    ("critical", "medium"),
    ("high", "low"),
]

UNDERCLASSIFICATION_PRIORITY_PAIRS: List[Tuple[str, str]] = [
    ("p1", "p3"),
    ("p1", "p4"),
    ("p2", "p4"),
]


# ===========================================================================
# Configuration Dataclasses
# ===========================================================================

@dataclass
class ModelConfig:
    """Configuration for model architecture and tokenization."""
    pretrained_model_name: str = "distilbert-base-uncased"
    num_severity_classes: int = len(SEVERITY_LABELS)
    num_priority_classes: int = len(PRIORITY_LABELS)
    max_length: int = 256
    dropout_prob: float = 0.2


@dataclass
class NormalizationConfig:
    """Configuration for normalizing candidate issues into textual representations."""
    include_rule_id: bool = True
    include_language: bool = True
    include_issue_type: bool = True
    include_message: bool = True
    include_code_snippet: bool = True
    include_evidence: bool = True


@dataclass
class TrainingConfig:
    """Hyperparameters and settings for multi-task training."""
    learning_rate: float = 2e-5
    weight_decay: float = 0.01
    batch_size: int = 16
    epochs: int = 5
    severity_loss_weight: float = 0.5
    priority_loss_weight: float = 0.5
    use_class_weights: bool = True
    early_stopping_patience: int = 3
    warmup_ratio: float = 0.1
    max_grad_norm: float = 1.0
    seed: int = 42
    output_dir: str = "backend/app/models/issue_classifier"


@dataclass
class InferenceConfig:
    """Configuration for inference and post-processing."""
    confidence_threshold: float = 0.80
    model_dir: str = "backend/app/models/issue_classifier"
    device: str = "auto"  # "auto" | "cuda" | "cpu"
