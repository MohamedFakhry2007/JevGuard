import random

import pytest

from jevguard.calibration import MIN_FIT_N, Calibrator, brier, ece, fit, load, log_loss, save


def _overconfident(n=400, seed=1):
    """Labels are true only 70% of the time when the model says 0.95 (overconfident)."""
    rng = random.Random(seed)
    probs, labels = [], []
    for _ in range(n):
        p = 0.95 if rng.random() < 0.5 else 0.05
        y = int(rng.random() < (0.7 if p > 0.5 else 0.3))
        probs.append(p)
        labels.append(y)
    return probs, labels


def test_identity_by_default():
    assert Calibrator().apply(0.8) == pytest.approx(0.8, abs=1e-6)


def test_monotone():
    c = Calibrator(temperature=2.0, bias=-0.5)
    xs = [i / 20 for i in range(21)]
    ys = [c.apply(x) for x in xs]
    assert ys == sorted(ys)


def test_fit_reduces_loss_and_ece_on_overconfident_data():
    probs, labels = _overconfident()
    cal = fit(probs, labels)
    after = [cal.apply(p) for p in probs]
    assert cal.temperature > 1.0
    assert log_loss(after, labels) < log_loss(probs, labels)
    assert ece(after, labels) < ece(probs, labels)
    assert brier(after, labels) < brier(probs, labels)


def test_fit_falls_back_to_identity_when_data_cannot_support_it():
    assert fit([0.9] * (MIN_FIT_N - 1), [1] * (MIN_FIT_N - 1)) == Calibrator(n_fit=MIN_FIT_N - 1)
    same = fit([0.5] * 100, [1] * 100)
    assert (same.temperature, same.bias) == (1.0, 0.0)


def test_ece_zero_for_perfectly_calibrated():
    assert ece([0.0, 1.0, 0.0, 1.0], [0, 1, 0, 1]) == pytest.approx(0.0)


def test_save_load_roundtrip(tmp_path):
    cals = {"dose_stated": Calibrator(temperature=2.5, bias=0.25, n_fit=80)}
    save(cals, tmp_path / "c.json")
    assert load(tmp_path / "c.json") == cals
