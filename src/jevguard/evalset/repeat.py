"""How repeatable is Jev? Compare several recordings of the SAME requests.

    python -m jevguard.evalset.repeat --recordings a.jsonl b.jsonl c.jsonl [--policy p.yaml]
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from collections import defaultdict
from pathlib import Path
from typing import Any

from jevguard.backends import ReplayBackend
from jevguard.engine import JevGuard
from jevguard.evalset.build import load
from jevguard.evalset.run import evaluate, with_recordings
from jevguard.evalset.systems import JevRulesSystem
from jevguard.policy import Policy


def answer_spread(paths: list[str]) -> dict[str, Any]:
    runs = [{r["key"]: r for r in map(json.loads, Path(p).read_text().splitlines()) if r} for p in paths]
    keys = set.intersection(*[set(r) for r in runs])
    spread: dict[str, list[float]] = defaultdict(list)
    for k in keys:
        answers = [r[k]["response"]["answers"] for r in runs]
        for q, first in answers[0].items():
            if first["type"] == "noul":
                v = [a[q]["noul"] for a in answers]
                spread[q].append(max(v) - min(v))
    flat = [x for v in spread.values() for x in v]
    return {
        "items_in_all_runs": len(keys), "runs": len(runs),
        "noul_identical_share": sum(x == 0 for x in flat) / len(flat) if flat else None,
        "noul_range_points": {q: {"mean": round(st.mean(v) * 100, 2), "max": round(max(v) * 100, 2)} for q, v in sorted(spread.items())},
    }


def decision_flips(paths: list[str], items_path: str, policy: Policy, split: str = "dev", skip_missing: bool = False) -> dict[str, Any]:
    items = [i for i in load(items_path) if i.split == split]
    skipped: list[str] = []
    if skip_missing:
        items, skipped = with_recordings(items, paths)
    per = [{r.id: r for r in evaluate(JevRulesSystem(JevGuard(ReplayBackend(p), policy)), items)} for p in paths]
    flipped = {i.id: [run[i.id].predicted.value for run in per] for i in items if len({run[i.id].predicted for run in per}) > 1}
    crossing = [k for k, v in flipped.items() if len({a in ("correct", "block", "escalate") for a in v}) > 1]
    gold_missed = [i.id for i in items if i.expected_action.severity >= 2
                   and any(run[i.id].predicted.severity < 2 for run in per)]
    return {"n": len(items), "skipped_missing_recording": skipped, "action_differs": flipped, "intervention_status_differs": crossing,
            "gold_interventions_missed_in_any_run": gold_missed}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recordings", nargs="+", required=True)
    ap.add_argument("--items", default="eval/data/items.jsonl")
    ap.add_argument("--policy")
    ap.add_argument("--skip-missing", action="store_true")
    ap.add_argument("--out", default="eval/results/repeatability_dev.json")
    a = ap.parse_args(argv)
    policy = Policy.load(a.policy) if a.policy else Policy.load()
    rep = {"answers": answer_spread(a.recordings), "decisions": decision_flips(a.recordings, a.items, policy, skip_missing=a.skip_missing), "policy": policy.digest}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, indent=2))
    d = rep["decisions"]
    print(f"yes/no answers identical across runs: {rep['answers']['noul_identical_share']:.0%}")
    print(f"final action differs on {len(d['action_differs'])}/{d['n']} items; intervention status differs on {len(d['intervention_status_differs'])}; gold interventions missed in any run: {len(d['gold_interventions_missed_in_any_run'])}")


if __name__ == "__main__":
    main()
