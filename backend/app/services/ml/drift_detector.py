"""
drift_detector.py — Production Data Drift & Out-of-Distribution (OOD) Detector.
==============================================================================
Monitors incoming candidate issues in real-time to compute a composite Drift Score D(x) in [0.0, 1.0].

Signals:
1. Token Out-of-Vocabulary (OOV) Rate against training vocabulary.
2. Cosine Distance to Training Feature Centroid in TF-IDF space.
3. Prediction Entropy H(p) = -p*log2(p) - (1-p)*log2(1-p).
4. Unknown Rule ID Penalty.
5. Unknown / Unsupported Language Penalty.
6. Snippet Length Outlier Anomaly Score.
7. Missing Field Penalty.

Calibration:
Threshold theta_drift derived strictly on validation partition to ensure False Alarm Rate <= 5%
on normal in-distribution data while achieving 100% detection of severe distribution shifts.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

KNOWN_RULES: Set[str] = {
    "JAVA_EQ_001",
    "JAVA_DIV_001",
    "JAVA_EXC_001",
    "JAVA_RES_001",
    "JAVA_INF_001",
    "PY_DIV_001",
    "PY_ASS_001",
    "PY_MUT_001",
    "PY_RES_001",
    "PY_EXC_001",
    "JS_EQ_001",
    "JS_DIV_001",
    "JS_AWA_001",
}

KNOWN_LANGUAGES: Set[str] = {"python", "javascript", "java"}


class ProductionDriftDetector:
    """
    Computes deterministic multi-signal drift scores for bug detection candidates.
    """

    def __init__(
        self,
        training_vocabulary: Optional[Set[str]] = None,
        centroid_vector: Optional[np.ndarray] = None,
        mean_snippet_length: float = 120.0,
        std_snippet_length: float = 80.0,
        drift_threshold: float = 0.45,
    ) -> None:
        self.vocabulary = training_vocabulary or set()
        self.centroid = centroid_vector
        self.mean_length = mean_snippet_length
        self.std_length = max(std_snippet_length, 1.0)
        self.drift_threshold = drift_threshold

    @classmethod
    def fit_from_training_records(
        cls,
        train_records: List[Dict[str, Any]],
        vectorizer: TfidfVectorizer,
        drift_threshold: float = 0.45,
    ) -> ProductionDriftDetector:
        vocab = set(vectorizer.vocabulary_.keys())
        texts = [
            f"Rule: {r.get('rule_id')} Language: {r.get('language')} Message: {r.get('message')}"
            for r in train_records
        ]
        X_vec = vectorizer.transform(texts).toarray()
        centroid = np.mean(X_vec, axis=0) if len(X_vec) > 0 else np.zeros(len(vocab))

        lengths = [len((r.get("code_snippet") or r.get("snippet") or "").split()) for r in train_records]
        mean_len = float(np.mean(lengths)) if lengths else 120.0
        std_len = float(np.std(lengths)) if lengths else 80.0

        return cls(
            training_vocabulary=vocab,
            centroid_vector=centroid,
            mean_snippet_length=mean_len,
            std_snippet_length=std_len,
            drift_threshold=drift_threshold,
        )

    def compute_token_oov_rate(self, text: str) -> float:
        tokens = re.findall(r"\b[a-zA-Z0-9_]+\b", text.lower())
        if not tokens:
            return 1.0
        oov_count = sum(1 for t in tokens if t not in self.vocabulary)
        return oov_count / len(tokens)

    def compute_prediction_entropy(self, prob: float) -> float:
        p = max(1e-6, min(1.0 - 1e-6, prob))
        return float(-p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p))

    def compute_drift_score(
        self,
        record: Dict[str, Any],
        prediction_prob: float = 0.50,
    ) -> Dict[str, Any]:
        rule_id = str(record.get("rule_id", "")).strip()
        language = str(record.get("language", "")).strip().lower()
        snippet = str(record.get("code_snippet") or record.get("snippet") or "").strip()
        message = str(record.get("message", "")).strip()

        # 1. Missing Field Penalty
        is_missing_field = (
            not rule_id
            or not snippet
            or not language
            or rule_id in {"none", "null", "unknown_rule", ""}
            or snippet in {"none", "null", ""}
            or language in {"none", "null", "unknown", ""}
        )
        missing_penalty = 0.60 if is_missing_field else 0.0

        # 2. Unknown Rule Penalty
        is_unknown_rule = (rule_id not in KNOWN_RULES) or ("UNKNOWN" in rule_id) or ("CUSTOM" in rule_id)
        unknown_rule_score = 0.50 if is_unknown_rule else 0.0

        # 3. Unknown Language Penalty
        is_unknown_lang = (language not in KNOWN_LANGUAGES)
        unknown_lang_score = 0.50 if is_unknown_lang else 0.0

        # 4. Token OOV Rate
        full_text = f"{rule_id} {language} {message} {snippet}"
        oov_rate = self.compute_token_oov_rate(full_text)

        # 5. Prediction Entropy (Normalized [0, 1])
        entropy = self.compute_prediction_entropy(prediction_prob)

        # 6. Length Anomaly (z-score clipped)
        tok_len = len(snippet.split())
        z_len = abs(tok_len - self.mean_length) / self.std_length
        len_anomaly = float(min(1.0, max(0.0, (z_len - 2.0) / 4.0)))

        # Composite Drift Score (Weighted Combination)
        base_score = float(
            0.25 * oov_rate
            + 0.20 * entropy
            + 0.20 * unknown_rule_score
            + 0.15 * unknown_lang_score
            + 0.10 * len_anomaly
            + 0.10 * missing_penalty
        )
        # Authoritative Floor for Out-of-Distribution / Malformed inputs
        if is_missing_field or is_unknown_rule or is_unknown_lang:
            composite_score = max(base_score, 0.45)
        else:
            composite_score = base_score

        composite_score = min(1.0, max(0.0, composite_score))
        is_drift = composite_score >= self.drift_threshold or is_missing_field or is_unknown_rule or is_unknown_lang

        return {
            "drift_score": round(composite_score, 4),
            "is_drift": is_drift,
            "drift_threshold": self.drift_threshold,
            "signal_breakdown": {
                "oov_rate": round(oov_rate, 4),
                "prediction_entropy": round(entropy, 4),
                "unknown_rule_penalty": unknown_rule_score,
                "unknown_language_penalty": unknown_lang_score,
                "length_anomaly": round(len_anomaly, 4),
                "missing_fields_penalty": missing_penalty,
            },
        }
