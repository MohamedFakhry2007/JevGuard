# A Jev pattern: a risk-tiered, fail-closed answer guard

Status: a proposal from one worked example, not a spec.

**Relation to an existing pattern.** TypeSafe's [Confidence-Gated Routing](https://docs.typesafe.ai/patterns/confidence-routing)
gates an action on confidence, with higher bars for riskier actions and three outcomes: act, ask, or hand to a person.
This proposal is a narrower case of the same idea for guarding generated text. It adds four things: Noul questions
that carry no `confidence`, so the gate is on the probability; a fail-closed rule when a high-risk check is unsure;
combining several questions in code before gating; and a five-way action set with a full audit record.

## Problem
A generative system produces text that a person will act on. Each answer needs a fast, cheap check before
delivery, and the check must be inspectable. Asking another LLM for a verdict is slow and hard to audit.

## Pattern
1. **Split the judgment into narrow Noul questions**, each phrased so `true` means the risky property is present.
   Ask them all in one call about the same state.
2. **Combine questions in code, not in a prompt.** Example: "the user describes emergency symptoms" and "the answer
   advises urgent care" are separate Noul questions. The product `p(emergency) * (1 - p(urgent))` is the signal.
3. **Give each check a risk tier and two thresholds.** Below `uncertain_at` is clear, between the two is unsure,
   above `act_at` has fired. High-risk checks act earlier and treat the unsure band as an escalation.
4. **Fail closed.** A timeout, an API error, an unparsable or incomplete response escalates. It never passes.
5. **Resolve by severity** (escalate, block, correct, flag, pass) in one final rule, so rule order cannot undo a block.
6. **Corrections are fixed templates**, never model rewrites.
7. **Record everything**: probabilities, bands, rules fired, model version, request id, policy digest.

## Sketch
```python
response = client.system_one(state=turn.to_state(), questions=QUESTIONS)   # 10 questions, one call
signals = {sid: band(p_of(response, sid), POLICY[sid]) for sid in SIGNALS}
signals["emergency_no_urgent"] = band(max(p_red_flag, p_emergency_scope) * (1 - p_urgent), POLICY["emergency_no_urgent"])
action = worst(rule(signals) for rule in RULES)                             # deterministic
```

## Evidence from this project (synthetic data, one reviewer, see the README for limits)
- Jev's probabilities ranked unsafe above safe with an AUC of 0.96 or higher on 11 of 12 checks (tune half).
- On 82 sealed answers, the pattern caught 38 of 38 problems and never gave a problem too weak an action, where a
  single 50% cutoff gave a too-weak action to 11 of 38. The cost was more wrong interventions (6 of 44 versus 2 of 44).
- Median Jev time 282 ms for ten questions, about $0.05 per 1,000 checks. The rule layer adds under a millisecond.

## Design points that seem worth standardising
- **Thresholds need data.** Jev's background level on a check can sit at about 10% for clearly safe inputs, so a fixed
  "unsure from 10%" band fires constantly. Thresholds were fit on labeled examples, with floors so tuning cannot chase noise.
- **Noul has no `confidence`.** The pattern gates on the probability itself.
- **Freeze before the test set.** Lock thresholds and question wording, record test answers without scoring, score once.

## Questions I would ask the Jev team
1. Is there a recommended way to phrase a Noul so negation ("do not double the dose") is read correctly? One such
   answer scored 44% on "directs a prescription change".
2. Same request, slightly different numbers: 63% of yes/no answers were identical across three runs, and the largest
   change was seven points. Is that expected, and is there a way to pin it?
3. Guidance on how to choose `uncertain_at` for a Noul whose background level is not near zero?
4. Would a batch of narrow Noul questions with shared state be billed once for the state, as it appears to be?
