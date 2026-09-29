"""Helpers for building scripted Jev responses in tests and demos."""
from __future__ import annotations

from typing import Any

from jevguard.questions import QUESTIONS
from jevguard.schemas import JevResponse, choice_confidence, parse_response, score_confidence_approx

SCOPES = list(QUESTIONS["request_scope"]["criteria"])
CLEAR_NOULS = {
    "dose_stated": 0.02, "rx_action": 0.02, "contraindication_conflict": 0.01,
    "red_flag_in_query": 0.02, "self_harm_in_query": 0.01, "urgent_care_advised": 0.05, "discourages_care": 0.01,
    "unsupported_claim": 0.05,
}


def make_response(nouls: dict[str, float] | None = None, scope: str = "general_education",
                  certainty_level: int = 0, model: str = "scripted") -> JevResponse:
    """A complete, all-clear response with overrides. `nouls` overrides individual probabilities."""
    n = {**CLEAR_NOULS, **(nouls or {})}
    answers: dict[str, Any] = {k: {"type": "noul", "noul": v} for k, v in n.items()}
    sp = {o: (0.9 if o == scope else 0.1 / (len(SCOPES) - 1)) for o in SCOPES}
    answers["request_scope"] = {"type": "choice", "choice": scope,
                                "confidence": choice_confidence(sp.values()), "probabilities": sp}
    cp = {str(i): (0.9 if i == certainty_level else 0.1 / 3) for i in range(4)}
    answers["diagnostic_certainty"] = {
        "type": "score", "score": sum(int(k) * v for k, v in cp.items()),
        "confidence": score_confidence_approx(cp.values()), "probabilities": cp,
    }
    return parse_response({"model": model, "answers": answers, "usage": {"input_tokens": 500, "output_tokens": 60}},
                          latency_ms=250.0, endpoint="scripted")


class ScriptedBackend:
    name = "scripted"

    def __init__(self, response: JevResponse | Exception):
        self.response = response
        self.calls = 0

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> JevResponse:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response
