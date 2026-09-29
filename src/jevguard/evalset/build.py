"""Deterministically build eval/data/items.jsonl from scenarios and hand-written items.

    python -m jevguard.evalset.build [--out eval/data/items.jsonl]
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from jevguard.evalset.gold import expected_action
from jevguard.evalset.handwritten import HAND
from jevguard.evalset.scenarios import SCENARIOS, SRC, Scenario
from jevguard.evalset.schema import EvalItem, Labels

SPLIT_SALT = "jevguard-split-v1"

# category -> label overrides applied on top of the safe base labels
MUTATION_LABELS: dict[str, dict] = {
    "dose_stated": {"dose_stated": True},
    "rx_stop_directive": {"rx_action": True},
    "rx_dose_directive": {"rx_action": True, "dose_stated": True},
    "discourages_care": {"discourages_care": True},
    "contraindication": {"contraindication_conflict": True},
    "contra_rx": {"contraindication_conflict": True, "rx_action": True},
    "contra_rx_dose": {"contraindication_conflict": True, "rx_action": True, "dose_stated": True},
    "rx_discourage": {"rx_action": True, "discourages_care": True},
    "red_flag_no_urgent": {"urgent_care_advised": False},
    "red_flag_dose": {"urgent_care_advised": False, "dose_stated": True},
    "overconfident_diagnosis": {"certainty_definitive": True},
    "unsupported_claim": {"unsupported_claim": True},
}


def split_of(scenario_id: str) -> str:
    h = int(hashlib.sha256(f"{SPLIT_SALT}:{scenario_id}".encode()).hexdigest(), 16)
    return "dev" if h % 3 == 0 else "test"


def _base_labels(sc: Scenario) -> Labels:
    return Labels(red_flag_in_query=sc.red_flag, urgent_care_advised=sc.red_flag, request_scope=sc.scope)


def _from_scenario(sc: Scenario) -> list[EvalItem]:
    common = {
        "scenario_id": sc.id, "split": split_of(sc.id), "origin": "mutation", "question": sc.question,
        "context": sc.context, "sources": [SRC + sc.source], "source_ref": sc.seed_ref,
        "tags": ["heartsafe_seed"] if sc.seed_ref else [],
    }
    base = _base_labels(sc)
    items = [EvalItem(id=f"{sc.id}-safe", kind="safe", category="safe", answer=f"{sc.lead} {sc.tail}",
                      labels=base, expected_action=expected_action(base), **{**common, "origin": "safe_base"})]
    for cat, bad_tail in sc.bad.items():
        lb = base.model_copy(update=MUTATION_LABELS[cat])
        items.append(EvalItem(id=f"{sc.id}-{cat}", kind="unsafe", category=cat, answer=f"{sc.lead} {bad_tail}",
                              labels=lb, expected_action=expected_action(lb), **common))
    return items


def _from_hand(h) -> EvalItem:
    return EvalItem(
        id=h.id, scenario_id=h.id, split=split_of(h.id), kind=h.kind, category=h.category,
        origin="hand_written", tags=h.tags, question=h.question, context=h.context,
        sources=h.sources, answer=h.answer, labels=h.labels,
        expected_action=expected_action(h.labels), notes=h.notes,
    )


def build_items() -> list[EvalItem]:
    items: list[EvalItem] = []
    for sc in SCENARIOS:
        items.extend(_from_scenario(sc))
    items.extend(_from_hand(h) for h in HAND)
    return items


def write(items: list[EvalItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(i.model_dump_json() + "\n" for i in items))


def load(path: str | Path) -> list[EvalItem]:
    return [EvalItem.model_validate_json(line) for line in Path(path).read_text().splitlines() if line.strip()]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/data/items.jsonl")
    args = ap.parse_args()
    its = build_items()
    write(its, Path(args.out))
    print(f"wrote {len(its)} items to {args.out}")
