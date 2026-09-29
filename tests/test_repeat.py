import json
from pathlib import Path

import pytest

from jevguard.evalset import repeat

REC = Path(__file__).resolve().parents[1] / "eval" / "recordings"


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def row(key, p):
    return {"key": key, "response": {"model": "m", "answers": {"dose_stated": {"type": "noul", "noul": p}}}}


def test_answer_spread_counts_identical_and_range(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write(a, [row("k1", 0.10), row("k2", 0.50)])
    write(b, [row("k1", 0.10), row("k2", 0.56)])
    out = repeat.answer_spread([str(a), str(b)])
    assert out["items_in_all_runs"] == 2 and out["noul_identical_share"] == 0.5
    assert out["noul_range_points"]["dose_stated"] == {"mean": 3.0, "max": 6.0}


def test_only_items_present_in_every_run_are_compared(tmp_path):
    a, b = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write(a, [row("k1", 0.1), row("k2", 0.1)])
    write(b, [row("k1", 0.1)])
    assert repeat.answer_spread([str(a), str(b)])["items_in_all_runs"] == 1


@pytest.mark.skipif(not (REC / "v0.1" / "dev_repeat2.jsonl").exists(), reason="repeat recordings not present")
def test_real_repeat_runs_never_turn_a_gold_intervention_into_no_action(tmp_path):
    out = tmp_path / "r.json"
    repeat.main(["--recordings", *[str(REC / "v0.1" / f) for f in ("dev.jsonl", "dev_repeat1.jsonl", "dev_repeat2.jsonl")], "--skip-missing", "--out", str(out)])
    rep = json.loads(out.read_text())
    assert rep["answers"]["items_in_all_runs"] == 46
    assert rep["decisions"]["gold_interventions_missed_in_any_run"] == []
