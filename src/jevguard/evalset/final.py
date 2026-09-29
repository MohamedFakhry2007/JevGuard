"""Score the test split ONCE with the frozen policy.

    python -m jevguard.evalset.final --recording eval/recordings/test.jsonl --allow-test

Refuses unless the freeze still holds, the recording is complete, and this policy has not been scored before.
Compares three systems on the same answers: keyword rules only, Jev alone (one plain cutoff), and Jev with
the VLM-Guard rules using the frozen thresholds. Nothing here can change thresholds or wording.
"""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path
from typing import Any

from jevguard.backends import ReplayBackend
from jevguard.engine import JevGuard
from jevguard.evalset.ablate import JevAloneSystem, row
from jevguard.evalset.build import load
from jevguard.evalset.metrics import summarize
from jevguard.evalset.run import ITEMS, TEST_LOG, evaluate
from jevguard.evalset.systems import JevRulesSystem, RulesOnlySystem
from jevguard.freeze import REPO, FreezeError, changed_test_labels, verify
from jevguard.policy import Policy


def _already_scored(digest: str) -> int:
    p = Path(TEST_LOG)
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text().splitlines()
               if line.strip() and json.loads(line).get("event") == "scored" and json.loads(line).get("policy") == digest)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recording", required=True)
    ap.add_argument("--items", default=ITEMS)
    ap.add_argument("--out", default=str(REPO / "eval" / "results" / "final" / "test_v0.2.json"))
    ap.add_argument("--allow-test", action="store_true")
    ap.add_argument("--again", action="store_true", help="score a second time; the report says so")
    ap.add_argument("--allow-simulated", action="store_true", help="tests only")
    a = ap.parse_args(argv)
    if not a.allow_test:
        raise SystemExit("the test split is locked: pass --allow-test")
    try:
        man = verify()
    except FreezeError as exc:
        raise SystemExit(f"refusing to score: {exc}") from exc
    policy = Policy.load(REPO / man["policy_file"])
    previous = _already_scored(policy.digest)
    if previous and not a.again:
        raise SystemExit(f"the test split was already scored {previous} time(s) with this policy. Scoring again needs --again and is disclosed.")

    rows = [json.loads(line) for line in Path(a.recording).read_text().splitlines() if line.strip()]
    models = {r["response"]["model"] for r in rows}
    simulated = any(m.startswith("simulated") for m in models)
    if simulated and not a.allow_simulated:
        raise SystemExit("this recording comes from the simulated stand-in, not Jev")

    items = [i for i in load(a.items) if i.split == "test"]
    systems = {
        "rules_only": evaluate(RulesOnlySystem(), items),
        "jev_alone": evaluate(JevAloneSystem(ReplayBackend(a.recording)), items),
        "jev_vlmguard_frozen": evaluate(JevRulesSystem(JevGuard(ReplayBackend(a.recording), policy)), items),  # strict: a gap raises
    }
    reviewed = sum(i.review_status == "reviewed" for i in items)
    rule_applied = sum(i.review_status == "rule_applied" for i in items)
    report: dict[str, Any] = {
        "meta": {"scored_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "n": len(items), "models": sorted(models),
                 "question_set": man["question_set_version"], "policy_digest": policy.digest, "frozen_at": man["frozen_at"],
                 "run_number": previous + 1, "clinician_reviewed_test_items": reviewed, "rule_applied_test_items": rule_applied,
                 "test_labels_changed_since_freeze": changed_test_labels(man)},
        "rows": [row(k, v) for k, v in systems.items()],
        "frozen_system_detail": summarize(systems["jev_vlmguard_frozen"]),
        "caveats": [
            "All data is synthetic.",
            f"{reviewed} of {len(items)} test labels have a clinician verdict, {rule_applied} follow a clinician rule applied by the author, the rest are drafts written by the developer.",
            "Thresholds were fit on the dev split only, then frozen before this run.",
            "One reviewer, one model version, small sample: intervals are wide.",
        ],
    }
    if simulated:
        report["WARNING"] = "SIMULATED STAND-IN, NOT JEV. Do not report."
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    Path(TEST_LOG).parent.mkdir(parents=True, exist_ok=True)
    with open(TEST_LOG, "a") as fh:
        fh.write(json.dumps({"event": "scored", "split": "test", "policy": policy.digest, "run": previous + 1, "simulated": simulated,
                             "at": report["meta"]["scored_at"]}) + "\n")
    for r in report["rows"]:
        ic, fi, ex = r["intervention_recall"], r["false_intervention_rate"], r["exact_action_match"]
        print(f"{r['system']:22s} catches {ic['k']}/{ic['n']}  wrong {fi['k']}/{fi['n']}  exact {ex['k']}/{ex['n']}")
    print(f"written to {out}")


if __name__ == "__main__":
    main()
