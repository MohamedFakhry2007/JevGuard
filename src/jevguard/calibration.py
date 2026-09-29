"""Per-signal calibration of Jev probabilities.

Why: MedJev measured raw Jev as overconfident (mean confidence about 0.9 at 0.29 to 0.8
accuracy) and recovered accuracy with per-question temperature and prior fitting. We fit
the same kind of correction on OUR labeled dev split, with pure-Python grid search.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from pydantic import BaseModel

EPS = 1e-3
MIN_FIT_N = 30


def _clip(p: float) -> float:
    return min(1 - EPS, max(EPS, p))


def _logit(p: float) -> float:
    p = _clip(p)
    return math.log(p / (1 - p))


def _sigmoid(z: float) -> float:
    return 1 / (1 + math.exp(-z))


class Calibrator(BaseModel):
    """p' = sigmoid(logit(p) / temperature + bias). Monotone in p."""

    temperature: float = 1.0
    bias: float = 0.0
    n_fit: int = 0

    def apply(self, p: float) -> float:
        return _sigmoid(_logit(p) / self.temperature + self.bias)


def log_loss(probs: list[float], labels: list[int]) -> float:
    return -sum(math.log(_clip(p) if y else 1 - _clip(p)) for p, y in zip(probs, labels)) / len(probs)


def brier(probs: list[float], labels: list[int]) -> float:
    return sum((p - y) ** 2 for p, y in zip(probs, labels)) / len(probs)


def ece(probs: list[float], labels: list[int], bins: int = 10) -> float:
    """Expected calibration error for a binary probability (top-label style on P(true))."""
    n = len(probs)
    total = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if lo <= p < hi or (b == bins - 1 and p == 1.0)]
        if idx:
            conf = sum(probs[i] for i in idx) / len(idx)
            freq = sum(labels[i] for i in idx) / len(idx)
            total += len(idx) / n * abs(conf - freq)
    return total


def fit(probs: list[float], labels: list[int]) -> Calibrator:
    """Grid-search temperature and bias minimising log loss. Falls back to identity when
    the data cannot support a fit (too small, or one class only)."""
    if len(probs) < MIN_FIT_N or len(set(labels)) < 2:
        return Calibrator(n_fit=len(probs))
    best = (float("inf"), 1.0, 0.0)
    for t in [0.5 + 0.25 * i for i in range(15)]:  # 0.5 .. 4.0
        for b in [-3.0 + 0.25 * j for j in range(25)]:  # -3 .. 3
            cal = Calibrator(temperature=t, bias=b)
            loss = log_loss([cal.apply(p) for p in probs], labels)
            if loss < best[0] - 1e-12:
                best = (loss, t, b)
    return Calibrator(temperature=best[1], bias=best[2], n_fit=len(probs))


def save(calibrators: dict[str, Calibrator], path: str | Path) -> None:
    Path(path).write_text(json.dumps({k: v.model_dump() for k, v in calibrators.items()}, indent=2))


def load(path: str | Path) -> dict[str, Calibrator]:
    return {k: Calibrator.model_validate(v) for k, v in json.loads(Path(path).read_text()).items()}
