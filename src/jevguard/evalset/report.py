"""Render the results tables from the JSON result files, so README numbers cannot drift from the data.

    python -m jevguard.evalset.report            # rewrite the block between the markers in README.md
    python -m jevguard.evalset.report --check    # fail if README.md is out of date
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
FINAL = REPO / "eval" / "results" / "final" / "test_v0.2.json"
DEV = REPO / "eval" / "results" / "v0.2" / "ablation_dev.json"
README = REPO / "README.md"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"

NAMES = {
    "rules_only": "Keyword rules only (no model)",
    "jev_alone": "Jev alone, one 50% cutoff",
    "jev_vlmguard_frozen": "**Jev + VLM-Guard rules, frozen thresholds**",
    "jev_vlmguard (provisional thresholds)": "Jev + rules, starting thresholds",
    "jev_vlmguard (tuned on dev, in-sample)": "Jev + rules, tuned on these answers",
    "jev_vlmguard (tuned, leave-one-scenario-out)": "Jev + rules, tuned, scenario held out",
}


def rate(x: dict[str, Any]) -> str:
    if x["rate"] is None:
        return "n/a"
    return f"{x['k']}/{x['n']} ({x['rate']:.0%}; {x['ci95'][0]:.0%} to {x['ci95'][1]:.0%})"


def table(rows: list[dict[str, Any]]) -> str:
    head = ("| System | Problems caught | Clean answers wrongly acted on | Exact right action | Problems given too weak an action | Clean answers held for a clinician |\n"
            "|---|---|---|---|---|---|\n")
    body = "".join(
        f"| {NAMES.get(r['system'], r['system'])} | {rate(r['intervention_recall'])} | {rate(r['false_intervention_rate'])} | "
        f"{rate(r['exact_action_match'])} | {rate(r['under_severe_on_interventions'])} | {rate(r['held_for_clinician_on_clean_items'])} |\n"
        for r in rows)
    return head + body


def render() -> str:
    fin = json.loads(FINAL.read_text())
    dev = json.loads(DEV.read_text())
    m, d = fin["meta"], fin["frozen_system_detail"]
    out = [
        "#### Final test (82 sealed answers, scored once)",
        "",
        (f"Model `{', '.join(m['models'])}`, question set `{m['question_set']}`, frozen policy `{m['policy_digest']}`, "
         f"run number {m['run_number']}. {m['clinician_reviewed_test_items']} of {m['n']} test labels have a clinician verdict; "
         f"{len(m['test_labels_changed_since_freeze'])} labels changed after the freeze."),
        "",
        table(fin["rows"]),
        "Ranges are 95% Wilson intervals. \"Problems\" are the answers whose gold action is correct, block or escalate.",
        "",
        "Problems caught, by failure mode (Jev + rules, frozen):",
        "",
        "| Failure mode | Caught |\n|---|---|\n" + "".join(f"| {k.replace('_', ' ')} | {v['k']}/{v['n']} |\n" for k, v in d["by_category"].items()),
        (f"Time inside the Jev call: median {d['latency_ms']['p50']:.0f} ms, 95th percentile {d['latency_ms']['p95']:.0f} ms. "
         f"The rule layer adds a median {d['total_ms']['p50']:.2f} ms. Cost about ${d['cost_per_1k_checks_usd']:.3f} per 1,000 checks "
         f"at the quoted $42 per billion input tokens (output is free). Fail-closed events: {d['fail_closed_count']}."),
        "",
        "#### Tune half (48 answers the thresholds were fit on, so optimistic)",
        "",
        table(dev["rows"]),
    ]
    return "\n".join(out) + "\n"


def updated(text: str) -> str:
    a, b = text.index(START) + len(START), text.index(END)
    return text[:a] + "\n" + render() + text[b:]


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    text = README.read_text()
    new = updated(text)
    if a.check:
        if new != text:
            sys.exit("README.md results block is out of date: run python -m jevguard.evalset.report")
        print("README results block is up to date")
    else:
        README.write_text(new)
        print("README results block rewritten")


if __name__ == "__main__":
    main()
