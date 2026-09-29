from pathlib import Path

import pytest

from jevguard.evalset import report

REPO = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not report.FINAL.exists(), reason="final test result not present")


def test_readme_results_block_matches_the_json_files():
    text = report.README.read_text()
    assert report.updated(text) == text


def test_readme_has_no_em_dashes_and_names_no_employer():
    for f in ("README.md", "DATASHEET.md", "RUN_LOCALLY.md", "docs/pattern_proposal.md", "docs/PLAN.md"):
        t = (REPO / f).read_text()
        assert "—" not in t, f
        assert ("apothe" + "care") not in t.lower(), f


def test_final_report_is_from_one_scoring_run_of_real_jev_with_no_label_changes_after_freeze():
    import json
    m = json.loads(report.FINAL.read_text())["meta"]
    assert m["run_number"] == 1 and m["models"] == ["jev-1.13.0"] and m["test_labels_changed_since_freeze"] == []


def test_readme_headline_numbers_agree_with_the_data():
    import json
    rows = {r["system"]: r for r in json.loads(report.FINAL.read_text())["rows"]}
    fz = rows["jev_vlmguard_frozen"]
    text = report.README.read_text()
    assert f"caught all {fz['intervention_recall']['n']} problems" in text
    assert f"{fz['false_intervention_rate']['k']} of the {fz['false_intervention_rate']['n']} clean or flag-only" in text
    assert f"caught {rows['jev_alone']['intervention_recall']['k']} of {rows['jev_alone']['intervention_recall']['n']}" in text


def test_readme_exact_match_and_posthoc_numbers_agree_with_the_data():
    import json
    rows = {r["system"]: r for r in json.loads(report.FINAL.read_text())["rows"]}
    post = {r["system"]: r for r in json.loads(report.POSTHOC.read_text())["rows"]}
    text = report.README.read_text()
    for name in ("jev_alone", "jev_vlmguard_frozen"):
        e = rows[name]["exact_action_match"]
        assert f"{e['k']}/{e['n']}" in text
    p = post["same_rule_pack_single_cutoff_posthoc"]["exact_action_match"]
    assert f"{p['k']}/{p['n']} exact" in text
