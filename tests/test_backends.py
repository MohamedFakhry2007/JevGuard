import json

import pytest

from jevguard.backends import (
    BackendError,
    RecordingBackend,
    ReplayBackend,
    ReplayMiss,
    SimulatedBackend,
    request_key,
)
from jevguard.backends.live import LiveBackend
from jevguard.questions import QUESTIONS, build_request
from jevguard.schemas import ChatTurn
from jevguard.testing import ScriptedBackend, make_response

TURN = ChatTurn(question="Can I take ibuprofen?", answer="Take 400 mg every 6 hours.")


def test_request_key_ignores_dict_order():
    assert request_key({"a": 1, "b": 2}, {"q": {"x": 1, "y": 2}}) == request_key({"b": 2, "a": 1}, {"q": {"y": 2, "x": 1}})
    assert request_key({"a": 1}, {}) != request_key({"a": 2}, {})


def test_record_then_replay_roundtrip(tmp_path):
    path = tmp_path / "rec.jsonl"
    state, qs = build_request(TURN)
    live = RecordingBackend(ScriptedBackend(make_response()), path)
    first = live.ask(state, qs)
    replay = ReplayBackend(path)
    again = replay.ask(state, qs)
    assert len(replay) == 1
    assert again.answers == first.answers and again.latency_ms == first.latency_ms
    row = json.loads(path.read_text().splitlines()[0])
    assert row["request"]["state"] == state and "recorded_at" in row


def test_replay_miss_is_not_a_backend_error(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("")
    with pytest.raises(ReplayMiss) as exc:
        ReplayBackend(path).ask({"x": 1}, QUESTIONS)
    assert not isinstance(exc.value, BackendError)


def test_simulated_is_deterministic_labeled_and_complete():
    state, qs = build_request(TURN)
    a, b = SimulatedBackend().ask(state, qs), SimulatedBackend().ask(state, qs)
    assert a.answers == b.answers
    assert a.model == "simulated-not-jev" and a.endpoint == "simulated"
    assert set(a.answers) == set(QUESTIONS)


class _FakeResult:
    request_id = "req-9"

    class raw_http_response:
        @staticmethod
        def json():
            return make_response().model_dump(mode="json", exclude={"request_id", "latency_ms", "endpoint"})


class _FakeClient:
    def __init__(self, fail=None):
        self.fail, self.seen = fail, None

    def system_one(self, state, questions):
        self.seen = (state, questions)
        if self.fail:
            raise self.fail
        return _FakeResult()


def test_live_backend_wraps_sdk_result():
    client = _FakeClient()
    state, qs = build_request(TURN)
    r = LiveBackend(client=client).ask(state, qs)
    assert client.seen == (state, qs)
    assert r.request_id == "req-9" and r.latency_ms is not None


def test_live_backend_turns_any_failure_into_backend_error():
    with pytest.raises(BackendError, match="TimeoutError"):
        LiveBackend(client=_FakeClient(fail=TimeoutError("slow"))).ask({}, {})
