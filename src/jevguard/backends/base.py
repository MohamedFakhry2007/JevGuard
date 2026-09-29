"""Backend protocol. Everything downstream depends only on this."""
from __future__ import annotations

import hashlib
from typing import Any, Protocol

from jevguard.schemas import JevResponse, canonical_json


class BackendError(Exception):
    """The backend failed (timeout, HTTP error, bad payload). The guard fails closed."""


class JevBackend(Protocol):
    name: str

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> JevResponse: ...


def request_key(state: Any, questions: dict[str, dict[str, Any]]) -> str:
    """Stable hash of a request. Used to index recordings."""
    return hashlib.sha256(canonical_json({"state": state, "questions": questions}).encode()).hexdigest()
