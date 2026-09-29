import json
from pathlib import Path

import pytest

from jevguard import freeze
from jevguard.evalset import final, record, run
from jevguard.evalset.build import load
from jevguard.policy import Policy

REPO = Path(__file__).resolve().parents[1]
ITEMS = str(REPO / "eval" / "data" / "items.jsonl")
pytestmark = pytest.mark.skipif(not freeze.MANIFEST.exists(), reason="thresholds not frozen yet")


def test_committed_freeze_holds():
    man = freeze.verify()
    assert man["policy_digest"] == Policy.load(freeze.FROZEN_POLICY).digest
    assert freeze.changed_test_labels(man) == []


def test_frozen_policy_is_the_dev_candidate_without_the_carried_over_header():
    frozen = freeze.FROZEN_POLICY.read_text()
    assert frozen.startswith("# FROZEN") and "CANDIDATE" not in frozen
    assert Policy.load(freeze.FROZEN_POLICY).digest == Policy.load(REPO / "eval/policies/v0.2_dev_candidate.yaml").digest


def test_a_different_policy_file_is_refused():
    with pytest.raises(freeze.FreezeError, match="frozen policy"):
        freeze.verify(REPO / "eval" / "policies" / "v0.2_dev_candidate.yaml")


def test_editing_the_frozen_policy_is_detected(tmp_path, monkeypatch):
    man = json.loads(freeze.MANIFEST.read_text())
    man["policy_file_sha256"] = "0" * 64
    fake = tmp_path / "FREEZE.json"
    fake.write_text(json.dumps(man))
    monkeypatch.setattr(freeze, "MANIFEST", fake)
    with pytest.raises(freeze.FreezeError, match="policy file has changed"):
        freeze.verify()


def test_changing_the_question_wording_is_detected(monkeypatch):
    edited = json.loads(json.dumps(freeze.QUESTIONS))
    edited["dose_stated"]["instructions"] += " (edited)"
    monkeypatch.setattr(freeze, "QUESTIONS", edited)
    with pytest.raises(freeze.FreezeError, match="question wording"):
        freeze.verify()


def test_a_freeze_cannot_be_redone():
    with pytest.raises(freeze.FreezeError, match="already exists"):
        freeze.create(REPO / "eval" / "policies" / "v0.2_dev_candidate.yaml")


def test_changed_test_labels_are_disclosed(monkeypatch):
    man = json.loads(freeze.MANIFEST.read_text())
    victim = next(iter(man["test_label_digests"]))
    man["test_label_digests"][victim] = "x"
    assert freeze.changed_test_labels(man) == [victim]


def test_test_split_scoring_needs_the_frozen_policy_and_never_defaults_to_another(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # so a failed guard could never write to the real test log
    with pytest.raises(SystemExit, match="pass --policy"):
        run.main(["--system", "jev", "--backend", "simulated", "--split", "test", "--allow-test", "--items", ITEMS])
    with pytest.raises(SystemExit, match="frozen policy"):
        run.main(["--system", "jev", "--backend", "simulated", "--split", "test", "--allow-test", "--items", ITEMS,
                  "--policy", str(REPO / "eval" / "policies" / "v0.2_dev_candidate.yaml")])
    assert not (tmp_path / "eval" / "results" / "test_runs.jsonl").exists()


def test_recording_the_test_split_needs_the_unlock_flag(tmp_path):
    with pytest.raises(SystemExit, match="locked"):
        record.main(["--split", "test", "--recording", str(tmp_path / "t.jsonl"), "--simulated"])


def test_record_then_score_once(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rec, out = tmp_path / "test.jsonl", tmp_path / "final.json"
    record.main(["--split", "test", "--allow-test", "--simulated", "--recording", str(rec), "--items", ITEMS])
    n_test = sum(1 for i in load(ITEMS) if i.split == "test")
    assert len(rec.read_text().splitlines()) == n_test
    with pytest.raises(SystemExit, match="simulated"):
        final.main(["--recording", str(rec), "--allow-test", "--items", ITEMS, "--out", str(out)])
    args = ["--recording", str(rec), "--allow-test", "--allow-simulated", "--items", ITEMS, "--out", str(out)]
    final.main(args)
    rep = json.loads(out.read_text())
    assert "NOT JEV" in rep["WARNING"] and rep["meta"]["n"] == n_test and rep["meta"]["run_number"] == 1
    assert [r["system"] for r in rep["rows"]] == ["rules_only", "jev_alone", "jev_vlmguard_frozen"]
    with pytest.raises(SystemExit, match="already scored"):
        final.main(args)
    final.main([*args, "--again"])
    assert json.loads(out.read_text())["meta"]["run_number"] == 2
    events = [json.loads(line)["event"] for line in (tmp_path / "eval" / "results" / "test_runs.jsonl").read_text().splitlines()]
    assert events == ["recorded", "scored", "scored"]


def test_scoring_refuses_an_incomplete_recording(tmp_path, monkeypatch):
    from jevguard.backends import ReplayMiss
    monkeypatch.chdir(tmp_path)
    rec = tmp_path / "test.jsonl"
    record.main(["--split", "test", "--allow-test", "--simulated", "--recording", str(rec), "--items", ITEMS])
    rec.write_text("".join(rec.read_text().splitlines(keepends=True)[:5]))
    with pytest.raises(ReplayMiss):
        final.main(["--recording", str(rec), "--allow-test", "--allow-simulated", "--items", ITEMS, "--out", str(tmp_path / "x.json")])
    assert not (tmp_path / "x.json").exists()
