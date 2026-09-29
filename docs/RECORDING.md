# Recording real Jev responses

Every headline number in this repo must come from real Jev responses recorded once and then
replayed, so anyone can reproduce results without a key.

## What you need
A session or machine that can reach `api.typesafe.ai` with a valid credential.

- **Own machine:** `export TYPESAFE_API_KEY=...` (never commit it).
- **Cloud session where the network proxy injects the credential:** add `--placeholder-key`.
  The official SDK refuses to build a client with no key, so a dummy value is passed and the
  proxy is expected to supply the real one. This path has not been tested yet. If the first
  request fails with an authentication error, the proxy is not injecting for this route.

## Steps
1. `git fetch origin claude/magical-faraday-7rml4l && git checkout claude/magical-faraday-7rml4l`
2. `pip install -e ".[dev]"`
3. Dry run on a few items to check the wiring and look at real latency:
   `python -m jevguard.evalset.run --system jev --backend live --recording eval/recordings/pilot.jsonl --split dev`
   then stop it after a handful of items, or copy 5 items into a scratch items file.
4. Record the full dev split:
   `python -m jevguard.evalset.run --system jev --backend live --recording eval/recordings/dev.jsonl --split dev --out eval/results/jev_dev_raw.json`
   The recording is resumable. Re-running only calls Jev for items that are missing.
5. Commit `eval/recordings/dev.jsonl` and the report to a NEW branch (for example
   `claude/record-dev`), not to `claude/magical-faraday-7rml4l`, and push it. Do not record the
   test split until thresholds and calibration are frozen on dev.

## Cost and time
About 46 dev items at roughly 500 to 1,800 input tokens each. At the documented $42 per billion
input tokens that is a fraction of a cent. Expect a few seconds of wall time.

## Repeatability run (recommended before freezing)
Live Jev answers were not identical between two recordings of the same 46 dev items (the
pilot and the committed run differed on 1 false intervention and 2 escalations). To measure
that spread, record the dev split two more times into separate files:

    python -m jevguard.evalset.run --system jev --backend live --placeholder-key --split dev \
        --recording eval/recordings/dev_repeat1.jsonl --out eval/results/jev_dev_repeat1.json
    python -m jevguard.evalset.run --system jev --backend live --placeholder-key --split dev \
        --recording eval/recordings/dev_repeat2.jsonl --out eval/results/jev_dev_repeat2.json

Commit both to a new branch (for example `claude/record-repeat`). Cost is about $0.002 each.

## Test split (only after thresholds are frozen and you say so)
    python -m jevguard.evalset.run --system jev --backend live --placeholder-key --split test --allow-test \
        --recording eval/recordings/test.jsonl --policy eval/policies/FROZEN.yaml --out eval/results/jev_test.json
The run is appended to eval/results/test_runs.jsonl. Do it once.
