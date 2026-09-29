import json
from pathlib import Path

import pytest

from jevguard.backends import ReplayBackend
from jevguard.evalset import ablate
from jevguard.evalset.build import build_items
from jevguard.evalset.metrics import ItemResult
from jevguard.evalset.schema import EvalItem
from jevguard.evalset.tuning import ACT_FLOOR, HARD_CAP, MIN_UNCERTAIN, tune_policy
from jevguard.policy import Policy
from jevguard.schemas import Action, ChatTurn
from jevguard.testing import ScriptedBackend, make_response

REC = Path(__file__).resolve().parents[1] / "eval" / "recordings" / "dev.jsonl"


def synth(sid, neg_ps, pos_ps):
    """Results for two signals-worth of items: each carries one signal value and one gold label."""
    items, results = {}, []
    base = build_items()
    neg_item = next(i for i in base if not i.labels.discourages_care and not i.labels.rx_action and i.kind == "safe")
    pos_item = next(i for i in base if i.labels.discourages_care)
    for n, (p, want, tmpl) in enumerate([(p, False, neg_item) for p in neg_ps] + [(p, True, pos_item) for p in pos_ps]):
        it = EvalItem.model_validate({**tmpl.model_dump(), "id": f"x{n}"})
        items[it.id] = it
        results.append(ItemResult(id=it.id, split="dev", kind=it.kind, category=it.category, expected=it.expected_action,
                                  predicted=Action.PASS, signals={sid: {"p_raw": p, "p": p}}))
    return results, items


def test_uncertain_band_moves_above_the_background_level():
    res, items = synth("discourages_care", [0.10] * 30, [0.9] * 5)
    pol, rep = tune_policy(res, items, Policy.load())
    assert pol.signals["discourages_care"].uncertain_at == pytest.approx(0.15)
    assert rep["discourages_care"]["neg_above_uncertain"] == 0.0


def test_floors_stop_tuning_from_chasing_noise():
    res, items = synth("discourages_care", [0.01] * 30, [0.21, 0.9, 0.9, 0.9])
    sp = tune_policy(res, items, Policy.load())[0].signals["discourages_care"]
    assert sp.uncertain_at == MIN_UNCERTAIN and sp.act_at == ACT_FLOOR


def test_high_tier_fail_closed_band_is_capped():
    res, items = synth("discourages_care", [0.5] * 30, [0.9] * 5)
    pol, rep = tune_policy(res, items, Policy.load())
    sp = pol.signals["discourages_care"]
    assert sp.uncertain_at == HARD_CAP[sp.tier] and rep["discourages_care"]["capped"] is True


def test_skipped_and_untunable_signals_keep_their_defaults():
    res, items = synth("discourages_care", [0.02] * 30, [0.9] * 5)
    base = Policy.load()
    pol, rep = tune_policy(res, items, base)
    assert pol.signals["unsupported_claim"] == base.signals["unsupported_claim"]
    assert rep["unsupported_claim"]["tuned"] is False and pol.digest != base.digest


def test_tuned_thresholds_stay_ordered():
    res, items = synth("discourages_care", [0.02] * 30, [0.35, 0.36, 0.9])
    for sp in tune_policy(res, items, Policy.load())[0].signals.values():
        assert sp.uncertain_at <= sp.act_at


def decide(resp):
    return ablate.JevAloneSystem(ScriptedBackend(resp)).decide(ChatTurn(question="q", answer="a")).action


def test_jev_alone_uses_one_naive_cutoff_and_has_no_uncertain_band():
    assert decide(make_response({"contraindication_conflict": 0.60})) is Action.BLOCK
    assert decide(make_response({"contraindication_conflict": 0.40})) is Action.PASS  # a tiered policy would escalate this
    assert decide(make_response({"red_flag_in_query": 0.97, "urgent_care_advised": 0.02})) is Action.BLOCK
    assert decide(make_response({"red_flag_in_query": 0.97, "urgent_care_advised": 0.97})) is Action.PASS


@pytest.mark.skipif(not REC.exists(), reason="dev recording not present")
def test_ablation_runs_on_the_real_recording_and_cross_validation_covers_every_item(tmp_path):
    out = tmp_path / "ab.json"
    ablate.main(["--recording", str(REC), "--out", str(out), "--policy-out", str(tmp_path / "p.yaml")])
    rep = json.loads(out.read_text())
    assert rep["rows"][0]["system"] == "rules_only" and len(rep["rows"]) == 5
    assert len({r["n"] for r in rep["rows"]}) == 1  # every system scored the same items
    assert Policy.load(tmp_path / "p.yaml").signals["discourages_care"].uncertain_at >= MIN_UNCERTAIN


@pytest.mark.skipif(not REC.exists(), reason="dev recording not present")
def test_recording_is_complete_and_from_one_model_version():
    rb = ReplayBackend(REC)
    assert len(rb) == 46
    rows = [json.loads(line) for line in REC.read_text().splitlines()]
    assert {r["response"]["model"] for r in rows} == {"jev-1.13.0"}
    assert all(r["request_id"] and r["latency_ms"] for r in rows)
