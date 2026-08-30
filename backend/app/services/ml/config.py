"""
config.py — Production Machine Learning Pipeline Configuration.
================================================================
Configures model architecture, hyperparameter defaults, filepaths,
calibrated thresholds, and label specifications for validity and severity.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

# Base Paths
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BACKEND_DIR / "data"
MODELS_DIR = BACKEND_DIR / "models"

# Runtime directories
MODELS_DIR.mkdir(parents=True, exist_ok=True)
(MODELS_DIR / "validity").mkdir(parents=True, exist_ok=True)
(MODELS_DIR / "severity").mkdir(parents=True, exist_ok=True)

# Production Dataset Paths
GROUND_TRUTH_DATASET_PATH = DATA_DIR / "ground_truth.json"
SAFETY_BENCHMARK_DATASET_PATH = DATA_DIR / "safety_benchmark.json"

# Transformer Model Selection
MODEL_NAME = os.getenv("MODEL_NAME", "distilbert-base-uncased")
RANDOM_SEED = 42

# Task 1: Candidate Validity Classification
VALIDITY_LABELS = ["FALSE_POSITIVE", "TRUE_POSITIVE"]
VALIDITY_LABEL2ID: Dict[str, int] = {"FALSE_POSITIVE": 0, "TRUE_POSITIVE": 1}
VALIDITY_ID2LABEL: Dict[int, str] = {0: "FALSE_POSITIVE", 1: "TRUE_POSITIVE"}

# Task 2: Severity Classification
SEVERITY_LABELS = ["low", "medium", "high", "critical"]
SEVERITY_CONFIG_A_LABELS = ["medium", "high"]
SEVERITY_CONFIG_A_LABEL2ID: Dict[str, int] = {"medium": 0, "high": 1}
SEVERITY_CONFIG_A_ID2LABEL: Dict[int, str] = {0: "medium", 1: "high"}

# Production Calibrated Thresholds & Limits
PRODUCTION_THRESHOLD = 0.40
PRODUCTION_DRIFT_THRESHOLD = 0.30
PRODUCTION_PAYLOAD_LIMIT_BYTES = 500 * 1024  # 500 KB safe limit

# Default Training Hyperparameters
DEFAULT_TRAINING_CONFIG = {
    "model_name": MODEL_NAME,
    "random_seed": RANDOM_SEED,
    "max_length": 256,
    "learning_rate": 3e-5,
    "train_batch_size": 8,
    "eval_batch_size": 16,
    "num_train_epochs": 8,
    "weight_decay": 0.01,
    "warmup_ratio": 0.1,
    "early_stopping_patience": 3,
}
