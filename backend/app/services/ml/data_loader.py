"""
data_loader.py — Production Dataset Loading & Task Preparation.
===============================================================
Loads canonical ground-truth datasets, prepares feature texts and numeric labels
for validity and severity tasks, and computes balanced training class weights.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .config import (
    GROUND_TRUTH_DATASET_PATH,
    SAFETY_BENCHMARK_DATASET_PATH,
    SEVERITY_CONFIG_A_LABEL2ID,
    VALIDITY_LABEL2ID,
)
from .input_builder import build_input_text


def load_ground_truth_dataset(path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads the canonical ground-truth dataset for production training & evaluation."""
    target_path = path or GROUND_TRUTH_DATASET_PATH
    if not target_path.exists():
        raise FileNotFoundError(f"Ground truth dataset not found at: {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_safety_benchmark_dataset(path: Optional[Path] = None) -> Dict[str, Any]:
    """Loads the frozen safety benchmark dataset (historical TP & FP cases)."""
    target_path = path or SAFETY_BENCHMARK_DATASET_PATH
    if not target_path.exists():
        raise FileNotFoundError(f"Safety benchmark dataset not found at: {target_path}")
    with open(target_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Backward compatibility aliases
load_phase10_dataset = load_ground_truth_dataset
load_phase65_dataset = load_safety_benchmark_dataset


def prepare_validity_data(
    records: List[Dict[str, Any]],
    representation: str = "structured",
) -> Tuple[List[str], List[int], List[Dict[str, Any]]]:
    """
    Prepares Stage 1 Validity data (TRUE_POSITIVE vs FALSE_POSITIVE).
    Returns: (texts, labels, raw_records)
    """
    texts: List[str] = []
    labels: List[int] = []
    filtered_records: List[Dict[str, Any]] = []

    for r in records:
        gt = r.get("ground_truth") or r.get("label")
        if gt not in VALIDITY_LABEL2ID:
            continue
        text_input = build_input_text(r, representation=representation)
        texts.append(text_input)
        labels.append(VALIDITY_LABEL2ID[gt])
        filtered_records.append(r)

    return texts, labels, filtered_records


def prepare_severity_data(
    records: List[Dict[str, Any]],
    representation: str = "structured",
) -> Tuple[List[str], List[int], List[Dict[str, Any]]]:
    """
    Prepares Stage 2 Severity data for confirmed/predicted TRUE_POSITIVE items.
    Returns: (texts, labels, raw_records)
    """
    texts: List[str] = []
    labels: List[int] = []
    filtered_records: List[Dict[str, Any]] = []

    for r in records:
        if (r.get("ground_truth") or r.get("label")) != "TRUE_POSITIVE":
            continue

        raw_sev = (r.get("severity") or "").lower().strip()
        if raw_sev not in SEVERITY_CONFIG_A_LABEL2ID:
            continue

        lbl_id = SEVERITY_CONFIG_A_LABEL2ID[raw_sev]
        text_input = build_input_text(r, representation=representation)
        texts.append(text_input)
        labels.append(lbl_id)
        filtered_records.append(r)

    return texts, labels, filtered_records


def compute_training_class_weights(y_train: List[int]) -> Dict[int, float]:
    """
    Computes balanced class weights strictly on the training partition.
    Formula: weight[c] = total_train_samples / (n_classes * count[c])
    """
    if not y_train:
        return {}
    classes, counts = np.unique(y_train, return_counts=True)
    n_samples = len(y_train)
    n_classes = len(classes)
    weights: Dict[int, float] = {}
    for cls, count in zip(classes, counts):
        weights[int(cls)] = float(n_samples / (n_classes * count))
    return weights
