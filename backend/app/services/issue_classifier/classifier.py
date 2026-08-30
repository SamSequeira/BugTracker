"""
classifier.py — Issue Classifier Inference Engine & Output Enrichment.
========================================================================
Loads trained multi-task checkpoints, computes probability distributions,
evaluates confidence thresholds (flagging needs_review), and enriches
candidate issue dictionaries with ML predictions.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import torch
from transformers import AutoTokenizer

from .config import (
    ID_TO_PRIORITY,
    ID_TO_SEVERITY,
    InferenceConfig,
    PRIORITY_LABELS,
    SEVERITY_LABELS,
)
from .model import MultiTaskDistilBertClassifier
from .normalizer import IssueNormalizer

logger = logging.getLogger(__name__)


class IssueClassifier:
    """
    Inference service for classifying candidate issues by Severity and Priority.
    """

    def __init__(
        self,
        config: Optional[InferenceConfig] = None,
        model_dir: Optional[str] = None,
        model: Optional[MultiTaskDistilBertClassifier] = None,
        tokenizer: Optional[Any] = None,
    ) -> None:
        self.config = config or InferenceConfig()
        if model_dir:
            self.config.model_dir = model_dir

        # Device selection: automatic GPU detection with CPU fallback
        if self.config.device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(self.config.device)

        self.normalizer = IssueNormalizer()
        self.model = model
        self.tokenizer = tokenizer

        # Load from disk if model is not provided directly
        if self.model is None and Path(self.config.model_dir).exists():
            self.load_model(self.config.model_dir)

    def load_model(self, model_dir: Union[str, Path]) -> None:
        """Load trained weights, tokenizer, and config from disk."""
        path = Path(model_dir)
        if not path.exists():
            raise FileNotFoundError(f"Model directory not found at: {path}")

        logger.info(f"Loading Issue Classifier model from: {path} on device {self.device}")
        self.tokenizer = AutoTokenizer.from_pretrained(str(path))
        self.model = MultiTaskDistilBertClassifier.from_pretrained(str(path)).to(self.device)
        self.model.eval()

    def predict_batch(
        self,
        issues: List[Union[Dict[str, Any], Any]],
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Run multi-task inference on a batch of candidate issues.

        Returns
        -------
        List of classification dicts:
        [
          {
            "severity": {
              "label": "high",
              "confidence": 0.94,
              "probabilities": { "critical": 0.03, ... }
            },
            "priority": {
              "label": "p1",
              "confidence": 0.88,
              "probabilities": { "p1": 0.88, ... }
            },
            "needs_review": False
          },
          ...
        ]
        """
        if not issues:
            return []

        if self.model is None or self.tokenizer is None:
            raise RuntimeError("IssueClassifier model is not initialized or trained.")

        self.model.eval()
        texts = [self.normalizer.normalize(i, language=language) for i in issues]

        inputs = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        if hasattr(inputs, "to"):
            inputs = inputs.to(self.device)
        else:
            inputs = {k: v.to(self.device) if hasattr(v, "to") else v for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self.model(
                input_ids=inputs["input_ids"],
                attention_mask=inputs["attention_mask"],
            )

            sev_probs = outputs["severity_probabilities"].cpu().numpy()  # (B, 4)
            prio_probs = outputs["priority_probabilities"].cpu().numpy()  # (B, 4)

        results = []
        for i in range(len(issues)):
            s_dist = {label: round(float(sev_probs[i][idx]), 4) for idx, label in enumerate(SEVERITY_LABELS)}
            p_dist = {label: round(float(prio_probs[i][idx]), 4) for idx, label in enumerate(PRIORITY_LABELS)}

            best_s_idx = int(sev_probs[i].argmax())
            best_p_idx = int(prio_probs[i].argmax())

            best_s_label = ID_TO_SEVERITY[best_s_idx]
            best_p_label = ID_TO_PRIORITY[best_p_idx]

            conf_s = round(float(sev_probs[i][best_s_idx]), 4)
            conf_p = round(float(prio_probs[i][best_p_idx]), 4)

            # Confidence thresholding: needs_review if below threshold
            needs_review = (
                conf_s < self.config.confidence_threshold or
                conf_p < self.config.confidence_threshold
            )

            results.append({
                "severity": {
                    "label": best_s_label,
                    "confidence": conf_s,
                    "probabilities": s_dist,
                },
                "priority": {
                    "label": best_p_label,
                    "confidence": conf_p,
                    "probabilities": p_dist,
                },
                "needs_review": needs_review,
            })

        return results

    def enrich_candidate_issue(
        self,
        issue: Union[Dict[str, Any], Any],
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Preserve original candidate issue data and append ML classification."""
        if hasattr(issue, "to_dict"):
            data = issue.to_dict()
        elif isinstance(issue, dict):
            data = dict(issue)
        else:
            data = getattr(issue, "__dict__", {})

        pred = self.predict_batch([data], language=language)[0]
        data["classification"] = pred
        return data

    def enrich_candidate_issues_batch(
        self,
        issues: List[Union[Dict[str, Any], Any]],
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Preserve original candidate issue data and append ML classification in batch."""
        if not issues:
            return []

        dict_issues = []
        for i in issues:
            if hasattr(i, "to_dict"):
                dict_issues.append(i.to_dict())
            elif isinstance(i, dict):
                dict_issues.append(dict(i))
            else:
                dict_issues.append(getattr(i, "__dict__", {}))

        predictions = self.predict_batch(dict_issues, language=language)

        for d, p in zip(dict_issues, predictions):
            d["classification"] = p

        return dict_issues

    def classify_repository_analysis(
        self,
        analysis_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Takes raw static analyzer repository analysis output and returns
        the enriched output with ML classification for every issue.
        """
        enriched_result = dict(analysis_result)

        if "results" in enriched_result:
            for file_res in enriched_result["results"]:
                issues = file_res.get("issues", [])
                lang = file_res.get("language")
                if issues:
                    file_res["issues"] = self.enrich_candidate_issues_batch(issues, language=lang)

        if "issues" in enriched_result and isinstance(enriched_result["issues"], list):
            lang = enriched_result.get("language")
            enriched_result["issues"] = self.enrich_candidate_issues_batch(
                enriched_result["issues"], language=lang
            )

        return enriched_result
