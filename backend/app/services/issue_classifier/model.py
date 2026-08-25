"""
model.py — Multi-Task DistilBERT Architecture for Severity & Priority.
======================================================================
Implements a single shared DistilBERT encoder backbone with two distinct
classification heads for multi-task learning.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple, Union

import torch
import torch.nn as nn
from transformers import DistilBertModel, DistilBertPreTrainedModel

from .config import ModelConfig


class MultiTaskDistilBertClassifier(DistilBertPreTrainedModel):
    """
    Multi-task classification model based on DistilBERT.

    Architecture:
        DistilBERT Backbone (shared encoder)
            │
            ├─→ [CLS] Hidden State
            │       │
            │       ├─→ Dropout ─→ Severity Head (Linear: 768 → 4)
            │       │
            │       └─→ Dropout ─→ Priority Head (Linear: 768 → 4)
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        model_config: Optional[ModelConfig] = None,
        severity_class_weights: Optional[torch.Tensor] = None,
        priority_class_weights: Optional[torch.Tensor] = None,
        severity_loss_weight: float = 0.5,
        priority_loss_weight: float = 0.5,
    ) -> None:
        if config is None:
            from transformers import DistilBertConfig
            config = DistilBertConfig.from_pretrained(
                model_config.pretrained_model_name if model_config else "distilbert-base-uncased"
            )

        super().__init__(config)

        self.model_config = model_config or ModelConfig()
        self.num_severity_classes = self.model_config.num_severity_classes
        self.num_priority_classes = self.model_config.num_priority_classes
        self.severity_loss_weight = severity_loss_weight
        self.priority_loss_weight = priority_loss_weight

        # Shared DistilBERT encoder
        self.distilbert = DistilBertModel(config)

        # Classification Heads
        hidden_size = config.dim
        dropout_rate = self.model_config.dropout_prob

        self.dropout = nn.Dropout(dropout_rate)
        self.severity_head = nn.Linear(hidden_size, self.num_severity_classes)
        self.priority_head = nn.Linear(hidden_size, self.num_priority_classes)

        # Register optional class weights buffers for imbalanced loss computation
        if severity_class_weights is not None:
            self.register_buffer("severity_class_weights", severity_class_weights)
        else:
            self.severity_class_weights = None

        if priority_class_weights is not None:
            self.register_buffer("priority_class_weights", priority_class_weights)
        else:
            self.priority_class_weights = None

        # Initialize weights
        self.init_weights()

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        severity_labels: Optional[torch.Tensor] = None,
        priority_labels: Optional[torch.Tensor] = None,
    ) -> Dict[str, Union[torch.Tensor, None]]:
        """
        Forward pass for multi-task issue classification.

        Parameters
        ----------
        input_ids : torch.Tensor of shape (batch_size, seq_len)
        attention_mask : torch.Tensor of shape (batch_size, seq_len), optional
        severity_labels : torch.Tensor of shape (batch_size,), optional
        priority_labels : torch.Tensor of shape (batch_size,), optional

        Returns
        -------
        dict containing:
            - 'severity_logits': Tensor of shape (batch_size, num_severity_classes)
            - 'priority_logits': Tensor of shape (batch_size, num_priority_classes)
            - 'severity_probabilities': Tensor of shape (batch_size, num_severity_classes)
            - 'priority_probabilities': Tensor of shape (batch_size, num_priority_classes)
            - 'severity_loss': scalar Tensor (if labels provided)
            - 'priority_loss': scalar Tensor (if labels provided)
            - 'loss': scalar total combined loss Tensor (if labels provided)
        """
        # Encoder forward pass
        distilbert_output = self.distilbert(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        # Extract [CLS] token representation (index 0)
        hidden_state = distilbert_output[0]  # (batch_size, seq_len, dim)
        cls_rep = hidden_state[:, 0]  # (batch_size, dim)
        pooled = self.dropout(cls_rep)

        # Compute logits for both tasks
        severity_logits = self.severity_head(pooled)
        priority_logits = self.priority_head(pooled)

        # Softmax probabilities
        severity_probs = torch.softmax(severity_logits, dim=-1)
        priority_probs = torch.softmax(priority_logits, dim=-1)

        output: Dict[str, Any] = {
            "severity_logits": severity_logits,
            "priority_logits": priority_logits,
            "severity_probabilities": severity_probs,
            "priority_probabilities": priority_probs,
            "severity_loss": None,
            "priority_loss": None,
            "loss": None,
        }

        # Multi-task loss computation if labels are provided
        total_loss = torch.tensor(0.0, device=input_ids.device)
        has_loss = False

        if severity_labels is not None:
            loss_fct_sev = nn.CrossEntropyLoss(weight=self.severity_class_weights)
            sev_loss = loss_fct_sev(severity_logits.view(-1, self.num_severity_classes), severity_labels.view(-1))
            output["severity_loss"] = sev_loss
            total_loss = total_loss + (self.severity_loss_weight * sev_loss)
            has_loss = True

        if priority_labels is not None:
            loss_fct_prio = nn.CrossEntropyLoss(weight=self.priority_class_weights)
            prio_loss = loss_fct_prio(priority_logits.view(-1, self.num_priority_classes), priority_labels.view(-1))
            output["priority_loss"] = prio_loss
            total_loss = total_loss + (self.priority_loss_weight * prio_loss)
            has_loss = True

        if has_loss:
            output["loss"] = total_loss

        return output
