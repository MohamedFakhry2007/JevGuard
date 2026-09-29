# JevGuard build plan (approved)

Status legend: done, next, later.

## Goal
Show Jev as a fast, cheap, calibrated judgment layer on every answer of a generative clinical
chatbot. Jev answers atomic typed safety questions. Deterministic VLM-Guard rules turn them
into one of: pass, flag, correct, block, escalate. Every decision is audited.

## Design rules
1. Everything runs with no API key: replay backend for real recordings, simulated backend for
   plumbing. The simulated backend is not Jev and never produces reported results.
2. Never gate on raw Jev confidence. Noul answers carry none, and MedJev measured Jev as
   overconfident. Calibrate probabilities per signal on the dev split, then band them.
3. Risk-scaled bands. High-tier signals fail closed: an uncertain band escalates.
4. Any backend failure or incomplete response escalates. A missing replay recording is an
   error, not an escalation, so evaluations cannot silently score gaps.
5. Corrections are fixed templates. No model rewrites clinical text.
6. Thresholds are chosen on dev, frozen, then the test split is run once.
7. Synthetic data is labeled synthetic. No employer data of any kind.

## Milestones
| Day | Scope | Status |
|---|---|---|
| 0 | Packaging patch for vlm-guard (docs/upstream), repo scaffold, CI | done (patch not yet applied upstream) |
| 1 | Schemas, questions v0.1-draft, backends (replay, recording, simulated, live SDK), calibration, policy, rule pack, resolver, engine, audit, offline tests | done |
| 1 | Eval dataset schema, gold policy, 125 draft items, DATASHEET | done (labels unreviewed) |
| 2 | Eval harness, metrics with Wilson intervals, rules-only baseline run | next |
| 2 | Grow dataset to about 240, clinician review of labels, LLM judge baseline | later |
| 3 | Record real Jev on dev (needs key), tune wording on dev only, fit calibration and thresholds, freeze, run test once, judge run, ablations | later |
| 4 | Streamlit UI, README with diagram and honest results, DATASHEET, pattern proposal | later |

## When a key is needed
Nothing above needs one. Needed for: piloting question wording, recording dev and test runs,
measuring real latency. The judge baseline needs a separate LLM key.

## Deviation from the strategy message
A prescription directive without a dose escalates (the strategy said flag). Stopping a
prescription drug is high risk even with no number attached. To be re-checked on dev.

## Second deviation (found while writing the gold policy)
The first rule pack escalated every emergency-scope request, which would have turned good
answers ("call emergency services") into false escalations. Emergency evidence (red flag in the
question OR emergency scope) now feeds the red-flag composite instead, and the diagnosis-request
scope is a logged routing signal with no action.
