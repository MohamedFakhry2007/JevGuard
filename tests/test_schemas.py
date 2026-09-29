import pytest
from pydantic import ValidationError

from jevguard.schemas import (
    Action,
    ChatTurn,
    choice_confidence,
    input_cost_usd,
    parse_response,
    worst,
)

# Verbatim response body from the Jev Quick Start documentation.
QUICKSTART = {
    "model": "jev-1.13.0",
    "answers": {
        "department": {"type": "choice", "choice": "technical", "confidence": 0.78,
                       "probabilities": {"technical": 0.85, "sales": 0.0, "billing": 0.15}},
        "frustration": {"type": "score", "score": 1.0, "confidence": 1.0,
                        "legend": {"0": "Calm, just stating facts", "1": "Frustrated but civil",
                                   "2": "Very angry, strong language"},
                        "probabilities": {"0": 0.0, "1": 1.0, "2": 0.0}},
        "is_urgent": {"type": "noul", "noul": 1.0},
    },
    "usage": {"input_tokens": 392, "output_tokens": 65},
}


def test_parses_documented_response():
    r = parse_response(QUICKSTART, request_id="req-1", latency_ms=290.0)
    assert r.model == "jev-1.13.0"
    assert r.answers["is_urgent"].noul == 1.0
    assert r.answers["department"].choice == "technical"
    assert r.usage.input_tokens == 392 and r.request_id == "req-1"


def test_noul_answer_has_no_confidence_field():
    r = parse_response(QUICKSTART)
    assert not hasattr(r.answers["is_urgent"], "confidence")


def test_choice_confidence_matches_documented_formula():
    # docs example: probabilities 0.85 / 0.0 / 0.15 reported as confidence 0.78
    assert choice_confidence([0.85, 0.0, 0.15]) == pytest.approx(0.775)
    assert choice_confidence([1 / 3] * 3) == pytest.approx(0.0)
    assert choice_confidence([1.0]) == 1.0


def test_rejects_unknown_answer_type_and_out_of_range():
    with pytest.raises(ValidationError):
        parse_response({"model": "m", "answers": {"x": {"type": "weird"}}})
    with pytest.raises(ValidationError):
        parse_response({"model": "m", "answers": {"x": {"type": "noul", "noul": 1.5}}})


def test_action_severity_order_and_worst():
    order = [Action.PASS, Action.FLAG, Action.CORRECT, Action.BLOCK, Action.ESCALATE]
    assert sorted(order, key=lambda a: -a.severity) == order[::-1]
    assert worst([Action.FLAG, Action.BLOCK, Action.CORRECT]) is Action.BLOCK
    assert worst([]) is Action.PASS


def test_state_labels_fields_and_marks_missing_context():
    s = ChatTurn(question="q", answer="a").to_state()
    assert s["patient_context"] == "none provided" and s["retrieved_sources"] == "none provided"
    assert list(s) == ["user_question", "patient_context", "retrieved_sources", "chatbot_answer"]


def test_turn_id_is_stable():
    assert ChatTurn(question="q", answer="a").turn_id == ChatTurn(question="q", answer="a").turn_id


def test_cost_uses_input_tokens_only():
    assert input_cost_usd(1_000_000_000) == pytest.approx(42.0)
    assert input_cost_usd(1784) == pytest.approx(7.5e-5, rel=0.01)
