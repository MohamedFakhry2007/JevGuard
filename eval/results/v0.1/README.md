# Question set v0.1 results (frozen)

Nine questions, `QUESTION_SET_VERSION = "v0.1-draft"`. These results were produced from the recordings in
`eval/recordings/` at the git tag `questions-v0.1`. Check out that tag to reproduce them:

    git checkout questions-v0.1
    python -m jevguard.evalset.ablate --recording eval/recordings/dev.jsonl

Scope: the dev split only (47 answers, 22 that need action and 25 that do not). Thresholds in
`eval/policies/v0.1_dev_candidate.yaml` were fit on those same answers. The test split was never run.
Labels: 17 of 126 have a clinician verdict, the rest are drafts.
