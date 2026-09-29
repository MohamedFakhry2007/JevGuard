"""Systems under evaluation share one interface so they are scored identically."""
from __future__ import annotations

import time
from typing import Protocol

from pydantic import BaseModel, Field

from jevguard.deterministic import rules_only_decide
from jevguard.engine import JevGuard
from jevguard.schemas import Action, ChatTurn


class SystemOutput(BaseModel):
    action: Action
    latency_ms: float = 0.0
    total_ms: float = 0.0
    cost_usd: float = 0.0
    input_tokens: int = 0
    failure: str | None = None
    reasons: list[str] = Field(default_factory=list)
    signals: dict[str, dict[str, float]] = Field(default_factory=dict)


class System(Protocol):
    name: str

    def decide(self, turn: ChatTurn) -> SystemOutput: ...


class RulesOnlySystem:
    """Regex moderation with no model. The floor that Jev has to beat."""

    name = "rules_only"

    def decide(self, turn: ChatTurn) -> SystemOutput:
        t0 = time.perf_counter()
        action, reasons = rules_only_decide(turn)
        return SystemOutput(action=action, reasons=reasons, total_ms=(time.perf_counter() - t0) * 1000)


class JevRulesSystem:
    name = "jev_rules"

    def __init__(self, guard: JevGuard):
        self.guard = guard

    def decide(self, turn: ChatTurn) -> SystemOutput:
        d = self.guard.check(turn)
        return SystemOutput(
            action=d.action, latency_ms=d.jev_latency_ms or 0.0, total_ms=d.total_ms, cost_usd=d.cost_usd,
            input_tokens=d.input_tokens, failure=d.failure, reasons=d.reasons,
            signals={k: {"p_raw": s.p_raw, "p": s.p} for k, s in d.signals.items()},
        )
