"""Record real Jev answers for a split WITHOUT scoring them.

    python -m jevguard.evalset.record --split test --allow-test --placeholder-key --recording eval/recordings/test.jsonl

Recording the test split is allowed only after the freeze, so nothing can be tuned to what Jev says there.
Nothing is scored or printed about the answers. Scoring is a separate, once-only step (evalset.final).
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from jevguard.backends import RecordReplayBackend
from jevguard.evalset.build import load
from jevguard.evalset.run import ITEMS, TEST_LOG
from jevguard.freeze import FreezeError, verify
from jevguard.questions import build_request


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "test"], required=True)
    ap.add_argument("--recording", required=True)
    ap.add_argument("--items", default=ITEMS)
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--placeholder-key", action="store_true")
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--simulated", action="store_true", help="tests only: record from the stand-in, not Jev")
    a = ap.parse_args(argv)
    if a.split == "test":
        if not a.allow_test:
            raise SystemExit("the test split is locked: pass --allow-test")
        try:
            verify()
        except FreezeError as exc:
            raise SystemExit(f"refusing to record the test split: {exc}") from exc
    if a.simulated:
        from jevguard.backends import SimulatedBackend
        inner = SimulatedBackend()
    else:
        from jevguard.backends.live import LiveBackend
        inner = LiveBackend(model=a.model, **({"api_key": "proxy-injected"} if a.placeholder_key else {}))
    items = [i for i in load(a.items) if i.split == a.split]
    backend = RecordReplayBackend(a.recording, inner)
    for it in items:
        backend.ask(*build_request(it.to_turn()))
    if a.split == "test":
        Path(TEST_LOG).parent.mkdir(parents=True, exist_ok=True)
        with open(TEST_LOG, "a") as fh:
            fh.write(json.dumps({"event": "recorded", "split": "test", "n": len(items), "live_calls": backend.live_calls,
                                 "at": datetime.datetime.now(datetime.timezone.utc).isoformat()}) + "\n")
    print(f"recorded {len(items)} {a.split} answers ({backend.live_calls} live calls) to {a.recording}. Nothing was scored.")


if __name__ == "__main__":
    main()
