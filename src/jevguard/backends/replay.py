"""Replay and record real Jev responses so results reproduce without an API key."""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any

from jevguard.backends.base import JevBackend, request_key
from jevguard.schemas import JevResponse, parse_response


class ReplayMiss(Exception):
    """No recording for this request. Deliberately NOT a BackendError: a missing
    recording must stop an evaluation, not be scored as a fail-closed escalation."""


class ReplayBackend:
    name = "replay"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._rows: dict[str, dict[str, Any]] = {}
        for line in self.path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                self._rows[row["key"]] = row

    def __len__(self) -> int:
        return len(self._rows)

    def has(self, state: Any, questions: dict[str, dict[str, Any]]) -> bool:
        return request_key(state, questions) in self._rows

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> JevResponse:
        key = request_key(state, questions)
        row = self._rows.get(key)
        if row is None:
            raise ReplayMiss(f"no recording for request {key[:12]} in {self.path}")
        return parse_response(
            row["response"],
            request_id=row.get("request_id"),
            latency_ms=row.get("latency_ms"),
            endpoint=row.get("endpoint", "typesafe"),
        )


class RecordingBackend:
    """Wraps a live backend and appends every exchange to a JSONL recording."""

    def __init__(self, inner: JevBackend, path: str | Path):
        self.inner = inner
        self.name = f"recording({inner.name})"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> JevResponse:
        resp = self.inner.ask(state, questions)
        row = {
            "key": request_key(state, questions),
            "request": {"state": state, "questions": questions},
            "response": resp.model_dump(mode="json", exclude={"request_id", "latency_ms", "endpoint"}),
            "request_id": resp.request_id,
            "latency_ms": resp.latency_ms,
            "endpoint": resp.endpoint,
            "recorded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with self.path.open("a") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        return resp


class RecordReplayBackend:
    """Replay what exists, call `inner` for the rest and record it. Resumable and pays once."""

    def __init__(self, path: str | Path, inner: JevBackend):
        self.path = Path(path)
        self.inner = inner
        self.name = f"record_replay({inner.name})"
        self._replay = ReplayBackend(self.path) if self.path.exists() else None
        self._rec = RecordingBackend(inner, self.path)
        self.live_calls = 0

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> JevResponse:
        if self._replay is not None:
            try:
                return self._replay.ask(state, questions)
            except ReplayMiss:
                pass
        self.live_calls += 1
        resp = self._rec.ask(state, questions)
        self._replay = ReplayBackend(self.path)
        return resp
