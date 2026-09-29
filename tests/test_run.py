import json

import pytest

from jevguard.backends import (
    RecordReplayBackend,
    ReplayBackend,
    ReplayMiss,
    SimulatedBackend,
)
from jevguard.engine import JevGuard
from jevguard.evalset import run
from jevguard.evalset.build import build_items
from jevguard.evalset.systems import JevRulesSystem, RulesOnlySystem


def dev_items(n=None):
    it = [i for i in build_items() if i.split == "dev"]
    return it[:n] if n else it


def test_every_dev_item_gets_a_decision_from_both_systems():
    for system in (RulesOnlySystem(), JevRulesSystem(JevGuard(SimulatedBackend()))):
        out = run.evaluate(system, dev_items())
        assert len(out) == len(dev_items()) and all(r.predicted for r in out)


def test_replay_miss_stops_the_run_instead_of_scoring_a_gap(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    with pytest.raises(ReplayMiss):
        run.evaluate(JevRulesSystem(JevGuard(ReplayBackend(empty))), dev_items(1))


def test_record_replay_pays_once_and_resumes(tmp_path):
    path = tmp_path / "rec.jsonl"
    first = RecordReplayBackend(path, SimulatedBackend())
    a = run.evaluate(JevRulesSystem(JevGuard(first)), dev_items(5))
    assert first.live_calls == 5
    second = RecordReplayBackend(path, SimulatedBackend())  # a new process picks the file up
    b = run.evaluate(JevRulesSystem(JevGuard(second)), dev_items(8))
    assert second.live_calls == 3  # only the three new items
    assert [r.predicted for r in a] == [r.predicted for r in b[:5]]
    assert len(ReplayBackend(path)) == 8


def test_report_is_stamped_when_simulated_and_when_labels_are_unreviewed(tmp_path):
    out = tmp_path / "r.json"
    run.main(["--system", "jev", "--backend", "simulated", "--split", "dev", "--out", str(out)])
    rep = json.loads(out.read_text())
    assert "NOT JEV" in rep["WARNING"] and "unreviewed" in rep["NOTICE"]
    assert rep["meta"]["backend"] == "simulated" and "signals_raw" in rep


def test_test_split_is_locked_and_logged(tmp_path, monkeypatch):
    items = str(run.ITEMS)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "eval" / "data").mkdir(parents=True)
    import shutil
    from pathlib import Path
    shutil.copy(Path(__file__).resolve().parents[1] / run.ITEMS, tmp_path / items)
    with pytest.raises(SystemExit, match="locked"):
        run.main(["--system", "rules_only", "--split", "test"])
    run.main(["--system", "rules_only", "--split", "test", "--allow-test"])
    log = (tmp_path / run.TEST_LOG).read_text().splitlines()
    assert len(log) == 1 and json.loads(log[0])["split"] == "test"


def test_jev_system_requires_a_recording_for_replay_and_live():
    with pytest.raises(SystemExit, match="recording"):
        run.main(["--system", "jev", "--backend", "replay", "--split", "dev"])
