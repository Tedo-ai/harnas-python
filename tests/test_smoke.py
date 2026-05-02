import pytest

from harnas import smoke


def test_smoke_request_shapes():
    assert smoke.request_for("anthropic", "claude-test", "hi") == {
        "model": "claude-test",
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": "hi"}],
    }
    assert smoke.request_for("openai", "gpt-test", "hi") == {
        "model": "gpt-test",
        "messages": [{"role": "user", "content": "hi"}],
    }
    assert smoke.request_for("gemini", "gemini-test", "hi")["contents"][0]["parts"][0]["text"] == "hi"


def test_smoke_requires_api_key(monkeypatch, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert smoke.main(["--provider", "anthropic", "hello"]) == 1

    assert "ANTHROPIC_API_KEY is not set" in capsys.readouterr().err


def test_smoke_rejects_mutually_exclusive_modes(monkeypatch, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    assert smoke.main([
        "--provider",
        "openai",
        "--stream-only",
        "--buffered-only",
        "hello",
    ]) == 1

    assert "mutually exclusive" in capsys.readouterr().err


def test_smoke_require_text_exits_on_blank(capsys):
    with pytest.raises(SystemExit):
        smoke.require_text("buffered", "")

    assert "buffered response contained no text" in capsys.readouterr().err
