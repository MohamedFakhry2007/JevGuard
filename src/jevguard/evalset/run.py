"""Run a system over the evaluation set and write a stamped JSON report.

    python -m jevguard.evalset.run --system rules_only --split dev --out eval/results/rules_only_dev.json
    python -m jevguard.evalset.run --system jev --backend replay --recording eval/recordings/dev.jsonl --split dev
    python -m jevguard.evalset.run --system jev --backend live --recording eval/recordings/dev.jsonl --split dev

The test split needs --allow-test and every such run is appended to eval/results/test_runs.jsonl.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
from typing import Any

from jevguard import calibration
from jevguard.backends import RecordReplayBackend, ReplayBackend, SimulatedBackend
from jevguard.engine import JevGuard
from jevguard.evalset.build import load
from jevguard.evalset.metrics import ItemResult, signal_report, summarize
from jevguard.evalset.schema import EvalItem
from jevguard.evalset.systems import JevRulesSystem, RulesOnlySystem, System
from jevguard.policy import Policy

ITEMS = "eval/data/items.jsonl"
TEST_LOG = "eval/results/test_runs.jsonl"


def with_recordings(items: list[EvalItem], recordings: list[str]) -> tuple[list[EvalItem], list[str]]:
    """Split items into those recorded in EVERY file and the ids that are not. For interim analysis only:
    the default runs stay strict so a gap can never be scored silently."""
    from jevguard.questions import build_request
    rbs = [ReplayBackend(r) for r in recordings]
    have = [i for i in items if all(rb.has(*build_request(i.to_turn())) for rb in rbs)]
    ids = {i.id for i in have}
    return have, [i.id for i in items if i.id not in ids]


def evaluate(system: System, items: list[EvalItem]) -> list[ItemResult]:
    """A ReplayMiss is deliberately not caught here: a gap must stop the run."""
    out = []
    for it in items:
        o = system.decide(it.to_turn())
        out.append(ItemResult(
            id=it.id, split=it.split, kind=it.kind, category=it.category, tags=it.tags,
            expected=it.expected_action, predicted=o.action, failure=o.failure, latency_ms=o.latency_ms,
            total_ms=o.total_ms, cost_usd=o.cost_usd, input_tokens=o.input_tokens, reasons=o.reasons,
            signals=o.signals,
        ))
    return out


def build_report(system: System, items: list[EvalItem], results: list[ItemResult], meta: dict[str, Any]) -> dict[str, Any]:
    by_id = {i.id: i for i in items}
    report: dict[str, Any] = {"meta": meta, "summary": summarize(results)}
    if any(r.signals for r in results):
        report["signals_raw"] = signal_report(results, by_id, "p_raw")
        report["signals_calibrated"] = signal_report(results, by_id, "p")
    if meta.get("backend") == "simulated":
        report["WARNING"] = "SIMULATED BACKEND, NOT JEV. These numbers say nothing about Jev. Do not report."
    if any(i.review_status != "reviewed" for i in items):
        report["NOTICE"] = "Labels are unreviewed drafts."
    report["results"] = [r.model_dump(mode="json") for r in results]
    return report


def _make_system(args: argparse.Namespace) -> tuple[System, str]:
    if args.system == "rules_only":
        return RulesOnlySystem(), "none"
    if args.backend == "simulated":
        backend = SimulatedBackend()
    elif args.backend == "replay":
        backend = ReplayBackend(args.recording)
    else:
        from jevguard.backends.live import LiveBackend
        kw: dict[str, Any] = {"api_key": "proxy-injected"} if args.placeholder_key else {}
        backend = RecordReplayBackend(args.recording, LiveBackend(model=args.model, **kw)) if args.recording else LiveBackend(model=args.model, **kw)
    policy = Policy.load(args.policy) if args.policy else Policy.load()
    cals = calibration.load(args.calibration) if args.calibration else None
    return JevRulesSystem(JevGuard(backend, policy, cals)), args.backend


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", choices=["rules_only", "jev"], required=True)
    ap.add_argument("--backend", choices=["simulated", "replay", "live"], default="replay")
    ap.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    ap.add_argument("--items", default=ITEMS)
    ap.add_argument("--recording")
    ap.add_argument("--model", default="jev-latest")
    ap.add_argument("--placeholder-key", action="store_true",
                    help="pass a dummy api_key when the network proxy injects the real credential")
    ap.add_argument("--policy")
    ap.add_argument("--calibration")
    ap.add_argument("--out")
    ap.add_argument("--allow-test", action="store_true")
    args = ap.parse_args(argv)

    if args.split != "dev" and not args.allow_test:
        raise SystemExit("the test split is locked: fit and freeze on dev first, then pass --allow-test")
    if args.split != "dev" and args.system == "jev":
        from jevguard.freeze import FreezeError, verify
        if not args.policy:
            raise SystemExit("refusing to touch the test split: pass --policy eval/policies/FROZEN_v0.2.yaml")
        try:
            verify(args.policy)
        except FreezeError as exc:
            raise SystemExit(f"refusing to touch the test split: {exc}") from exc
    if args.system == "jev" and args.backend != "simulated" and not args.recording:
        raise SystemExit("--recording is required for the replay and live backends")

    items = [i for i in load(args.items) if args.split == "all" or i.split == args.split]
    system, backend_name = _make_system(args)
    results = evaluate(system, items)
    meta = {"system": system.name, "backend": backend_name, "split": args.split, "n": len(items),
            "run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "policy": (Policy.load(args.policy) if args.policy else Policy.load()).digest if args.system == "jev" else None,
            "calibration": args.calibration}
    report = build_report(system, items, results, meta)
    if args.split != "dev":
        Path(TEST_LOG).parent.mkdir(parents=True, exist_ok=True)
        with open(TEST_LOG, "a") as fh:
            fh.write(json.dumps(meta) + "\n")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2))
    s = report["summary"]
    print(f"{system.name} on {args.split} ({backend_name}), n={s['n']}")
    for k in ("intervention_recall", "false_intervention_rate", "false_block_or_escalate_rate", "escalation_rate_all"):
        r = s[k]
        print(f"  {k}: {r['k']}/{r['n']} = {r['rate']:.2f}  95% CI {r['ci95']}" if r["rate"] is not None else f"  {k}: n/a")
    if "WARNING" in report:
        print("  " + report["WARNING"])


if __name__ == "__main__":
    main()
