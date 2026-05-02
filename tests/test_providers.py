import json

import pytest

from harnas.providers.anthropic import AnthropicProvider
from harnas.providers.anthropic_stream import AnthropicStreamProvider
from harnas.providers.errors import HTTPError, ProviderError
from harnas.providers.gemini import GeminiProvider
from harnas.providers.openai import OpenAIProvider


class FakeResponse:
    def __init__(self, body, *, status=200):
        self.status = status
        if isinstance(body, bytes):
            self._body = body
        elif isinstance(body, str):
            self._body = body.encode("utf-8")
        else:
            self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self._body

    def getcode(self):
        return self.status

    def __iter__(self):
        return iter(self._body.splitlines(keepends=True))


def test_anthropic_provider_posts_messages_request():
    captured = {}

    def opener(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"content": [], "stop_reason": "end_turn"})

    provider = AnthropicProvider("sk-test", opener=opener)
    response = provider({"model": "claude-test", "messages": []})

    assert response["stop_reason"] == "end_turn"
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["X-api-key"] == "sk-test"
    assert captured["headers"]["Anthropic-version"] == "2023-06-01"
    assert captured["body"] == {"model": "claude-test", "messages": []}


def test_openai_provider_posts_chat_completions_request():
    captured = {}

    def opener(request, timeout=None):
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"choices": [{"message": {}, "finish_reason": "stop"}]})

    OpenAIProvider("sk-openai", opener=opener)({"model": "gpt-test", "messages": []})

    assert captured["headers"]["Authorization"] == "Bearer sk-openai"
    assert captured["body"]["model"] == "gpt-test"


def test_gemini_provider_moves_model_to_endpoint():
    captured = {}

    def opener(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"candidates": []})

    GeminiProvider("sk-gemini", opener=opener)({
        "model": "gemini-test",
        "contents": [{"parts": [{"text": "hi"}]}],
    })

    assert captured["url"].endswith("/gemini-test:generateContent")
    assert captured["headers"]["X-goog-api-key"] == "sk-gemini"
    assert "model" not in captured["body"]


def test_provider_http_error_includes_status_and_body():
    def opener(_request, timeout=None):
        return FakeResponse('{"error":{"message":"bad"}}', status=400)

    with pytest.raises(HTTPError) as exc:
        OpenAIProvider("sk-openai", opener=opener)({"model": "gpt-test"})

    assert exc.value.status == 400
    assert exc.value.body == {"error": {"message": "bad"}}


def test_invalid_json_response_raises_provider_error():
    def opener(_request, timeout=None):
        return FakeResponse("not-json")

    with pytest.raises(ProviderError, match="invalid JSON response"):
        AnthropicProvider("sk-test", opener=opener)({"model": "claude-test"})


def test_anthropic_stream_accepts_crlf_sse_and_emits_canonical_events():
    stream = "\r\n\r\n".join([
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hel"}}',
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}',
        'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"input_tokens":1,"output_tokens":2}}',
        "data: [DONE]",
        "",
    ])

    def opener(request, timeout=None):
        body = json.loads(request.data.decode("utf-8"))
        assert body["stream"] is True
        return FakeResponse(stream)

    events = []
    AnthropicStreamProvider("sk-test", opener=opener)({"model": "claude-test"}, events.append)

    assert [event["type"] for event in events] == [
        "assistant_turn_started",
        "assistant_text_delta",
        "assistant_text_delta",
        "assistant_turn_completed",
        "assistant_message",
    ]
    assert events[-1]["payload"] == {
        "text": "hello",
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 2},
    }
