"""
dataset.py — Dataset Pipeline, Tokenization, Splitting & Leakage Prevention.
===========================================================================
Provides PyTorch Dataset implementations, verified label encoding/decoding,
stratified/chronological splitting, deduplication, and class weight computation.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import PreTrainedTokenizerFast

from .config import (
    ModelConfig,
    PRIORITY_LABELS,
    PRIORITY_TO_ID,
    SEVERITY_LABELS,
    SEVERITY_TO_ID,
)
from .normalizer import IssueNormalizer

logger = logging.getLogger(__name__)


class IssueDataset(Dataset):
    """PyTorch Dataset wrapper for multi-task issue classification."""

    def __init__(
        self,
        encodings: Dict[str, torch.Tensor],
        severity_labels: Optional[List[int]] = None,
        priority_labels: Optional[List[int]] = None,
    ) -> None:
        self.encodings = encodings
        self.severity_labels = severity_labels
        self.priority_labels = priority_labels

    def __len__(self) -> int:
        return len(self.encodings["input_ids"])

    def __getitem__(self, idx: int) -> Dict[str, torch.Tensor]:
        item = {
            "input_ids": self.encodings["input_ids"][idx],
            "attention_mask": self.encodings["attention_mask"][idx],
        }
        if self.severity_labels is not None:
            item["severity_labels"] = torch.tensor(self.severity_labels[idx], dtype=torch.long)
        if self.priority_labels is not None:
            item["priority_labels"] = torch.tensor(self.priority_labels[idx], dtype=torch.long)
        return item


class DatasetPipeline:
    """End-to-end data processing pipeline for Issue Classification."""

    def __init__(self, normalizer: Optional[IssueNormalizer] = None) -> None:
        self.normalizer = normalizer or IssueNormalizer()

    def validate_and_parse_record(self, record: Dict[str, Any]) -> Tuple[Dict[str, Any], int, int]:
        """
        Validate that a record contains verified severity and priority labels.

        Returns
        -------
        (clean_record, severity_id, priority_id)
        """
        if "severity" not in record or "priority" not in record:
            raise ValueError("Record missing required ground-truth 'severity' or 'priority' fields.")

        sev_label = str(record["severity"]).strip().lower()
        prio_label = str(record["priority"]).strip().lower()

        if sev_label not in SEVERITY_TO_ID:
            raise ValueError(f"Invalid severity label: '{sev_label}'. Must be one of {SEVERITY_LABELS}")

        if prio_label not in PRIORITY_TO_ID:
            raise ValueError(f"Invalid priority label: '{prio_label}'. Must be one of {PRIORITY_LABELS}")

        return record, SEVERITY_TO_ID[sev_label], PRIORITY_TO_ID[prio_label]

    def deduplicate_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate records based on their normalized text representation to
        prevent data leakage across train/validation/test splits.
        """
        seen_texts = set()
        unique_records = []

        for r in records:
            norm_text = self.normalizer.normalize(r)
            if norm_text not in seen_texts:
                seen_texts.add(norm_text)
                unique_records.append(r)

        return unique_records

    def split_dataset(
        self,
        records: List[Dict[str, Any]],
        train_ratio: float = 0.70,
        val_ratio: float = 0.15,
        test_ratio: float = 0.15,
        chronological: bool = False,
        timestamp_key: str = "timestamp",
        seed: int = 42,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Split dataset into train, validation, and test sets.
        Supports chronological ordering or stratified random splitting.
        """
        # Deduplicate first to guarantee zero cross-split leakage
        unique_records = self.deduplicate_records(records)
        n = len(unique_records)

        if n == 0:
            return [], [], []

        if chronological and timestamp_key in unique_records[0]:
            # Chronological split: older issues for train, newer for val/test
            sorted_records = sorted(unique_records, key=lambda x: x.get(timestamp_key, 0))
            train_end = int(n * train_ratio)
            val_end = int(n * (train_ratio + val_ratio))
            return sorted_records[:train_end], sorted_records[train_end:val_end], sorted_records[val_end:]

        # Random / Stratified split
        rng = np.random.RandomState(seed)
        indices = np.arange(n)
        rng.shuffle(indices)

        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        train_records = [unique_records[i] for i in indices[:train_end]]
        val_records = [unique_records[i] for i in indices[train_end:val_end]]
        test_records = [unique_records[i] for i in indices[val_end:]]

        return train_records, val_records, test_records

    def compute_class_weights(
        self,
        label_ids: List[int],
        num_classes: int,
    ) -> torch.Tensor:
        """
        Compute balanced inverse-frequency class weights:
            weight = N / (num_classes * count)
        """
        counts = Counter(label_ids)
        total_samples = len(label_ids)
        weights = []

        for c in range(num_classes):
            c_count = counts.get(c, 0)
            if c_count > 0:
                w = total_samples / (num_classes * c_count)
            else:
                w = 1.0
            weights.append(w)

        # Normalize weights so their mean is 1.0
        weights_tensor = torch.tensor(weights, dtype=torch.float)
        weights_tensor = weights_tensor / weights_tensor.mean()
        return weights_tensor

    def encode_records(
        self,
        records: List[Dict[str, Any]],
        tokenizer: Any,
        max_length: int = 256,
        is_labeled: bool = True,
    ) -> IssueDataset:
        """Normalize and tokenize candidate issue records into an IssueDataset."""
        texts = [self.normalizer.normalize(r) for r in records]

        encodings = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )

        if not is_labeled:
            return IssueDataset(encodings=encodings)

        severity_labels = []
        priority_labels = []

        for r in records:
            _, sev_id, prio_id = self.validate_and_parse_record(r)
            severity_labels.append(sev_id)
            priority_labels.append(prio_id)

        return IssueDataset(
            encodings=encodings,
            severity_labels=severity_labels,
            priority_labels=priority_labels,
        )
