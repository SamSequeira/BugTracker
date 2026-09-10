"""
calibration.py — Post-Hoc Probability Calibration via Temperature Scaling.
==========================================================================
Fits temperature scaling parameters using validation split logits only.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np
from scipy.optimize import minimize


class TemperatureScaler:
    """
    Fits and applies a scalar temperature parameter T to calibrate logits.
    T is optimized strictly on validation split data using NLL loss.
    """

    def __init__(self) -> None:
        self.temperature: float = 1.0

    def fit(self, logits: np.ndarray, y_true: np.ndarray) -> float:
        """
        Fit temperature T > 0 on validation set logits using cross-entropy minimization.
        """
        if len(logits) == 0:
            return 1.0

        logits_arr = np.array(logits, dtype=float)
        y_arr = np.array(y_true, dtype=int)

        def _nll(temp: float) -> float:
            scaled = logits_arr / max(temp, 1e-4)
            # Softmax
            exp_scaled = np.exp(scaled - np.max(scaled, axis=1, keepdims=True))
            probs = exp_scaled / np.sum(exp_scaled, axis=1, keepdims=True)
            # Gather true class probabilities
            nll = -np.mean(np.log(np.clip(probs[np.arange(len(y_arr)), y_arr], 1e-12, 1.0)))
            return float(nll)

        res = minimize(_nll, x0=1.0, bounds=[(0.01, 10.0)], method="L-BFGS-B")
        self.temperature = float(res.x[0]) if res.success else 1.0
        return self.temperature

    def transform(self, logits: np.ndarray) -> np.ndarray:
        """Applies fitted temperature scaling to logits and returns calibrated probabilities."""
        logits_arr = np.array(logits, dtype=float)
        scaled = logits_arr / max(self.temperature, 1e-4)
        exp_scaled = np.exp(scaled - np.max(scaled, axis=1, keepdims=True))
        return exp_scaled / np.sum(exp_scaled, axis=1, keepdims=True)

    def scale_probabilities(self, logits: np.ndarray) -> np.ndarray:
        """Alias for transform."""
        return self.transform(logits)

