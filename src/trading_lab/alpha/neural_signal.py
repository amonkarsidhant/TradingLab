"""Neural Signal Model — lightweight MLP classifier on engineered features.

Phase 3 Milestone 3: Pure numpy implementation (no torch/tf).
Input: 10 engineered features (normalized)
Hidden: [32, 16] with ReLU
Output: 3-class softmax (BUY=0, HOLD=1, SELL=2)

Constraints:
- Max 10k parameters
- Training time < 5 seconds per ticker
- Inference returns probability > 0.6 → signal with confidence = prob
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from trading_lab.alpha.features import FeatureSet

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NeuralSignal:
    """Output from the neural model."""

    action: str  # BUY, HOLD, SELL
    confidence: float  # probability of chosen class
    probabilities: dict[str, float]  # all 3 class probs
    raw_features: list[float]  # the 10 input features used


class NeuralSignalModel:
    """Tiny MLP for signal classification."""

    MAX_PARAMS = 10_000
    INPUT_DIM = 10
    HIDDEN_DIMS = [32, 16]
    OUTPUT_DIM = 3  # BUY, HOLD, SELL
    EPOCHS = 500
    LR = 0.001
    BATCH_SIZE = 64

    def __init__(self, feature_names: list[str] | None = None):
        self.feature_names = feature_names or [
            "rsi_14",
            "atr_14_pct",
            "price_vs_sma_20",
            "price_vs_sma_50",
            "volume_zscore_20",
            "momentum_5d",
            "momentum_20d",
            "bb_width",
            "atr_rank_20",
            "volume_ma_20",
        ]
        assert len(self.feature_names) == self.INPUT_DIM
        self.weights: list[np.ndarray] = []
        self.biases: list[np.ndarray] = []
        self._init_weights()

    # ── Architecture ──────────────────────────────────────────────────────────

    def _init_weights(self) -> None:
        """Xavier initialization."""
        dims = [self.INPUT_DIM] + self.HIDDEN_DIMS + [self.OUTPUT_DIM]
        total_params = sum(
            dims[i] * dims[i + 1] + dims[i + 1] for i in range(len(dims) - 1)
        )
        if total_params > self.MAX_PARAMS:
            raise ValueError(
                f"Model has {total_params} params, max {self.MAX_PARAMS}"
            )
        for i in range(len(dims) - 1):
            w = np.random.randn(dims[i], dims[i + 1]) * math.sqrt(2.0 / dims[i])
            b = np.zeros(dims[i + 1])
            self.weights.append(w)
            self.biases.append(b)

    def _relu(self, x: np.ndarray) -> np.ndarray:
        return np.maximum(0, x)

    def _softmax(self, x: np.ndarray) -> np.ndarray:
        # x shape: (batch, classes)
        x_shifted = x - np.max(x, axis=1, keepdims=True)
        exp_x = np.exp(x_shifted)
        return exp_x / np.sum(exp_x, axis=1, keepdims=True)

    def _forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass. x shape: (batch, input_dim)"""
        for w, b in zip(self.weights[:-1], self.biases[:-1]):
            x = self._relu(x @ w + b)
        # Output layer (no activation)
        logits = x @ self.weights[-1] + self.biases[-1]
        return self._softmax(logits)

    # ── Training ────────────────────────────────────────────────────────────────

    def train(
        self,
        feature_sets: list[FeatureSet],
        labels: np.ndarray,
    ) -> dict[str, float]:
        """Train on feature sets.

        feature_sets: list of FeatureSet (one per sample/ticker)
        labels: np.ndarray of shape (N,) with class indices 0,1,2

        Returns training metrics.
        """
        # Build input matrix
        X = self._build_input_matrix(feature_sets)
        if X.shape[0] != labels.shape[0]:
            raise ValueError(f"X rows {X.shape[0]} != labels {labels.shape[0]}")

        N = X.shape[0]
        if N == 0:
            return {"loss": float("inf"), "accuracy": 0.0}

        # Normalize features (z-score per column)
        self.mean = np.nanmean(X, axis=0)
        self.std = np.nanstd(X, axis=0)
        self.std = np.where(self.std == 0, 1.0, self.std)
        X_norm = (X - self.mean) / self.std

        # One-hot labels
        Y = np.zeros((N, self.OUTPUT_DIM))
        Y[np.arange(N), labels.astype(int)] = 1

        # Training loop
        for epoch in range(self.EPOCHS):
            # Mini-batch
            indices = np.random.permutation(N)
            total_loss = 0.0
            correct = 0

            for start in range(0, N, self.BATCH_SIZE):
                batch_idx = indices[start : start + self.BATCH_SIZE]
                batch_x = X_norm[batch_idx]
                batch_y = Y[batch_idx]

                # Forward
                a = batch_x
                activations = [a]
                for w, b in zip(self.weights[:-1], self.biases[:-1]):
                    z = a @ w + b
                    a = self._relu(z)
                    activations.append(a)
                z = a @ self.weights[-1] + self.biases[-1]
                a = self._softmax(z)
                activations.append(a)

                # Accuracy
                preds = np.argmax(a, axis=1)
                true = np.argmax(batch_y, axis=1)
                correct += np.sum(preds == true)

                # Loss (cross-entropy)
                loss = -np.sum(batch_y * np.log(a + 1e-8)) / batch_x.shape[0]
                total_loss += loss

                # Backprop
                delta = a - batch_y  # (batch, output)
                grads_w = []
                grads_b = []

                # Output layer
                grads_w.append(activations[-2].T @ delta / batch_x.shape[0])
                grads_b.append(np.mean(delta, axis=0))

                # Hidden layers (backwards)
                for i in range(len(self.weights) - 2, -1, -1):
                    delta = (delta @ self.weights[i + 1].T) * (activations[i + 1] > 0)
                    grads_w.insert(0, activations[i].T @ delta / batch_x.shape[0])
                    grads_b.insert(0, np.mean(delta, axis=0))

                # Update
                for i in range(len(self.weights)):
                    self.weights[i] -= self.LR * grads_w[i]
                    self.biases[i] -= self.LR * grads_b[i]

            if epoch % 100 == 0 and N > 0:
                acc = correct / N
                logger.debug("Epoch %d: loss=%.4f, acc=%.2f%%", epoch, total_loss, acc * 100)

        # Final metrics
        final_probs = self._forward(X_norm)
        final_preds = np.argmax(final_probs, axis=1)
        accuracy = np.mean(final_preds == labels) if N > 0 else 0.0
        final_loss = -np.sum(Y * np.log(final_probs + 1e-8)) / N if N > 0 else float("inf")

        return {"loss": float(final_loss), "accuracy": float(accuracy)}

    def predict(self, feature_set: FeatureSet) -> NeuralSignal:
        """Generate signal from a single FeatureSet."""
        x = self._extract_features(feature_set)
        if np.any(np.isnan(x)):
            return NeuralSignal(
                action="HOLD",
                confidence=0.0,
                probabilities={"BUY": 0.0, "HOLD": 1.0, "SELL": 0.0},
                raw_features=x.tolist(),
            )

        x_norm = (x - self.mean) / self.std
        x_norm = x_norm.reshape(1, -1)
        probs = self._forward(x_norm)[0]

        classes = ["BUY", "HOLD", "SELL"]
        idx = int(np.argmax(probs))
        confidence = float(probs[idx])

        return NeuralSignal(
            action=classes[idx],
            confidence=confidence,
            probabilities={c: float(p) for c, p in zip(classes, probs)},
            raw_features=x.tolist(),
        )

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _build_input_matrix(self, feature_sets: list[FeatureSet]) -> np.ndarray:
        """Stack feature vectors into (N, INPUT_DIM) matrix."""
        rows = []
        for fs in feature_sets:
            x = self._extract_features(fs)
            rows.append(x)
        return np.array(rows)

    def _extract_features(self, feature_set: FeatureSet) -> np.ndarray:
        """Extract the 10 features from a FeatureSet, using latest values."""
        vec = []
        for name in self.feature_names:
            val = feature_set.latest(name)
            if math.isnan(val):
                val = 0.0
            vec.append(val)
        return np.array(vec)

    def parameter_count(self) -> int:
        return sum(w.size + b.size for w, b in zip(self.weights, self.biases))


# ── Label Generation ─────────────────────────────────────────────────────────


def generate_labels_from_returns(returns: np.ndarray, threshold: float = 0.005) -> np.ndarray:
    """Generate class labels from next-day returns.

    BUY if return > threshold
    SELL if return < -threshold
    HOLD otherwise

    Labels are shifted: label[i] = direction of return[i+1]
    """
    labels = np.full(len(returns), 1)  # HOLD default
    for i in range(len(returns) - 1):
        r = returns[i + 1]
        if r > threshold:
            labels[i] = 0  # BUY
        elif r < -threshold:
            labels[i] = 2  # SELL
    return labels
