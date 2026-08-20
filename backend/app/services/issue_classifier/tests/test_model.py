"""
Unit tests for MultiTaskDistilBertClassifier architecture and forward pass.
"""
from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent.parent.parent.parent.resolve()))

import torch
from transformers import DistilBertConfig

from app.services.issue_classifier.config import ModelConfig
from app.services.issue_classifier.model import MultiTaskDistilBertClassifier


class TestMultiTaskModel(unittest.TestCase):

    def setUp(self):
        # Use a small test config to keep unit test fast
        self.config = DistilBertConfig(
            vocab_size=100,
            dim=64,
            n_layers=2,
            n_heads=2,
            hidden_dim=128,
        )
        self.model_config = ModelConfig(
            num_severity_classes=4,
            num_priority_classes=4,
            dropout_prob=0.1,
        )
        self.model = MultiTaskDistilBertClassifier(
            config=self.config,
            model_config=self.model_config,
            severity_loss_weight=0.5,
            priority_loss_weight=0.5,
        )

    def test_forward_dimensions(self):
        batch_size = 3
        seq_len = 16
        input_ids = torch.randint(0, 100, (batch_size, seq_len))
        attention_mask = torch.ones((batch_size, seq_len))

        outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)

        # Check logits shapes
        self.assertEqual(outputs["severity_logits"].shape, (batch_size, 4))
        self.assertEqual(outputs["priority_logits"].shape, (batch_size, 4))

        # Check probability shapes
        self.assertEqual(outputs["severity_probabilities"].shape, (batch_size, 4))
        self.assertEqual(outputs["priority_probabilities"].shape, (batch_size, 4))

        # Probabilities must sum to 1.0 along class dimension
        sev_sums = outputs["severity_probabilities"].sum(dim=-1)
        prio_sums = outputs["priority_probabilities"].sum(dim=-1)
        self.assertTrue(torch.allclose(sev_sums, torch.ones(batch_size), atol=1e-5))
        self.assertTrue(torch.allclose(prio_sums, torch.ones(batch_size), atol=1e-5))

        # No loss when labels are not provided
        self.assertIsNone(outputs["loss"])

    def test_multi_task_loss_computation(self):
        batch_size = 4
        seq_len = 16
        input_ids = torch.randint(0, 100, (batch_size, seq_len))
        attention_mask = torch.ones((batch_size, seq_len))

        severity_labels = torch.tensor([0, 1, 2, 3])
        priority_labels = torch.tensor([3, 2, 1, 0])

        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            severity_labels=severity_labels,
            priority_labels=priority_labels,
        )

        self.assertIsNotNone(outputs["loss"])
        self.assertIsNotNone(outputs["severity_loss"])
        self.assertIsNotNone(outputs["priority_loss"])

        # Total loss = 0.5 * sev_loss + 0.5 * prio_loss
        expected_total = 0.5 * outputs["severity_loss"] + 0.5 * outputs["priority_loss"]
        self.assertTrue(torch.allclose(outputs["loss"], expected_total, atol=1e-5))


if __name__ == "__main__":
    unittest.main()
