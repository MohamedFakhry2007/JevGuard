"""Cheap deterministic checks. They double as the rules-only baseline in the evaluation."""
from __future__ import annotations

import re

from jevguard.schemas import Action, ChatTurn, worst

_NUM_WORDS = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|fifty|hundred|thousand)"
_DOSE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|µg|g|ml|mL|units?|iu|IU)\b"
    rf"|\b{_NUM_WORDS}(?:[\s-]+\w+){{0,2}}\s+(?:milligrams?|micrograms?|grams?|milliliters?)\b",
    re.IGNORECASE,
)
_IMPERATIVE = re.compile(r"\b(take|start|stop|increase|double|skip|reduce|use)\b", re.IGNORECASE)
_CITATION = re.compile(r"\[\d+\]|\(sources?:|\bsources?:|https?://|\baccording to\b", re.IGNORECASE)
_URGENT = re.compile(
    r"\b(call|dial)\s+(?:911|999|112|(?:your\s+local\s+)?emergency(?:\s+(?:services|number))?|an ambulance)"
    r"|\bemergency (?:room|department|care|services)\b"
    r"|\bseek (?:urgent|emergency|immediate)(?: medical)? (?:care|attention|help)\b"
    r"|\bgo to the (?:er|ed|emergency)\b"
    r"|\bcrisis (?:line|service|team)s?\b|\bhelpline\b|\b988\b",
    re.IGNORECASE,
)
_RED_FLAG = re.compile(
    r"chest (?:pain|pressure|tightness)|(?:trouble|difficulty|hard to) breath|short(?:ness)? of breath"
    r"|can'?t breathe|slurred speech|face droop|sudden weakness|suicid|kill myself|severe bleeding"
    r"|worst headache|coughing up blood|unconscious|passed out",
    re.IGNORECASE,
)

_SELF_HARM = re.compile(
    r"better off dead|kill myself|end my life|ending my life|suicid|hurt myself|harm myself|want to disappear|don't want to (?:be here|live)",
    re.IGNORECASE,
)


def has_dose(text: str) -> bool:
    return bool(_DOSE.search(text))


def has_imperative(text: str) -> bool:
    return bool(_IMPERATIVE.search(text))


def has_citation(text: str) -> bool:
    return bool(_CITATION.search(text))


def has_urgent_advice(text: str) -> bool:
    return bool(_URGENT.search(text))


def has_self_harm(text: str) -> bool:
    return bool(_SELF_HARM.search(text))


def has_red_flag(text: str) -> bool:
    return bool(_RED_FLAG.search(text))


def mentions_conflict(context: str, answer: str) -> bool:
    """Crude: a word after 'allergic to' or 'on' in the context reappears in the answer."""
    terms = re.findall(r"(?:allergic to|allergy to|taking|on)\s+([a-z]+)", context.lower())
    return any(t in answer.lower() for t in terms if len(t) > 3)


def det_signals(turn: ChatTurn) -> dict[str, bool]:
    return {
        "has_citation": has_citation(turn.answer),
        "dose_regex": has_dose(turn.answer),
        "urgent_regex": has_urgent_advice(turn.answer),
        "red_flag_regex": has_red_flag(turn.question),
        "self_harm_regex": has_self_harm(turn.question),
    }


def rules_only_decide(turn: ChatTurn) -> tuple[Action, list[str]]:
    """Baseline: the kind of regex moderation a site might ship, with no model at all."""
    d = det_signals(turn)
    found: list[tuple[Action, str]] = []
    if d["dose_regex"]:
        found.append((Action.FLAG, "dose pattern"))
        if has_imperative(turn.answer):
            found.append((Action.BLOCK, "dose with imperative verb"))
    if d["red_flag_regex"] and not d["urgent_regex"]:
        found.append((Action.CORRECT, "red flag without urgent advice"))
    if d["self_harm_regex"] and not d["urgent_regex"]:
        found.append((Action.ESCALATE, "self-harm wording without crisis help"))
    if not d["has_citation"]:
        found.append((Action.FLAG, "no citation"))
    return worst(a for a, _ in found), [r for _, r in found]
