"""Evaluation item schema. Labels are ground truth about the ANSWER, independent of any model."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from jevguard.schemas import Action, ChatTurn

Scope = Literal[
    "general_education", "symptom_triage", "medication_question",
    "diagnosis_request", "emergency", "non_medical",
]


class Labels(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dose_stated: bool = False
    rx_action: bool = False
    contraindication_conflict: bool = False
    red_flag_in_query: bool = False  # the user's message describes emergency-level symptoms
    urgent_care_advised: bool = False
    discourages_care: bool = False
    unsupported_claim: bool = False
    certainty_definitive: bool = False
    request_scope: Scope = "general_education"


class EvalItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    scenario_id: str  # split unit: everything derived from one scenario shares a split
    split: Literal["dev", "test"]
    kind: Literal["safe", "hard_negative", "unsafe"]
    category: str  # failure mode for unsafe items
    origin: Literal["mutation", "hand_written", "safe_base"]
    tags: list[str] = Field(default_factory=list)
    synthetic: bool = True
    review_status: Literal["draft_unreviewed", "reviewed"] = "draft_unreviewed"
    source_ref: str | None = None  # e.g. a HeartSafe golden question id used only as a prompt seed
    question: str
    context: str = ""
    sources: list[str] = Field(default_factory=list)
    answer: str
    labels: Labels
    expected_action: Action
    notes: str = ""

    def to_turn(self) -> ChatTurn:
        return ChatTurn(id=self.id, question=self.question, answer=self.answer,
                        context=self.context, sources=self.sources)
