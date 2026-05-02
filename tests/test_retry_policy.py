from harnas.agent_loop import AgentLoop
from harnas.providers.errors import HTTPError, ProviderError
from harnas.providers.retry_policy import RetryPolicy
from harnas.session import Session


class AnthropicFlakyProvider:
    def __init__(self):
        self.calls = 0

    def __call__(self, _request):
        self.calls += 1
        if self.calls == 1:
            raise HTTPError(503, {"error": "busy"})
        return {
            "content": [{"type": "text", "text": "ok"}],
            "stop_reason": "end_turn",
            "usage": {},
        }


class FatalProvider:
    def __call__(self, _request):
        raise HTTPError(400, {"error": "bad"})


def projection(_log):
    return {"model": "test", "messages": []}


def ingestor(_response):
    return [{
        "type": "assistant_message",
        "payload": {"text": "ok", "stop_reason": "end_turn", "usage": {}},
    }]


def test_retry_policy_retries_transient_http_before_success():
    session = Session.create()
    provider = AnthropicFlakyProvider()

    AgentLoop(
        session=session,
        projection=projection,
        provider=provider,
        ingestor=ingestor,
        retry_policy=RetryPolicy(backoff_ms=lambda _attempt: 0),
    ).run()

    assert provider.calls == 2
    assert [(e.type, e.payload.get("terminal")) for e in session.log] == [
        ("provider_error", False),
        ("assistant_message", None),
    ]
    assert session.log[0].payload["provider"] == "anthropic"
    assert session.log[0].payload["attempt"] == 1


def test_retry_policy_aborts_permanent_http():
    session = Session.create()

    reason = AgentLoop(
        session=session,
        projection=projection,
        provider=FatalProvider(),
        ingestor=ingestor,
        retry_policy=RetryPolicy(backoff_ms=lambda _attempt: 0),
    ).run()

    assert reason == "provider_failed"
    assert len(session.log) == 1
    assert session.log[0].type == "provider_error"
    assert session.log[0].payload["terminal"] is True
    assert session.log[0].payload["status"] == 400


def test_retry_policy_classifies_network_style_errors():
    policy = RetryPolicy(backoff_ms=lambda _attempt: 0)

    assert policy.decide(TimeoutError("timed out"), 1).retry is True
    assert policy.decide(ProviderError("connection reset by peer"), 1).retry is True
    assert policy.decide(HTTPError(400, "bad"), 1).retry is False
    assert policy.decide(HTTPError(503, "bad"), 3).retry is False
