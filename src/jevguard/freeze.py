"""Freeze manifest: locks the thresholds and question wording before the test split is touched.

    python -m jevguard.freeze --create eval/policies/v0.2_dev_candidate.yaml   # once, when freezing
    python -m jevguard.freeze --check                                          # any time

Test-split tools refuse to run unless the frozen policy and the question wording still match.
Labels may still be reviewed after the freeze, but every change is disclosed in the final report.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from jevguard.evalset.build import load
from jevguard.policy import Policy
from jevguard.questions import QUESTION_SET_VERSION, QUESTIONS
from jevguard.schemas import canonical_json

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "eval" / "FREEZE.json"
FROZEN_POLICY = REPO / "eval" / "policies" / "FROZEN_v0.2.yaml"
ITEMS = REPO / "eval" / "data" / "items.jsonl"


class FreezeError(Exception):
    pass


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def questions_digest() -> str:
    return _sha(canonical_json(QUESTIONS).encode())


def label_digest(item: Any) -> str:
    return _sha(canonical_json({"labels": item.labels.model_dump(), "expected": item.expected_action.value}).encode())


def create(candidate: Path) -> dict[str, Any]:
    if MANIFEST.exists():
        raise FreezeError(f"{MANIFEST} already exists. A freeze is not redone; start a new question-set version instead.")
    FROZEN_POLICY.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(ln for ln in candidate.read_text().splitlines() if not ln.lstrip().startswith("#")) + "\n"
    FROZEN_POLICY.write_text("# FROZEN. Do not edit. Changing anything here invalidates the test run.\n" + body)
    policy = Policy.load(FROZEN_POLICY)
    items = load(ITEMS)
    man = {
        "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "question_set_version": QUESTION_SET_VERSION,
        "questions_sha256": questions_digest(),
        "policy_file": str(FROZEN_POLICY.relative_to(REPO)),
        "policy_digest": policy.digest,
        "policy_file_sha256": _sha(FROZEN_POLICY.read_bytes()),
        "fit_on": "dev split, 48 answers, labels as of the freeze",
        "items_sha256_at_freeze": _sha(ITEMS.read_bytes()),
        "test_label_digests": {i.id: label_digest(i) for i in items if i.split == "test"},
    }
    MANIFEST.write_text(json.dumps(man, indent=2))
    return man


CODE_MANIFEST = REPO / "eval" / "FREEZE_CODE.json"
DECISION_FILES = ("questions.py", "thresholds.yaml", "policy.py", "signals.py", "rules.py", "engine.py", "templates.py",
                  "deterministic.py", "schemas.py", "evalset/gold.py", "evalset/systems.py", "evalset/ablate.py")


def code_digests() -> dict[str, str]:
    """Hashes of the files that decide an action. Supplementary: added after review, so it records the code as of
    that date rather than at the freeze commit (see the note written into the manifest)."""
    return {f: _sha((REPO / "src" / "jevguard" / f).read_bytes()) for f in DECISION_FILES}


def load_manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        raise FreezeError("no freeze manifest: thresholds have not been frozen")
    return json.loads(MANIFEST.read_text())


def verify(policy_path: str | Path | None = None) -> dict[str, Any]:
    """Raise FreezeError unless the frozen policy file and the question wording are exactly as frozen."""
    man = load_manifest()
    path = Path(policy_path) if policy_path else REPO / man["policy_file"]
    if path.resolve() != (REPO / man["policy_file"]).resolve():
        raise FreezeError(f"the test split must use the frozen policy {man['policy_file']}, not {path}")
    if _sha(path.read_bytes()) != man["policy_file_sha256"] or Policy.load(path).digest != man["policy_digest"]:
        raise FreezeError("the frozen policy file has changed since the freeze")
    if QUESTION_SET_VERSION != man["question_set_version"] or questions_digest() != man["questions_sha256"]:
        raise FreezeError("the question wording has changed since the freeze")
    return man


def changed_test_labels(man: dict[str, Any]) -> list[str]:
    """Test items whose label or expected action differs from what was frozen (disclosed in the report)."""
    now = {i.id: label_digest(i) for i in load(ITEMS) if i.split == "test"}
    frozen = man["test_label_digests"]
    return sorted(k for k in set(now) | set(frozen) if now.get(k) != frozen.get(k))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--create", metavar="CANDIDATE_POLICY")
    g.add_argument("--check", action="store_true")
    g.add_argument("--write-code-digests", action="store_true", help="supplementary; see eval/FREEZE_CODE.json")
    g.add_argument("--check-code", action="store_true")
    a = ap.parse_args(argv)
    if a.write_code_digests:
        CODE_MANIFEST.write_text(json.dumps({
            "note": ("Supplementary, added after the test half was scored, in response to review. FREEZE.json covers thresholds, "
                     "question wording and test labels only. Since the freeze commit 454346f the decision code changed in two "
                     "places: engine.py (fail closed on any unexpected error in signal computation; a warning when no policy "
                     "is given) and schemas.py (reject malformed probabilities). Neither changes any decision on the recorded "
                     "answers: `python -m jevguard.evalset.posthoc` re-derives the committed test rows exactly."),
            "digests": code_digests()}, indent=2) + "\n")
        print("written", CODE_MANIFEST)
    elif a.check_code:
        now, then = code_digests(), json.loads(CODE_MANIFEST.read_text())["digests"]
        changed = sorted(k for k in now if now[k] != then.get(k))
        if changed:
            raise SystemExit(f"decision code changed since FREEZE_CODE.json: {changed}")
        print("decision code matches FREEZE_CODE.json")
    elif a.create:
        man = create(Path(a.create))
        print(f"frozen: policy {man['policy_digest']}, questions {man['question_set_version']} {man['questions_sha256'][:12]}")
    else:
        man = verify()
        print(f"ok: policy {man['policy_digest']} and questions {man['question_set_version']} match the freeze; "
              f"test labels changed since freeze: {len(changed_test_labels(man))}")


if __name__ == "__main__":
    main()
