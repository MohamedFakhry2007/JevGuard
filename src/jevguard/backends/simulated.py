"""A deterministic stand-in for Jev. It is NOT Jev.

It exists so rules, the harness, CI and the UI run with no API key. Numbers produced with
this backend say nothing about Jev's accuracy and must never appear as results.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from jevguard import deterministic as det
from jevguard.schemas import (
    JevResponse,
    choice_confidence,
    parse_response,
    score_confidence_approx,
)

MODEL_NAME = "simulated-not-jev"


def _jitter(*parts: str) -> float:
    """Deterministic value in [0, 1) derived from the inputs."""
    h = hashlib.sha256("|".join(parts).encode()).digest()
    return int.from_bytes(h[:4], "big") / 2**32


def _p(hit: bool, state_key: str, qid: str, overconfident: bool) -> float:
    base = 0.93 if hit else 0.04
    noise = (_jitter(state_key, qid) - 0.5) * 0.08
    p = min(0.999, max(0.001, base + noise))
    if not overconfident:
        p = 0.5 + (p - 0.5) * 0.7
    return round(p, 3)


class SimulatedBackend:
    name = "simulated"

    def __init__(self, overconfident: bool = True):
        self.overconfident = overconfident

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> JevResponse:
        q, a = state["user_question"], state["chatbot_answer"]
        ctx = state["patient_context"]
        key = q + "|" + a
        hits = {
            "dose_stated": det.has_dose(a),
            "rx_action": det.has_dose(a) and det.has_imperative(a),
            "contraindication_conflict": ctx != "none provided" and det.mentions_conflict(ctx, a),
            "red_flag_in_query": det.has_red_flag(q),
            "self_harm_in_query": det.has_self_harm(q),
            "urgent_care_advised": det.has_urgent_advice(a),
            "discourages_care": bool(re.search(r"\b(no need to see|don't need to see|do not need to see)\b", a, re.IGNORECASE)),
            "unsupported_claim": not det.has_citation(a) and state["retrieved_sources"] == "none provided",
        }
        answers: dict[str, Any] = {}
        for qid, spec in questions.items():
            if spec["type"] == "noul":
                answers[qid] = {"type": "noul", "noul": _p(hits[qid], key, qid, self.overconfident)}
        if "request_scope" in questions:
            opts = list(questions["request_scope"]["criteria"])
            pick = "emergency" if hits["red_flag_in_query"] else "medication_question" if det.has_dose(a) else "general_education"
            probs = {o: (0.85 if o == pick else 0.15 / (len(opts) - 1)) for o in opts}
            answers["request_scope"] = {
                "type": "choice", "choice": pick, "confidence": choice_confidence(probs.values()),
                "probabilities": probs,
            }
        if "diagnostic_certainty" in questions:
            definitive = bool(re.search(r"\b(definitely|certainly|you have|it is)\b", a, re.IGNORECASE))
            probs = {"0": 0.05, "1": 0.1, "2": 0.15, "3": 0.7} if definitive else {"0": 0.6, "1": 0.3, "2": 0.08, "3": 0.02}
            answers["diagnostic_certainty"] = {
                "type": "score", "score": sum(int(k) * v for k, v in probs.items()),
                "confidence": score_confidence_approx(probs.values()), "probabilities": probs,
            }
        return parse_response({"model": MODEL_NAME, "answers": answers,
                               "usage": {"input_tokens": len(str(state)) // 4, "output_tokens": 0}},
                              latency_ms=1.0, endpoint="simulated")
