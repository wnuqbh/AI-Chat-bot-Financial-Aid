"""Retry and error-message behaviour of the Gemini wrapper, using a fake Gemini client."""

from types import SimpleNamespace

import pytest
from google.genai import errors

from app.services import advisor
from app.services.advisor import AdvisorUnavailableError, generate_reply, stream_reply


def gemini_error(code):
    cls = errors.ClientError if code < 500 else errors.ServerError
    return cls(code, {"error": {"code": code, "message": "boom", "status": "X"}})


class FakeModels:
    """Each call takes the next scripted outcome: an exception to raise, or a list of chunk texts
    (which may itself contain an exception, raised mid-stream)."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def _next(self):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def generate_content(self, **_):
        return SimpleNamespace(text="".join(self._next()), candidates=[])

    def generate_content_stream(self, **_):
        for item in self._next():
            if isinstance(item, Exception):
                raise item
            yield SimpleNamespace(text=item, candidates=[])


@pytest.fixture
def fake_gemini(monkeypatch):
    def install(*outcomes):
        models = FakeModels(*outcomes)
        monkeypatch.setattr(advisor, "_get_client", lambda: SimpleNamespace(models=models))
        return models

    return install


def _request():
    return advisor.build_request([SimpleNamespace(role="user", content="hi")], None)


def test_overloaded_then_rate_limited_then_success(app, fake_gemini):
    models = fake_gemini(gemini_error(503), gemini_error(429), ["All good"])
    assert generate_reply([SimpleNamespace(role="user", content="hi")]) == "All good"
    assert models.calls == 3


def test_gives_up_with_a_friendly_message(app, fake_gemini):
    fake_gemini(gemini_error(429), gemini_error(429), gemini_error(429))
    with pytest.raises(AdvisorUnavailableError, match="too many requests"):
        generate_reply([SimpleNamespace(role="user", content="hi")])


def test_non_retryable_errors_fail_immediately(app, fake_gemini):
    models = fake_gemini(gemini_error(400))
    with pytest.raises(AdvisorUnavailableError, match="service is unavailable"):
        generate_reply([SimpleNamespace(role="user", content="hi")])
    assert models.calls == 1


def test_stream_retries_before_any_text(app, fake_gemini):
    models = fake_gemini(gemini_error(503), ["Hello ", "there"])
    assert list(stream_reply(_request())) == ["Hello ", "there"]
    assert models.calls == 2


def test_stream_does_not_retry_after_text_was_sent(app, fake_gemini):
    models = fake_gemini(["Hello ", gemini_error(503)], ["never used"])
    received = []
    with pytest.raises(AdvisorUnavailableError, match="temporarily overloaded"):
        for text in stream_reply(_request()):
            received.append(text)
    assert received == ["Hello "]
    assert models.calls == 1
