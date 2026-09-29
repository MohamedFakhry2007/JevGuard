"""Typed models shared across JevGuard."""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Action(str, Enum):
    """Final disposition of a chatbot answer, ordered by severity."""

    PASS = "pass"
    FLAG = "flag"
    CORRECT = "correct"
    BLOCK = "block"
    ESCALATE = "escalate"

    @property
    def severity(self) -> int:
        return _SEVERITY[self.value]


_SEVERITY = {"pass": 0, "flag": 1, "correct": 2, "block": 3, "escalate": 4}


def worst(actions: Iterable[Action]) -> Action:
    return max(actions, key=lambda a: a.severity, default=Action.PASS)


class Tier(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ChatTurn(BaseModel):
    """One chatbot exchange to be checked."""

    model_config = ConfigDict(extra="forbid")

    id: str = ""
    question: str
    answer: str
    context: str = ""
    sources: list[str] = Field(default_factory=list)

    @property
    def turn_id(self) -> str:
        if self.id:
            return self.id
        return hashlib.sha1((self.question + "\x00" + self.answer).encode()).hexdigest()[:12]

    def to_state(self) -> dict[str, str]:
        """The state sent to Jev. Field names act as labels for the questions."""
        return {
            "user_question": self.question,
            "patient_context": self.context or "none provided",
            "retrieved_sources": "\n".join(self.sources) if self.sources else "none provided",
            "chatbot_answer": self.answer,
        }


# ---- Jev response models (mirror the documented System One wire format) ----


class NoulAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["noul"]
    noul: float = Field(ge=0.0, le=1.0)


def _check_probabilities(probs: dict[str, float]) -> dict[str, float]:
    """Malformed probabilities must be rejected here, or a NaN or out-of-range value could compare as 'clear'."""
    for k, v in probs.items():
        if not math.isfinite(v) or not 0.0 <= v <= 1.0:
            raise ValueError(f"probability for {k!r} must be a finite number in [0, 1], got {v!r}")
    return probs


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["choice"]
    choice: str
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float]

    _valid = field_validator("probabilities")(_check_probabilities)


class ScoreAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["score"]
    score: float
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: dict[str, float]
    legend: dict[str, str] = Field(default_factory=dict)

    _valid = field_validator("probabilities")(_check_probabilities)

    @field_validator("probabilities")
    @classmethod
    def _integer_keys(cls, v: dict[str, float]) -> dict[str, float]:
        for k in v:
            int(k)  # a non-integer score key is a malformed response
        return v


Answer = Annotated[NoulAnswer | ChoiceAnswer | ScoreAnswer, Field(discriminator="type")]


class Usage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    input_tokens: int = 0
    output_tokens: int = 0


class JevResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str
    answers: dict[str, Answer]
    usage: Usage = Field(default_factory=Usage)
    request_id: str | None = None
    latency_ms: float | None = None
    endpoint: str = "typesafe"


def parse_response(raw: dict[str, Any], **meta: Any) -> JevResponse:
    """Parse a raw System One response body, attaching request metadata."""
    return JevResponse.model_validate({**raw, **{k: v for k, v in meta.items() if v is not None}})


def choice_confidence(probs: Iterable[float]) -> float:
    """Documented Choice confidence: (K * p_max - 1) / (K - 1)."""
    p = list(probs)
    k = len(p)
    if k <= 1:
        return 1.0
    return max(0.0, min(1.0, (k * max(p) - 1) / (k - 1)))


def score_confidence_approx(probs: Iterable[float]) -> float:
    """Approximation used only by the simulated backend. TypeSafe's Score formula is
    not published in the pages we read, so this is NOT claimed to match Jev."""
    p = list(probs)
    levels = len(p)
    if levels <= 1:
        return 1.0
    mode = max(range(levels), key=lambda i: p[i])
    return 1.0 - sum(pi * abs(i - mode) for i, pi in enumerate(p)) / (levels - 1)


def input_cost_usd(input_tokens: int, usd_per_billion: float = 42.0) -> float:
    """Input-token cost. Output tokens are documented as free. Price is configurable."""
    return input_tokens * usd_per_billion / 1e9


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
