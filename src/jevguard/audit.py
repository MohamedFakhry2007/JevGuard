"""Append-only JSONL audit log of guard decisions."""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from jevguard.engine import Decision


class AuditLog:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, decision: Decision) -> None:
        with self.path.open("a") as fh:
            fh.write(decision.model_dump_json() + "\n")

    def read(self) -> Iterator[Decision]:
        if not self.path.exists():
            return
        for line in self.path.read_text().splitlines():
            if line.strip():
                yield Decision.model_validate(json.loads(line))
