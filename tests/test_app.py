from pathlib import Path

import pytest

from jevguard import ui_model as ui
from jevguard.schemas import Action, ChatTurn

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app" / "streamlit_app.py")
needs_rec = pytest.mark.skipif(not ui.RECORDING.exists(), reason="dev recording not present")


@needs_rec
def test_only_dev_examples_with_a_recording_are_offered():
    ex = ui.recorded_examples()
    assert ex and all(e.split == "dev" for e in ex)
    assert not any(e.id.startswith("s04") for e in ex)  # s04 is in the sealed test split


@needs_rec
def test_recorded_mode_gives_the_same_decision_as_the_engine_for_a_saved_example():
    e = next(i for i in ui.recorded_examples() if i.id == "s28-contraindication")
    v = ui.run(e.to_turn(), "recorded", next(iter(ui.POLICIES)))
    assert v.decision.action is Action.BLOCK and v.rows[0].id == "contraindication_conflict"
    assert v.keyword_action in Action and v.warning is None
    strict = ui.run(e.to_turn(), "recorded", next(k for k in ui.POLICIES if k.startswith("Starting")))
    assert strict.decision.action is Action.ESCALATE  # Jev is 40% sure: the unsure band holds it


@needs_rec
def test_recorded_mode_refuses_text_that_was_never_sent_to_jev():
    with pytest.raises(ui.NoRecording):
        ui.run(ChatTurn(question="made up", answer="made up"), "recorded", next(iter(ui.POLICIES)))


def test_simulated_mode_is_stamped_and_works_on_any_text():
    v = ui.run(ChatTurn(question="Can I take ibuprofen?", answer="Take 400 mg now."), "simulated", next(iter(ui.POLICIES)))
    assert v.warning and "SIMULATED" in v.warning and v.decision.jev_model == "simulated-not-jev"


def test_live_mode_is_unavailable_without_a_key(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert not ui.live_available()
    with pytest.raises(ValueError):
        ui.run(ChatTurn(question="q", answer="a"), "live", next(iter(ui.POLICIES)))


@needs_rec
def test_app_opens_on_an_example_and_shows_a_decision_without_errors():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("block" in m.value for m in at.markdown) or any("escalate" in m.value for m in at.markdown)
    assert at.selectbox(key="example").value == "s23-rx_discourage"


@needs_rec
def test_app_edited_text_in_recorded_mode_explains_there_is_no_recording():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_area(key="ans").set_value("Something new that Jev never saw.").run()
    assert not at.exception and any("never sent to Jev" in e.value for e in at.error)


def test_app_simulated_mode_shows_the_warning_banner():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.radio(key="mode").set_value("simulated").run()
    at.text_area(key="q").set_value("I have crushing chest pain.").run()
    at.text_area(key="ans").set_value("Rest at home.").run()
    assert not at.exception and any("SIMULATED" in w.value for w in at.warning)


def test_reasons_are_shown_in_plain_words():
    from jevguard.engine import JevGuard
    from jevguard.testing import ScriptedBackend, make_response
    d = JevGuard(ScriptedBackend(make_response({"contraindication_conflict": 0.9}))).check(ChatTurn(question="q", answer="a"))
    text = " ".join(ui.plain_reasons(d))
    assert "conflicts with patient context" in text and "contraindication_conflict" not in text
