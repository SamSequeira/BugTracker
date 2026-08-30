"""
app.services.ml package.
========================
Provides production ML configuration, dataset loading, split validation,
multi-signal drift detection, safe inference, risk-controlled routing,
decoupled severity assessment, and evaluation metrics.
"""
from .calibration import TemperatureScaler
from .config import (
    DEFAULT_TRAINING_CONFIG,
    GROUND_TRUTH_DATASET_PATH,
    MODELS_DIR,
    PRODUCTION_DRIFT_THRESHOLD,
    PRODUCTION_PAYLOAD_LIMIT_BYTES,
    PRODUCTION_THRESHOLD,
    RANDOM_SEED,
    SAFETY_BENCHMARK_DATASET_PATH,
    SEVERITY_CONFIG_A_LABELS,
    SEVERITY_LABELS,
    VALIDITY_LABELS,
)
from .data_loader import (
    compute_training_class_weights,
    load_ground_truth_dataset,
    load_safety_benchmark_dataset,
    prepare_severity_data,
    prepare_validity_data,
)
from .drift_detector import ProductionDriftDetector
from .error_analysis import generate_error_analysis_report
from .inference import MLInferencePipeline, safe_predict
from .input_builder import build_input_text, normalize_evidence_dict
from .metrics import calculate_classification_metrics, compute_expected_calibration_error
from .preprocessing import consolidate_severity, severity_to_priority
from .routing import route_candidate_issue
from .safety import evaluate_historical_fp_rejection, evaluate_historical_tp_recall, is_static_rule_suppressed
from .severity import CANONICAL_RULE_SEVERITY_MAP, predict_production_severity
from .split_validator import assert_no_group_leakage, validate_splits

__all__ = [
    "DEFAULT_TRAINING_CONFIG",
    "GROUND_TRUTH_DATASET_PATH",
    "SAFETY_BENCHMARK_DATASET_PATH",
    "MODELS_DIR",
    "PRODUCTION_THRESHOLD",
    "PRODUCTION_DRIFT_THRESHOLD",
    "PRODUCTION_PAYLOAD_LIMIT_BYTES",
    "RANDOM_SEED",
    "SEVERITY_CONFIG_A_LABELS",
    "SEVERITY_LABELS",
    "VALIDITY_LABELS",
    "TemperatureScaler",
    "compute_training_class_weights",
    "load_ground_truth_dataset",
    "load_safety_benchmark_dataset",
    "prepare_severity_data",
    "prepare_validity_data",
    "generate_error_analysis_report",
    "MLInferencePipeline",
    "safe_predict",
    "ProductionDriftDetector",
    "route_candidate_issue",
    "predict_production_severity",
    "CANONICAL_RULE_SEVERITY_MAP",
    "evaluate_historical_tp_recall",
    "evaluate_historical_fp_rejection",
    "is_static_rule_suppressed",
    "build_input_text",
    "normalize_evidence_dict",
    "calculate_classification_metrics",
    "compute_expected_calibration_error",
    "consolidate_severity",
    "severity_to_priority",
    "assert_no_group_leakage",
    "validate_splits",
]
