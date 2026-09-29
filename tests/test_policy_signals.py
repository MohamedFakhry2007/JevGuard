import pytest

from jevguard.calibration import Calibrator
from jevguard.policy import Policy, SignalPolicy
from jevguard.questions import SIGNALS
from jevguard.schemas import Tier
from jevguard.signals import IncompleteResponse, compute_signals
from jevguard.testing import make_response


def test_default_policy_covers_every_signal_and_composite():
    pol = Policy.load()
    for s in SIGNALS:
        assert s.id in pol.signals and pol.signals[s.id].tier == s.tier
    assert "red_flag_no_urgent" in pol.signals


def test_high_tier_is_stricter_than_low_tier():
    pol = Policy.load()
    assert pol.signals["contraindication_conflict"].act_at < pol.signals["certainty_definitive"].act_at


def test_band_edges():
    sp = SignalPolicy(tier=Tier.HIGH, uncertain_at=0.1, act_at=0.5)
    assert [sp.band(p) for p in (0.09, 0.1, 0.49, 0.5)] == ["clear", "uncertain", "uncertain", "fired"]


def test_policy_rejects_misordered_thresholds():
    with pytest.raises(ValueError):
        SignalPolicy(tier=Tier.HIGH, uncertain_at=0.6, act_at=0.5)


def test_policy_digest_changes_with_thresholds():
    a = Policy.load()
    b = Policy.load()
    b.signals["dose_stated"].act_at = 0.9
    assert a.digest != b.digest


def test_composite_red_flag_without_urgent_care():
    pol = Policy.load()
    s = compute_signals(make_response({"red_flag_in_query": 0.95, "urgent_care_advised": 0.05}), pol)
    assert s["red_flag_no_urgent"].p == pytest.approx(0.95 * 0.95)
    assert s["red_flag_no_urgent"].band == "fired"
    ok = compute_signals(make_response({"red_flag_in_query": 0.95, "urgent_care_advised": 0.97}), pol)
    assert ok["red_flag_no_urgent"].band == "clear"


def test_derived_signals_from_choice_and_score():
    pol = Policy.load()
    s = compute_signals(make_response(scope="emergency", certainty_level=3), pol)
    assert s["scope_emergency"].band == "fired" and s["certainty_definitive"].band == "fired"


def test_calibration_is_applied_before_banding():
    pol = Policy.load()
    resp = make_response({"dose_stated": 0.95})
    raw = compute_signals(resp, pol)["dose_stated"]
    cal = compute_signals(resp, pol, {"dose_stated": Calibrator(temperature=4.0)})["dose_stated"]
    assert raw.p_raw == cal.p_raw == 0.95 and cal.p < raw.p


def test_missing_answer_is_incomplete():
    resp = make_response()
    del resp.answers["rx_action"]
    with pytest.raises(IncompleteResponse):
        compute_signals(resp, Policy.load())


def test_emergency_scope_alone_feeds_the_composite():
    pol = Policy.load()
    s = compute_signals(make_response(scope="emergency"), pol)
    assert s["red_flag_in_query"].band == "clear" and s["red_flag_no_urgent"].band == "fired"
