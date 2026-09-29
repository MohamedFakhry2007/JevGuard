"""JevGuard: ask Jev typed questions, then let deterministic VLM-Guard rules decide."""
from __future__ import annotations

import datetime
import time
import warnings
from typing import Any

from pydantic import BaseModel, Field
from vlm_guard import Analysis, GuardrailEngine

from jevguard import templates
from jevguard.backends.base import BackendError, JevBackend
from jevguard.calibration import Calibrator
from jevguard.deterministic import det_signals
from jevguard.policy import Policy
from jevguard.questions import QUESTION_SET_VERSION, build_request
from jevguard.rules import default_rules
from jevguard.schemas import Action, ChatTurn, input_cost_usd
from jevguard.signals import IncompleteResponse, SignalRecord, compute_signals


class FiredRule(BaseModel):
    rule: str
    action: str
    message: str


class Decision(BaseModel):
    turn_id: str
    action: Action
    original_text: str
    final_text: str
    reasons: list[str] = Field(default_factory=list)
    signals: dict[str, SignalRecord] = Field(default_factory=dict)
    fired: list[FiredRule] = Field(default_factory=list)
    failure: str | None = None  # set when the guard failed closed
    jev_model: str | None = None
    request_id: str | None = None
    endpoint: str | None = None
    jev_latency_ms: float | None = None
    total_ms: float = 0.0
    input_tokens: int = 0
    cost_usd: float = 0.0
    versions: dict[str, str] = Field(default_factory=dict)
    created_at: str = ""


class JevGuard:
    def __init__(
        self,
        backend: JevBackend,
        policy: Policy | None = None,
        calibrators: dict[str, Calibrator] | None = None,
    ):
        self.backend = backend
        if policy is None:
            warnings.warn("No policy given: using the provisional starting thresholds, which were not validated. "
                          "Pass Policy.load('eval/policies/FROZEN_v0.2.yaml') for the thresholds scored in the evaluation.",
                          UserWarning, stacklevel=2)
            policy = Policy.load()
        self.policy = policy
        self.calibrators = calibrators or {}

    def _versions(self, jev_model: str | None) -> dict[str, str]:
        return {"questions": QUESTION_SET_VERSION, "policy": f"{self.policy.version}:{self.policy.digest}",
                "backend": self.backend.name, "jev_model": jev_model or "none"}

    def _fail_closed(self, turn: ChatTurn, why: str, t0: float) -> Decision:
        return Decision(
            turn_id=turn.turn_id, action=Action.ESCALATE, original_text=turn.answer,
            final_text=templates.ESCALATE_HOLD, reasons=[f"fail closed: {why}"], failure=why,
            total_ms=(time.perf_counter() - t0) * 1000, versions=self._versions(None),
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    def check(self, turn: ChatTurn) -> Decision:
        t0 = time.perf_counter()
        state, questions = build_request(turn)
        try:
            resp = self.backend.ask(state, questions)
        except BackendError as exc:
            return self._fail_closed(turn, str(exc), t0)
        try:
            signals = compute_signals(resp, self.policy, self.calibrators)
        except IncompleteResponse as exc:
            return self._fail_closed(turn, f"incomplete response: {exc}", t0)
        except Exception as exc:  # noqa: BLE001 - a safety layer must never let an unexpected error pass the answer through
            return self._fail_closed(turn, f"signal computation failed: {type(exc).__name__}: {exc}", t0)

        analysis = Analysis(
            label="pass", confidence="Medium",
            evidence="; ".join(f"{s.id}={s.p:.2f}" for s in signals.values() if s.band != "clear"),
            findings=turn.question, recommendation="",
            metadata={
                "original_text": turn.answer,
                "signals": {k: v.model_dump(mode="json") for k, v in signals.items()},
                "det": det_signals(turn),
            },
        )
        engine = GuardrailEngine()  # one engine per request: its audit trail is per-instance state
        engine.register_list(default_rules())
        final, trail = engine.apply_with_audit(analysis)

        findings: list[dict[str, Any]] = final.metadata.get("findings", [])
        return Decision(
            turn_id=turn.turn_id, action=Action(final.label), original_text=turn.answer,
            final_text=final.metadata["final_text"], reasons=[f["reason"] for f in findings],
            signals=signals,
            fired=[FiredRule(rule=e.rule_name, action=e.action_type, message=e.message)
                   for e in trail.entries if e.action_type != "pass"],
            jev_model=resp.model, request_id=resp.request_id, endpoint=resp.endpoint,
            jev_latency_ms=resp.latency_ms, total_ms=(time.perf_counter() - t0) * 1000,
            input_tokens=resp.usage.input_tokens, cost_usd=input_cost_usd(resp.usage.input_tokens),
            versions=self._versions(resp.model),
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
