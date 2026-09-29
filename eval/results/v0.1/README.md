# Question set v0.1 results (frozen)

Nine questions, `QUESTION_SET_VERSION = "v0.1-draft"`. The recordings are in `eval/recordings/v0.1/` and were
made with that question set, so they only replay through the code as it was at that time. To reproduce these
results, check out the commit that added this file:

    git log --diff-filter=A --format=%h -- eval/results/v0.1/README.md
    git checkout <that commit>
    python -m jevguard.evalset.ablate --recording eval/recordings/dev.jsonl

Scope: the dev split only (47 answers, 22 that need action and 25 that do not). Thresholds in
`eval/policies/v0.1_dev_candidate.yaml` were fit on those same answers. The test split was never run.
Labels: 17 of 126 have a clinician verdict, the rest are drafts.
Repeatability: `repeatability_dev.json` (three runs of the same requests).
