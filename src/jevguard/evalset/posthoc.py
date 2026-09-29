"""Post-hoc analysis of the already scored test split. Adds no new model calls and changes no thresholds.

    python -m jevguard.evalset.posthoc --recording eval/recordings/test.jsonl --allow-test

Written after the test half was scored once, in response to review. It reads the same test recording,
checks that the frozen system reproduces the committed result, adds a baseline that was not in the
pre-registered set (the same rule pack with one 0.5 cutoff and no unsure band), and exports per-item
predictions. It logs a "posthoc" event, never a "scored" one. Read its numbers as exploratory.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from jevguard.backends import ReplayBackend
from jevguard.engine import JevGuard
from jevguard.evalset.ablate import JevAloneSystem, row, single_cutoff_policy
from jevguard.evalset.build import load
from jevguard.evalset.run import ITEMS, TEST_LOG, evaluate
from jevguard.evalset.systems import JevRulesSystem, RulesOnlySystem
from jevguard.freeze import REPO, FreezeError, verify
from jevguard.policy import Policy

FINAL = REPO / "eval" / "results" / "final" / "test_v0.2.json"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recording", required=True)
    ap.add_argument("--items", default=ITEMS)
    ap.add_argument("--out", default=str(REPO / "eval" / "results" / "final" / "test_v0.2_posthoc.json"))
    ap.add_argument("--predictions", default=str(REPO / "eval" / "results" / "final" / "test_v0.2_predictions.jsonl"))
    ap.add_argument("--allow-test", action="store_true")
    a = ap.parse_args(argv)
    if not a.allow_test:
        raise SystemExit("the test split is locked: pass --allow-test")
    try:
        man = verify()
    except FreezeError as exc:
        raise SystemExit(f"refusing to run: {exc}") from exc
    policy = Policy.load(REPO / man["policy_file"])
    items = [i for i in load(a.items) if i.split == "test"]
    rb = lambda: ReplayBackend(a.recording)
    systems = {
        "rules_only": evaluate(RulesOnlySystem(), items),
        "jev_alone": evaluate(JevAloneSystem(rb()), items),
        "jev_vlmguard_frozen": evaluate(JevRulesSystem(JevGuard(rb(), policy)), items),
        "same_rule_pack_single_cutoff_posthoc": evaluate(JevRulesSystem(JevGuard(rb(), single_cutoff_policy(policy))), items),
    }
    rows = {k: row(k, v) for k, v in systems.items()}
    committed = {r["system"]: r for r in json.loads(FINAL.read_text())["rows"]}
    for k, r in rows.items():
        if k in committed and r["exact_action_match"] != committed[k]["exact_action_match"]:
            raise SystemExit(f"{k} does not reproduce the committed result; refusing to write")

    out = {
        "meta": {"note": "POST-HOC and exploratory. Not part of the pre-registered comparison.",
                 "at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "policy_digest": policy.digest, "n": len(items)},
        "rows": list(rows.values()),
    }
    Path(a.out).write_text(json.dumps(out, indent=2))
    with open(a.predictions, "w") as fh:
        for i in items:
            rec = {"id": i.id, "expected": i.expected_action.value}
            for k, rs in systems.items():
                rec[k] = next(r.predicted.value for r in rs if r.id == i.id)
            fh.write(json.dumps(rec) + "\n")
    with open(TEST_LOG, "a") as fh:
        fh.write(json.dumps({"event": "posthoc", "split": "test", "policy": policy.digest, "at": out["meta"]["at"]}) + "\n")
    for r in rows.values():
        ic, fi, ex = r["intervention_recall"], r["false_intervention_rate"], r["exact_action_match"]
        print(f"{r['system']:40s} catches {ic['k']}/{ic['n']}  wrong {fi['k']}/{fi['n']}  exact {ex['k']}/{ex['n']}")


if __name__ == "__main__":
    main()
