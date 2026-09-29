"""Logic behind the demo app, kept out of the Streamlit file so it can be tested without a browser."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from jevguard.backends import ReplayBackend, ReplayMiss, SimulatedBackend
from jevguard.deterministic import rules_only_decide
from jevguard.engine import Decision, JevGuard
from jevguard.evalset.build import load
from jevguard.evalset.run import with_recordings
from jevguard.evalset.schema import EvalItem
from jevguard.policy import Policy
from jevguard.schemas import Action, ChatTurn

REPO = Path(__file__).resolve().parents[2]
RECORDING = REPO / "eval" / "recordings" / "dev.jsonl"
ITEMS = REPO / "eval" / "data" / "items.jsonl"
POLICIES: dict[str, Path | None] = {
    "Starting thresholds (a first guess)": None,
    "Tuned on the dev split (candidate)": REPO / "eval" / "policies" / "v0.2_dev_candidate.yaml",
}
MODES = {
    "recorded": "Recorded real Jev answers",
    "simulated": "Simulated (NOT Jev), any text",
    "live": "Live Jev",
}
MEANING = {
    Action.PASS: "The answer goes out unchanged.",
    Action.FLAG: "The answer goes out. It is logged for a human to look at.",
    Action.CORRECT: "A fixed safety sentence is added to the answer.",
    Action.BLOCK: "The answer is replaced with a safe fallback message.",
    Action.ESCALATE: "The answer is held for a clinician.",
}


class NoRecording(Exception):
    """Recorded mode was asked about text that was never sent to Jev."""


@dataclass
class CheckRow:
    id: str
    label: str
    tier: str
    p_raw: float
    p: float
    band: str
    is_risk: bool


@dataclass
class View:
    decision: Decision
    rows: list[CheckRow]
    keyword_action: Action
    keyword_reasons: list[str]
    mode: str
    warning: str | None


def plain_reasons(d: Decision) -> list[str]:
    """Replace internal check ids in the rule messages with their plain descriptions."""
    out = []
    for r in d.reasons:
        for sid, sig in d.signals.items():
            r = r.replace(sid.replace("_", " "), (sig.description or sid).lower()).replace(sid, (sig.description or sid).lower())
        out.append(r)
    return out


def live_available() -> bool:
    return bool(os.environ.get("TYPESAFE_API_KEY"))


def recorded_examples() -> list[EvalItem]:
    """Dev answers that have a real Jev recording. Test-split answers are never offered."""
    if not RECORDING.exists():
        return []
    dev = [i for i in load(ITEMS) if i.split == "dev"]
    have, _ = with_recordings(dev, [str(RECORDING)])
    return have


def load_policy(label: str) -> Policy:
    path = POLICIES[label]
    return Policy.load(path) if path else Policy.load()


def _backend(mode: str):
    if mode == "recorded":
        return ReplayBackend(RECORDING)
    if mode == "simulated":
        return SimulatedBackend()
    if mode == "live" and live_available():
        from jevguard.backends.live import LiveBackend
        return LiveBackend()
    raise ValueError(f"mode {mode!r} is not available here")


def run(turn: ChatTurn, mode: str, policy_label: str) -> View:
    guard = JevGuard(_backend(mode), load_policy(policy_label))
    try:
        d = guard.check(turn)
    except ReplayMiss as exc:
        raise NoRecording(str(exc)) from exc
    order = {"high": 0, "medium": 1, "low": 2}
    rows = sorted(
        (CheckRow(s.id, s.description or s.id, s.tier.value, s.p_raw, s.p, s.band, s.is_risk) for s in d.signals.values()),
        key=lambda r: ({"fired": 0, "uncertain": 1, "clear": 2}[r.band], order[r.tier], -r.p),
    )
    kw_action, kw_reasons = rules_only_decide(turn)
    warning = "SIMULATED. These probabilities come from a keyword stand-in, not from Jev." if mode == "simulated" else None
    return View(d, rows, kw_action, kw_reasons, mode, warning)
