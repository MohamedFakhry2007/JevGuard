import pytest

from jevguard.calibration import Calibrator
from jevguard.evalset.metrics import (
    ItemResult,
    auc,
    caught,
    fit_calibrators,
    percentile,
    signal_truth,
    summarize,
    wilson,
)
from jevguard.evalset.schema import Labels
from jevguard.policy import Policy
from jevguard.schemas import Action

A = Action


def res(i, expected, predicted, kind="unsafe", category="c", tags=(), lat=0.0, tot=1.0, cost=0.0, failure=None):
    return ItemResult(id=str(i), split="dev", kind=kind, category=category, tags=list(tags), expected=expected,
                      predicted=predicted, latency_ms=lat, total_ms=tot, cost_usd=cost, failure=failure)


def test_wilson_reference_values():
    assert wilson(0, 10)[0] == 0.0 and wilson(0, 10)[1] == pytest.approx(0.2775, abs=1e-3)
    assert wilson(10, 10)[1] == 1.0 and wilson(10, 10)[0] == pytest.approx(0.7225, abs=1e-3)
    assert wilson(5, 10) == pytest.approx((0.2366, 0.7634), abs=1e-3)
    assert wilson(0, 0) == (0.0, 1.0)


def test_percentile_nearest_rank():
    v = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(v, 0.5) == 30.0 and percentile(v, 0.95) == 50.0 and percentile([], 0.5) is None


def test_auc_perfect_random_and_undefined():
    assert auc([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0]) == 1.0
    assert auc([0.5, 0.5, 0.5, 0.5], [1, 0, 1, 0]) == 0.5
    assert auc([0.9, 0.1], [1, 1]) is None


def test_caught_semantics():
    assert caught(A.BLOCK, A.ESCALATE) and caught(A.CORRECT, A.BLOCK)  # any intervention counts
    assert not caught(A.BLOCK, A.FLAG) and not caught(A.ESCALATE, A.PASS)
    assert caught(A.FLAG, A.FLAG) and caught(A.FLAG, A.BLOCK) and not caught(A.FLAG, A.PASS)


def test_summary_rates_and_errors_are_counted_separately():
    rs = [
        res(1, A.BLOCK, A.BLOCK), res(2, A.BLOCK, A.FLAG), res(3, A.ESCALATE, A.BLOCK),  # 2 of 3 caught, 1 under-severe
        res(4, A.CORRECT, A.ESCALATE),  # caught, over-severe
        res(5, A.PASS, A.PASS, kind="safe"), res(6, A.PASS, A.BLOCK, kind="safe"),  # one false block
        res(7, A.FLAG, A.CORRECT, kind="hard_negative"),  # gold flag, predicted intervention
    ]
    s = summarize(rs)
    assert (s["intervention_recall"]["k"], s["intervention_recall"]["n"]) == (3, 4)
    # items 1 and 4 reach the gold severity; item 2 is flagged only; item 3 (block for a gold escalate) is under-severe
    assert (s["full_severity_recall"]["k"], s["full_severity_recall"]["n"]) == (2, 4)
    assert s["false_intervention_rate"]["k"] == 2 and s["false_intervention_rate"]["n"] == 3
    assert s["false_intervention_on_gold_pass"]["k"] == 1 and s["false_intervention_on_gold_pass"]["n"] == 2
    assert s["over_severe_on_interventions"]["k"] == 1
    assert s["escalation_rate_all"]["k"] == 1
    assert s["confusion"]["block"] == {"block": 1, "flag": 1}


def test_summary_by_tag_splits_caught_and_false_intervention():
    rs = [res(1, A.BLOCK, A.BLOCK, tags=["injection"]), res(2, A.BLOCK, A.PASS, tags=["injection"]),
          res(3, A.PASS, A.PASS, kind="hard_negative", tags=["injection"])]
    row = summarize(rs)["by_tag"]["injection"]
    assert row["caught"]["k"] == 1 and row["caught"]["n"] == 2 and row["false_intervention"]["k"] == 0


def test_summary_latency_cost_and_failures():
    rs = [res(i, A.PASS, A.PASS, kind="safe", lat=100.0 * (i + 1), tot=110.0 * (i + 1), cost=0.0001) for i in range(4)]
    rs[0] = res(0, A.PASS, A.ESCALATE, kind="safe", lat=100.0, tot=110.0, cost=0.0001, failure="timeout")
    s = summarize(rs)
    assert s["latency_ms"]["p50"] == 200.0 and s["total_ms"]["p95"] == 440.0
    assert s["cost_per_1k_checks_usd"] == pytest.approx(0.1) and s["fail_closed_count"] == 1


def test_signal_truth_covers_every_policy_signal():
    truth = signal_truth(Labels())
    assert set(Policy.load().signals) == set(truth)


def test_signal_truth_composite_uses_emergency_evidence():
    assert signal_truth(Labels(request_scope="emergency"))["red_flag_no_urgent"]
    assert not signal_truth(Labels(request_scope="emergency", urgent_care_advised=True))["red_flag_no_urgent"]


def test_fit_calibrators_keep_identity_without_enough_positives():
    from jevguard.evalset.build import build_items
    items = {i.id: i for i in build_items() if i.split == "dev"}
    rs = [ItemResult(id=k, split="dev", kind=v.kind, category=v.category, expected=v.expected_action,
                     predicted=A.PASS, signals={s: {"p_raw": 0.9 if t else 0.05, "p": 0.5}
                                                for s, t in signal_truth(v.labels).items()})
          for k, v in items.items()]
    cals = fit_calibrators(rs, items)
    assert set(cals) == set(Policy.load().signals)
    assert cals["scope_diagnosis_request"] == Calibrator(n_fit=len(items))  # too few positives on dev
