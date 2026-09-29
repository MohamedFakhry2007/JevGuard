import pytest

from jevguard import deterministic as d
from jevguard.schemas import Action, ChatTurn


@pytest.mark.parametrize("text", ["Take 500 mg twice daily.", "Give 2.5 mL now", "five hundred milligrams", "10 mcg"])
def test_dose_detected(text):
    assert d.has_dose(text)


@pytest.mark.parametrize("text", ["Ibuprofen is an NSAID.", "You have 3 options", "Take it easy"])
def test_dose_not_detected(text):
    assert not d.has_dose(text)


def test_citation_urgent_and_red_flag():
    assert d.has_citation("See [1] for details") and d.has_citation("According to the AHA")
    assert not d.has_citation("Just trust me")
    assert d.has_urgent_advice("Please call 911 now") and d.has_urgent_advice("go to the emergency department")
    assert not d.has_urgent_advice("Make an appointment next month")
    assert d.has_red_flag("I have crushing chest pain") and not d.has_red_flag("I have a mild cough")


def test_rules_only_baseline_actions():
    cited = " According to guidelines [1]."
    assert d.rules_only_decide(ChatTurn(question="q", answer="Rest and fluids." + cited))[0] is Action.PASS
    assert d.rules_only_decide(ChatTurn(question="q", answer="Take 400 mg now." + cited))[0] is Action.BLOCK
    assert d.rules_only_decide(ChatTurn(question="q", answer="Doses are 5 mg for adults." + cited))[0] is Action.FLAG
    a, _ = d.rules_only_decide(ChatTurn(question="I have chest pain", answer="Rest." + cited))
    assert a is Action.CORRECT
    assert d.rules_only_decide(ChatTurn(question="q", answer="Rest and fluids."))[0] is Action.FLAG
