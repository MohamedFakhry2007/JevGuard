"""Pick thresholds on the DEV split with a fixed, documented procedure.

Per signal, using Jev's raw probabilities and the gold labels:
  uncertain_at: the smallest 0.05-grid value at which at most MAX_NEG_RATE of the gold
                negatives are at or above it. This keeps the fail-closed band above Jev's
                normal background level instead of below it. High tier is capped at HARD_CAP
                so tuning can never push the fail-closed band far up.
  act_at:       0.5 by default. Lowered to the largest grid value that still catches at least
                TARGET_RECALL of the gold positives, when there are at least MIN_POS positives,
                but never below ACT_FLOOR. uncertain_at is never below MIN_UNCERTAIN.
Signals whose label definition is under review, or that feed only a composite, are skipped.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from jevguard.evalset.metrics import ItemResult, signal_truth
from jevguard.evalset.schema import EvalItem
from jevguard.policy import Policy, SignalPolicy
from jevguard.schemas import Tier

GRID = [round(0.05 * i, 2) for i in range(1, 20)]
MAX_NEG_RATE = {Tier.HIGH: 0.05, Tier.MEDIUM: 0.10, Tier.LOW: 0.10}
TARGET_RECALL = {Tier.HIGH: 0.95, Tier.MEDIUM: 0.90, Tier.LOW: 0.90}
HARD_CAP = {Tier.HIGH: 0.30, Tier.MEDIUM: 0.50, Tier.LOW: 0.60}
MIN_POS = 3
MIN_UNCERTAIN = 0.10  # Jev's background level is 0.01 to 0.05, so a band below 0.10 is inside the noise
ACT_FLOOR = 0.30  # never act on a probability lower than this, however few positives sit there
SKIP = {"unsupported_claim", "red_flag_in_query", "urgent_care_advised", "scope_diagnosis_request", "self_harm_in_query"}


def _share(values: list[float], t: float) -> float:
    return sum(v >= t for v in values) / len(values) if values else 0.0


def tune_policy(results: list[ItemResult], items: dict[str, EvalItem], base: Policy) -> tuple[Policy, dict[str, Any]]:
    pos: dict[str, list[float]] = defaultdict(list)
    neg: dict[str, list[float]] = defaultdict(list)
    for r in results:
        truth = signal_truth(items[r.id].labels)
        for sid, vals in r.signals.items():
            (pos if truth[sid] else neg)[sid].append(vals["p_raw"])

    tuned = base.model_copy(deep=True)
    tuned.version = f"tuned-on-dev-n{len(results)}"
    report: dict[str, Any] = {}
    for sid, sp in base.signals.items():
        if sid in SKIP or not neg[sid]:
            report[sid] = {"tuned": False, "reason": "skipped"}
            continue
        u = next((g for g in GRID if g >= MIN_UNCERTAIN and _share(neg[sid], g) <= MAX_NEG_RATE[sp.tier]), 0.95)
        capped = u > HARD_CAP[sp.tier]
        u = min(u, HARD_CAP[sp.tier])
        a = sp.act_at
        act_tuned = False
        if len(pos[sid]) >= MIN_POS:
            ok = [g for g in GRID if ACT_FLOOR <= g <= sp.act_at and _share(pos[sid], g) >= TARGET_RECALL[sp.tier]]
            a, act_tuned = (max(ok) if ok else ACT_FLOOR), True
        u = min(u, a)
        tuned.signals[sid] = SignalPolicy(tier=sp.tier, uncertain_at=u, act_at=a)
        report[sid] = {
            "tuned": True, "uncertain_at": u, "act_at": a, "act_at_tuned": act_tuned, "capped": capped,
            "n_neg": len(neg[sid]), "n_pos": len(pos[sid]),
            "neg_above_uncertain": round(_share(neg[sid], u), 3),
            "pos_above_act": round(_share(pos[sid], a), 3) if pos[sid] else None,
        }
    return tuned, report
