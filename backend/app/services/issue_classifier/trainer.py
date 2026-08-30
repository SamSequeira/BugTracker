"""
trainer.py — Multi-Task Training, Optimization & Checkpointing.
================================================================
Orchestrates model training, AdamW optimization, class-weighted loss,
validation monitoring, early stopping on mean Macro-F1, and artifact saving.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, get_linear_schedule_with_warmup

from .config import (
    ModelConfig,
    PRIORITY_LABELS,
    PRIORITY_TO_ID,
    SEVERITY_LABELS,
    SEVERITY_TO_ID,
    TrainingConfig,
)
from .dataset import DatasetPipeline, IssueDataset
from .evaluator import MultiTaskEvaluator
from .model import MultiTaskDistilBertClassifier
from .normalizer import IssueNormalizer

logger = logging.getLogger(__name__)


class MultiTaskTrainer:
    """Trainer for multi-task issue classification with DistilBERT."""

    def __init__(
        self,
        model_config: Optional[ModelConfig] = None,
        training_config: Optional[TrainingConfig] = None,
        device: Optional[str] = None,
    ) -> None:
        self.model_config = model_config or ModelConfig()
        self.training_config = training_config or TrainingConfig()

        # Device selection: automatic GPU detection with CPU fallback
        if device is None or device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        logger.info(f"MultiTaskTrainer initialized on device: {self.device}")

        self.normalizer = IssueNormalizer()
        self.pipeline = DatasetPipeline(normalizer=self.normalizer)
        self.evaluator = MultiTaskEvaluator()

        self.tokenizer = AutoTokenizer.from_pretrained(self.model_config.pretrained_model_name)

    def train(
        self,
        train_records: List[Dict[str, Any]],
        val_records: List[Dict[str, Any]],
        test_records: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Execute the full multi-task training and validation loop.
        """
        # Validate data presence
        if len(train_records) == 0 or len(val_records) == 0:
            raise ValueError("Training requires non-empty train and validation datasets.")

        # Compute class weights if configured
        sev_weights = None
        prio_weights = None
        if self.training_config.use_class_weights:
            sev_labels = [SEVERITY_TO_ID[str(r["severity"]).strip().lower()] for r in train_records]
            prio_labels = [PRIORITY_TO_ID[str(r["priority"]).strip().lower()] for r in train_records]
            sev_weights = self.pipeline.compute_class_weights(sev_labels, self.model_config.num_severity_classes).to(self.device)
            prio_weights = self.pipeline.compute_class_weights(prio_labels, self.model_config.num_priority_classes).to(self.device)

        # Instantiate Model
        model = MultiTaskDistilBertClassifier.from_pretrained(
            self.model_config.pretrained_model_name,
            model_config=self.model_config,
            severity_class_weights=sev_weights,
            priority_class_weights=prio_weights,
            severity_loss_weight=self.training_config.severity_loss_weight,
            priority_loss_weight=self.training_config.priority_loss_weight,
        ).to(self.device)

        # Prepare PyTorch Datasets & DataLoaders
        train_dataset = self.pipeline.encode_records(train_records, self.tokenizer, self.model_config.max_length)
        val_dataset = self.pipeline.encode_records(val_records, self.tokenizer, self.model_config.max_length)

        train_loader = DataLoader(train_dataset, batch_size=self.training_config.batch_size, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=self.training_config.batch_size, shuffle=False)

        # Optimizer and LR Scheduler
        optimizer = AdamW(model.parameters(), lr=self.training_config.learning_rate, weight_decay=self.training_config.weight_decay)
        total_steps = len(train_loader) * self.training_config.epochs
        warmup_steps = int(total_steps * self.training_config.warmup_ratio)
        scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps)

        best_val_score = -1.0
        best_epoch = 0
        patience_counter = 0
        best_val_metrics: Dict[str, Any] = {}
        best_model_state = None

        logger.info(f"Starting training for {self.training_config.epochs} epochs ({total_steps} total steps)...")

        for epoch in range(1, self.training_config.epochs + 1):
            model.train()
            train_loss_total = 0.0

            for batch in train_loader:
                optimizer.zero_grad()

                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                severity_labels = batch["severity_labels"].to(self.device)
                priority_labels = batch["priority_labels"].to(self.device)

                outputs = model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    severity_labels=severity_labels,
                    priority_labels=priority_labels,
                )

                loss = outputs["loss"]
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), self.training_config.max_grad_norm)

                optimizer.step()
                scheduler.step()

                train_loss_total += loss.item()

            avg_train_loss = train_loss_total / len(train_loader)

            # Validation pass
            val_metrics = self._evaluate_model(model, val_loader)
            mean_macro_f1 = val_metrics["mean_macro_f1"]

            logger.info(
                f"Epoch {epoch}/{self.training_config.epochs} - "
                f"Train Loss: {avg_train_loss:.4f} | "
                f"Val Mean Macro-F1: {mean_macro_f1:.4f} | "
                f"Sev F1: {val_metrics['severity']['macro_f1']:.4f} | "
                f"Prio F1: {val_metrics['priority']['macro_f1']:.4f}"
            )

            # Early stopping check on validation mean macro-F1
            if mean_macro_f1 > best_val_score:
                best_val_score = mean_macro_f1
                best_epoch = epoch
                best_val_metrics = val_metrics
                best_model_state = {k: v.cpu() for k, v in model.state_dict().items()}
                patience_counter = 0
            else:
                patience_counter += 1
                if patience_counter >= self.training_config.early_stopping_patience:
                    logger.info(f"Early stopping triggered at epoch {epoch}. Best epoch was {best_epoch}.")
                    break

        # Load best model weights
        if best_model_state is not None:
            model.load_state_dict({k: v.to(self.device) for k, v in best_model_state})

        # Evaluate on Test set if provided
        test_metrics = None
        if test_records and len(test_records) > 0:
            test_dataset = self.pipeline.encode_records(test_records, self.tokenizer, self.model_config.max_length)
            test_loader = DataLoader(test_dataset, batch_size=self.training_config.batch_size, shuffle=False)
            test_metrics = self._evaluate_model(model, test_loader)

        # Save artifacts
        output_dir = Path(self.training_config.output_dir)
        self.save_artifacts(model, output_dir, best_val_metrics, test_metrics)

        return {
            "best_epoch": best_epoch,
            "best_validation_score": best_val_score,
            "validation_metrics": best_val_metrics,
            "test_metrics": test_metrics,
            "output_dir": str(output_dir),
        }

    def _evaluate_model(
        self,
        model: MultiTaskDistilBertClassifier,
        dataloader: DataLoader,
    ) -> Dict[str, Any]:
        """Internal helper to compute evaluation metrics over a dataloader."""
        model.eval()

        sev_preds, sev_trues = [], []
        prio_preds, prio_trues = [], []

        with torch.no_grad():
            for batch in dataloader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)

                outputs = model(input_ids=input_ids, attention_mask=attention_mask)

                s_pred = outputs["severity_logits"].argmax(dim=-1).cpu().tolist()
                p_pred = outputs["priority_logits"].argmax(dim=-1).cpu().tolist()

                sev_preds.extend(s_pred)
                prio_preds.extend(p_pred)

                if "severity_labels" in batch:
                    sev_trues.extend(batch["severity_labels"].tolist())
                if "priority_labels" in batch:
                    prio_trues.extend(batch["priority_labels"].tolist())

        return self.evaluator.evaluate(sev_trues, sev_preds, prio_trues, prio_preds)

    def save_artifacts(
        self,
        model: MultiTaskDistilBertClassifier,
        output_dir: Path,
        val_metrics: Dict[str, Any],
        test_metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Save model checkpoint, tokenizer, label maps, and metrics."""
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save model weights and config
        model.save_pretrained(output_dir)

        # 2. Save tokenizer
        self.tokenizer.save_pretrained(output_dir)

        # 3. Save label mappings
        label_mappings = {
            "severity_labels": SEVERITY_LABELS,
            "priority_labels": PRIORITY_LABELS,
            "severity_to_id": SEVERITY_TO_ID,
            "priority_to_id": PRIORITY_TO_ID,
        }
        with open(output_dir / "label_mappings.json", "w", encoding="utf-8") as f:
            json.dump(label_mappings, f, indent=2)

        # 4. Save configs
        config_data = {
            "model_config": self.model_config.__dict__,
            "training_config": self.training_config.__dict__,
        }
        with open(output_dir / "training_config.json", "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)

        # 5. Save metrics
        metrics_data = {
            "validation_metrics": val_metrics,
            "test_metrics": test_metrics,
        }
        with open(output_dir / "evaluation_metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics_data, f, indent=2)

        logger.info(f"Artifacts successfully saved to: {output_dir}")
