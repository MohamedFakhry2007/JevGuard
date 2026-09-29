"""Turn a Jev response into calibrated, banded risk signals."""
from __future__ import annotations

from pydantic import BaseModel

from jevguard.calibration import Calibrator
from jevguard.policy import Band, Policy
from jevguard.questions import COMPOSITE_RED_FLAG, SIGNALS, SignalDef
from jevguard.schemas import ChoiceAnswer, JevResponse, NoulAnswer, ScoreAnswer, Tier


class IncompleteResponse(Exception):
    """The response lacks an answer we need, or has the wrong type. The guard fails closed."""


class SignalRecord(BaseModel):
    id: str
    tier: Tier
    p_raw: float
    p: float
    band: Band
    is_risk: bool
    description: str = ""


def _raw(defn: SignalDef, resp: JevResponse) -> float:
    ans = resp.answers.get(defn.question_id)
    if ans is None:
        raise IncompleteResponse(f"missing answer for {defn.question_id}")
    if defn.kind == "noul" and isinstance(ans, NoulAnswer):
        return ans.noul
    if defn.kind == "choice_option" and isinstance(ans, ChoiceAnswer):
        if defn.arg not in ans.probabilities:
            raise IncompleteResponse(f"{defn.question_id} lacks option {defn.arg}")
        return ans.probabilities[str(defn.arg)]
    if defn.kind == "score_at_least" and isinstance(ans, ScoreAnswer):
        return sum(v for k, v in ans.probabilities.items() if int(k) >= int(defn.arg))
    raise IncompleteResponse(f"unexpected answer type for {defn.question_id}")


def compute_signals(
    resp: JevResponse, policy: Policy, calibrators: dict[str, Calibrator] | None = None
) -> dict[str, SignalRecord]:
    calibrators = calibrators or {}
    out: dict[str, SignalRecord] = {}
    for defn in SIGNALS:
        raw = _raw(defn, resp)
        p = calibrators.get(defn.id, Calibrator()).apply(raw)
        out[defn.id] = SignalRecord(
            id=defn.id, tier=defn.tier, p_raw=raw, p=p, band=policy.signals[defn.id].band(p),
            is_risk=defn.is_risk, description=defn.description,
        )
    red, urgent = out["red_flag_in_query"], out["urgent_care_advised"]
    p = red.p * (1.0 - urgent.p)
    raw = red.p_raw * (1.0 - urgent.p_raw)
    sp = policy.signals[COMPOSITE_RED_FLAG]
    out[COMPOSITE_RED_FLAG] = SignalRecord(
        id=COMPOSITE_RED_FLAG, tier=sp.tier, p_raw=raw, p=p, band=sp.band(p), is_risk=True,
        description="Red flag in question and no urgent-care advice in answer",
    )
    return out
