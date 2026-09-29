# Question set v0.2 results

Ten questions, `QUESTION_SET_VERSION = "v0.2-draft"` (v0.1 plus `self_harm_in_query`). Recording:
`eval/recordings/dev.jsonl` (48 dev answers, jev-1.13.0). Scope: the dev split only. Thresholds in
`eval/policies/v0.2_dev_candidate.yaml` were fit on those same answers and are a candidate, not frozen.
The test split has not been run. 17 of 130 labels have a clinician verdict.

A labeling inconsistency was fixed after the first look at these results: unsafe variants of emergency
scenarios had been labeled as advising urgent care although their text contains none. It changes labels
only, not requests, so no re-recording was needed.

Reproduce: `python -m jevguard.evalset.ablate --recording eval/recordings/dev.jsonl`
