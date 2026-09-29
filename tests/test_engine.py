from jevguard import Action, ChatTurn, JevGuard, templates
from jevguard.audit import AuditLog
from jevguard.backends import BackendError
from jevguard.testing import ScriptedBackend, make_response

CITED = " According to guidelines [1]."


def guard(resp):
    return JevGuard(ScriptedBackend(resp))


def turn(answer="Rest and fluids." + CITED, question="I have a cold", **kw):
    return ChatTurn(question=question, answer=answer, **kw)


def test_clean_answer_passes_and_is_promoted():
    d = guard(make_response()).check(turn())
    assert d.action is Action.PASS and d.final_text == d.original_text
    assert [f.rule for f in d.fired] == ["jevguard.promote_verified"]


def test_contraindication_is_blocked_with_fallback_text():
    d = guard(make_response({"contraindication_conflict": 0.9})).check(turn())
    assert d.action is Action.BLOCK and d.final_text == templates.BLOCK_FALLBACK
    assert any("contraindication" in r for r in d.reasons)


def test_uncertain_high_tier_fails_closed_to_escalate():
    d = guard(make_response({"contraindication_conflict": 0.2})).check(turn())
    assert d.action is Action.ESCALATE and d.final_text == templates.ESCALATE_HOLD


def test_uncertain_medium_tier_does_not_escalate():
    d = guard(make_response({"dose_stated": 0.4})).check(turn())
    assert d.action is Action.PASS


def test_red_flag_without_urgent_advice_is_corrected_with_template():
    d = guard(make_response({"red_flag_in_query": 0.97, "urgent_care_advised": 0.03})).check(
        turn("Rest at home.", "I have crushing chest pain"))
    assert d.action is Action.CORRECT
    assert d.final_text.startswith("Rest at home.") and d.final_text.endswith(templates.URGENT_CARE)


def test_red_flag_with_urgent_advice_passes():
    d = guard(make_response({"red_flag_in_query": 0.97, "urgent_care_advised": 0.97}, scope="symptom_triage")).check(
        turn("Call 911 now." + CITED, "I have crushing chest pain"))
    assert d.action is Action.PASS


def test_most_severe_finding_wins_over_correct():
    resp = make_response({"red_flag_in_query": 0.97, "urgent_care_advised": 0.03, "contraindication_conflict": 0.9})
    d = guard(resp).check(turn())
    assert d.action is Action.BLOCK
    assert {"jevguard.red_flag_no_urgent", "jevguard.contraindication_conflict"} <= {f.rule for f in d.fired}


def test_dose_plus_rx_directive_blocks_dose_alone_only_flags():
    assert guard(make_response({"dose_stated": 0.95, "rx_action": 0.95})).check(turn()).action is Action.BLOCK
    assert guard(make_response({"dose_stated": 0.95})).check(turn()).action is Action.FLAG
    assert guard(make_response({"rx_action": 0.95})).check(turn()).action is Action.ESCALATE


def test_emergency_scope_without_urgent_advice_is_corrected():
    d = guard(make_response(scope="emergency")).check(turn())
    assert d.action is Action.CORRECT and d.final_text.endswith(templates.URGENT_CARE)


def test_emergency_scope_with_urgent_advice_is_not_escalated():
    d = guard(make_response({"urgent_care_advised": 0.97}, scope="emergency")).check(turn("Call 911 now." + CITED))
    assert d.action is Action.PASS


def test_diagnosis_request_is_a_routing_signal_not_an_action():
    d = guard(make_response(scope="diagnosis_request")).check(turn())
    assert d.action is Action.PASS and d.signals["scope_diagnosis_request"].band == "fired"


def test_definitive_certainty_appends_hedge():
    d = guard(make_response(certainty_level=3)).check(turn())
    assert d.action is Action.CORRECT and d.final_text.endswith(templates.HEDGE)


def test_regex_dose_that_jev_missed_is_flagged():
    d = guard(make_response()).check(turn("Take 400 mg now." + CITED))
    assert d.action is Action.FLAG and any("Jev saw no dose" in r for r in d.reasons)


def test_backend_failure_fails_closed():
    d = guard(BackendError("timeout")).check(turn())
    assert d.action is Action.ESCALATE and d.failure == "timeout" and d.final_text == templates.ESCALATE_HOLD


def test_incomplete_response_fails_closed():
    resp = make_response()
    del resp.answers["dose_stated"]
    d = guard(resp).check(turn())
    assert d.action is Action.ESCALATE and "incomplete" in d.failure


def test_every_decision_records_versions_and_cost():
    d = guard(make_response()).check(turn())
    assert set(d.versions) == {"questions", "policy", "backend", "jev_model"}
    assert d.input_tokens == 500 and d.cost_usd > 0 and d.jev_latency_ms == 250.0


def test_engines_do_not_share_audit_state_between_calls():
    g = guard(make_response({"contraindication_conflict": 0.9}))
    first, second = g.check(turn()), g.check(turn())
    assert len(first.fired) == len(second.fired)


def test_audit_log_roundtrip(tmp_path):
    log = AuditLog(tmp_path / "a" / "audit.jsonl")
    g = guard(make_response({"contraindication_conflict": 0.9}))
    d = g.check(turn())
    log.write(d)
    log.write(g.check(turn()))
    back = list(log.read())
    assert len(back) == 2 and back[0].action is Action.BLOCK and back[0].signals.keys() == d.signals.keys()


def test_escalate_outranks_block_when_both_fire():
    resp = make_response({"contraindication_conflict": 0.9, "rx_action": 0.95})
    d = guard(resp).check(turn())
    assert d.action is Action.ESCALATE and d.final_text == templates.ESCALATE_HOLD
    assert {"jevguard.contraindication_conflict", "jevguard.dose_and_rx"} <= {f.rule for f in d.fired}


def test_self_harm_message_with_no_crisis_response_goes_to_a_person():
    d = guard(make_response({"self_harm_in_query": 0.96, "urgent_care_advised": 0.03, "red_flag_in_query": 0.9}, scope="emergency")).check(
        turn("Everyone has bad days, get some sleep.", "I feel hopeless and want to disappear."))
    assert d.action is Action.ESCALATE and d.final_text == templates.ESCALATE_HOLD
    assert "jevguard.self_harm_no_urgent" in {f.rule for f in d.fired}


def test_self_harm_message_with_a_crisis_response_is_not_held():
    d = guard(make_response({"self_harm_in_query": 0.96, "urgent_care_advised": 0.97, "red_flag_in_query": 0.9}, scope="emergency")).check(
        turn("Please call a crisis line or emergency services now." + CITED, "I feel hopeless and want to disappear."))
    assert d.action is Action.PASS


def test_uncertain_self_harm_fails_closed():
    d = guard(make_response({"self_harm_in_query": 0.30, "urgent_care_advised": 0.03})).check(turn())
    assert d.action is Action.ESCALATE and "uncertain" in " ".join(d.reasons)


def test_wait_and_see_for_a_non_emergency_is_left_alone():
    d = guard(make_response(scope="symptom_triage")).check(
        turn("It is reasonable to wait a few days and see how it goes." + CITED, "I twisted my ankle. I can walk on it."))
    assert d.action is Action.PASS and d.final_text == d.original_text


def test_unexpected_error_in_signal_computation_fails_closed(monkeypatch):
    import jevguard.engine as eng

    def boom(*a, **k):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(eng, "compute_signals", boom)
    d = guard(make_response()).check(turn())
    assert d.action is Action.ESCALATE and d.failure and "RuntimeError" in d.failure


def test_malformed_probabilities_are_rejected():
    import pytest
    from pydantic import ValidationError

    from jevguard.schemas import ChoiceAnswer, ScoreAnswer
    for bad in ({"a": float("nan")}, {"a": 1.5}, {"a": -0.1}):
        with pytest.raises(ValidationError):
            ChoiceAnswer(type="choice", choice="a", confidence=0.5, probabilities=bad)
    with pytest.raises(ValidationError):
        ScoreAnswer(type="score", score=1.0, confidence=0.5, probabilities={"high": 0.5})
