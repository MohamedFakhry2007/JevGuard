"""Risk-scaled thresholds: stricter (earlier to act, fail closed) for high-tier checks."""
from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, model_validator

from jevguard.schemas import Tier, canonical_json

Band = Literal["clear", "uncertain", "fired"]


class SignalPolicy(BaseModel):
    tier: Tier
    uncertain_at: float
    act_at: float

    @model_validator(mode="after")
    def _ordered(self) -> SignalPolicy:
        if not 0.0 <= self.uncertain_at <= self.act_at <= 1.0:
            raise ValueError("need 0 <= uncertain_at <= act_at <= 1")
        return self

    def band(self, p: float) -> Band:
        if p >= self.act_at:
            return "fired"
        if p >= self.uncertain_at:
            return "uncertain"
        return "clear"


class Policy(BaseModel):
    version: str
    signals: dict[str, SignalPolicy]

    @classmethod
    def load(cls, path: str | Path | None = None) -> Policy:
        if path is None:
            text = resources.files("jevguard").joinpath("thresholds.yaml").read_text()
        else:
            text = Path(path).read_text()
        return cls.model_validate(yaml.safe_load(text))

    @property
    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.model_dump(mode="json")).encode()).hexdigest()[:12]
