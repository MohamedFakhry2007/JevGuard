"""VLM-Guard rule pack. Each rule reads calibrated signals and records a finding.

A final ResolveRule applies a severity order (escalate > block > correct > flag > pass),
because the VLM-Guard engine runs rules in sequence with no precedence of its own.
"""
from __future__ import annotations

from typing import Any

from vlm_guard import Analysis, BaseRule, RuleResult

from jevguard import templates
from jevguard.schemas import Action, worst


def _band(a: Analysis, sid: str) -> str:
    return a.metadata["signals"][sid]["band"]


def _p(a: Analysis, sid: str) -> float:
    return a.metadata["signals"][sid]["p"]


def _finding(a: Analysis, rule: str, action: Action, reason: str, append: str | None = None) -> RuleResult:
    a.metadata.setdefault("findings", []).append(
        {"rule": rule, "action": action.value, "reason": reason, "append": append}
    )
    return RuleResult(action_taken=True, action_type=action.value, message=reason)


class SignalGateRule(BaseRule):
    """Fire one action when a signal is fired, and optionally another when uncertain."""

    def __init__(self, signal: str, on_fired: Action, on_uncertain: Action | None = None,
                 append: str | None = None, reason: str = ""):
        self.signal, self.on_fired, self.on_uncertain, self.append = signal, on_fired, on_uncertain, append
        self.name = f"jevguard.{signal}"
        self.description = reason or f"Gate on {signal}"

    def condition(self, analysis: Analysis, context: dict) -> bool:
        b = _band(analysis, self.signal)
        return b == "fired" or (b == "uncertain" and self.on_uncertain is not None)

    def action(self, analysis: Analysis, context: dict) -> tuple[Analysis, RuleResult]:
        p = _p(analysis, self.signal)
        if _band(analysis, self.signal) == "fired":
            res = _finding(analysis, self.name, self.on_fired, f"{self.signal} fired (p={p:.2f})", self.append)
        else:
            res = _finding(analysis, self.name, self.on_uncertain,  # type: ignore[arg-type]
                           f"{self.signal} uncertain (p={p:.2f}), failing closed")
        return analysis, res


class DoseAndRxRule(BaseRule):
    """A dose alone is information. A dose plus a prescription-drug directive is a block."""

    name = "jevguard.dose_and_rx"
    description = "Block dosing directives for prescription drugs; escalate uncertain ones"

    def condition(self, analysis: Analysis, context: dict) -> bool:
        return _band(analysis, "rx_action") != "clear" or _band(analysis, "dose_stated") == "fired"

    def action(self, analysis: Analysis, context: dict) -> tuple[Analysis, RuleResult]:
        rx, dose = _band(analysis, "rx_action"), _band(analysis, "dose_stated")
        if rx == "fired" and dose == "fired":
            return analysis, _finding(analysis, self.name, Action.BLOCK, "prescription directive with a specific dose")
        if rx == "fired":
            return analysis, _finding(analysis, self.name, Action.ESCALATE, "prescription directive without a dose")
        if rx == "uncertain":
            return analysis, _finding(analysis, self.name, Action.ESCALATE, "possible prescription directive, failing closed")
        return analysis, _finding(analysis, self.name, Action.FLAG, "specific dose stated")


class UnsupportedClaimRule(BaseRule):
    name = "jevguard.unsupported_claim"
    description = "Flag claims Jev finds unsupported, or uncertain ones with no citation"

    def condition(self, analysis: Analysis, context: dict) -> bool:
        b = _band(analysis, "unsupported_claim")
        return b == "fired" or (b == "uncertain" and not analysis.metadata["det"]["has_citation"])

    def action(self, analysis: Analysis, context: dict) -> tuple[Analysis, RuleResult]:
        return analysis, _finding(analysis, self.name, Action.FLAG,
                                  f"unsupported claim (p={_p(analysis, 'unsupported_claim'):.2f})")


class DoseRegexDisagreementRule(BaseRule):
    """Belt and braces: a deterministic dose pattern that Jev missed is still a flag."""

    name = "jevguard.dose_regex_disagreement"
    description = "Flag when the dose regex fires but Jev sees no dose"

    def condition(self, analysis: Analysis, context: dict) -> bool:
        return analysis.metadata["det"]["dose_regex"] and _band(analysis, "dose_stated") == "clear"

    def action(self, analysis: Analysis, context: dict) -> tuple[Analysis, RuleResult]:
        return analysis, _finding(analysis, self.name, Action.FLAG, "dose pattern found but Jev saw no dose")


class PromoteVerifiedRule(BaseRule):
    """VLM-Guard 'Promote': every risk signal is clear, so confidence is raised to High."""

    name = "jevguard.promote_verified"
    description = "Promote confidence when all risk signals are clear and nothing else fired"

    def condition(self, analysis: Analysis, context: dict) -> bool:
        sigs = analysis.metadata["signals"].values()
        return not analysis.metadata.get("findings") and all(
            s["band"] == "clear" for s in sigs if s["is_risk"]
        )

    def action(self, analysis: Analysis, context: dict) -> tuple[Analysis, RuleResult]:
        analysis.metadata["promoted"] = True
        return analysis, RuleResult(action_taken=True, action_type="promote",
                                    message="all risk signals clear")


class ResolveRule(BaseRule):
    """Always last. Picks the most severe finding and builds the text to deliver."""

    name = "jevguard.resolve"
    description = "Resolve findings by severity and apply fixed-template corrections"

    def condition(self, analysis: Analysis, context: dict) -> bool:
        return True

    def action(self, analysis: Analysis, context: dict) -> tuple[Analysis, RuleResult]:
        findings: list[dict[str, Any]] = analysis.metadata.get("findings", [])
        final = worst(Action(f["action"]) for f in findings)
        original = analysis.metadata["original_text"]
        if final is Action.BLOCK:
            text = templates.BLOCK_FALLBACK
        elif final is Action.ESCALATE:
            text = templates.ESCALATE_HOLD
        elif final is Action.CORRECT:
            keys = list(dict.fromkeys(f["append"] for f in findings if f["action"] == "correct" and f["append"]))
            text = "\n\n".join([original, *[templates.APPENDS[k] for k in keys]])
        else:
            text = original
        analysis.metadata["final_text"] = text
        analysis.label = final.value
        analysis.confidence = (
            "High" if analysis.metadata.get("promoted") else "Low" if final.severity >= Action.BLOCK.severity else "Medium"
        )
        reason = "; ".join(f["reason"] for f in findings) or "no findings"
        return analysis, RuleResult(action_taken=True, action_type=final.value, message=reason)


def default_rules() -> list[BaseRule]:
    return [
        SignalGateRule("contraindication_conflict", Action.BLOCK, Action.ESCALATE,
                       reason="Answer conflicts with the patient context"),
        SignalGateRule("discourages_care", Action.BLOCK, Action.ESCALATE,
                       reason="Answer discourages seeking care"),
        SignalGateRule("self_harm_no_urgent", Action.ESCALATE, Action.ESCALATE,
                       reason="Self-harm message without a crisis response, a person must engage"),
        DoseAndRxRule(),
        SignalGateRule("red_flag_no_urgent", Action.CORRECT, Action.ESCALATE, append="urgent_care",
                       reason="Emergency evidence without urgent-care advice"),
        SignalGateRule("certainty_definitive", Action.CORRECT, append="hedge",
                       reason="Answer states a diagnosis as certain"),
        UnsupportedClaimRule(),
        DoseRegexDisagreementRule(),
        PromoteVerifiedRule(),
        ResolveRule(),
    ]
