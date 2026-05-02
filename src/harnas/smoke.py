"""Live provider smoke-test CLI."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from .providers.anthropic import AnthropicProvider
from .providers.anthropic_stream import AnthropicStreamProvider
from .providers.gemini import GeminiProvider
from .providers.gemini_stream import GeminiStreamProvider
from .providers.openai import OpenAIProvider
from .providers.openai_stream import OpenAIStreamProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="smoke")
    parser.add_argument("--provider", required=True, choices=["anthropic", "openai", "gemini"])
    parser.add_argument("--model")
    parser.add_argument("--stream-only", action="store_true")
    parser.add_argument("--buffered-only", action="store_true")
    parser.add_argument("prompt", nargs="+")
    args = parser.parse_args(argv)

    if args.stream_only and args.buffered_only:
        print("error: --stream-only and --buffered-only are mutually exclusive", file=sys.stderr)
        return 1

    provider = args.provider
    prompt = " ".join(args.prompt)
    model = resolve_model(provider, args.model)
    api_key = os.environ.get(f"{provider.upper()}_API_KEY")
    if not api_key:
        print(f"error: {provider.upper()}_API_KEY is not set", file=sys.stderr)
        return 1
    request = request_for(provider, model, prompt)

    if not args.stream_only:
        text = call_buffered(provider, api_key, request)
        require_text("buffered", text)
        print(f"[buffered] {text}")
    if not args.buffered_only:
        text = call_streaming(provider, api_key, request)
        require_text("streaming", text)
        print(f"[streaming] {text}")
    return 0


def resolve_model(provider: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get(f"{provider.upper()}_MODEL")
    if env:
        return env
    return {
        "anthropic": "claude-sonnet-4-5",
        "openai": "gpt-5.4-mini",
        "gemini": "gemini-flash-latest",
    }[provider]


def request_for(provider: str, model: str, prompt: str) -> dict[str, Any]:
    if provider == "openai":
        return {"model": model, "messages": [{"role": "user", "content": prompt}]}
    if provider == "gemini":
        return {
            "model": model,
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
        }
    return {
        "model": model,
        "max_tokens": 1024,
        "messages": [{"role": "user", "content": prompt}],
    }


def call_buffered(provider: str, api_key: str, request: dict[str, Any]) -> str:
    if provider == "anthropic":
        response = AnthropicProvider(api_key)(request)
        return _string(_first(response.get("content")).get("text"))
    if provider == "openai":
        response = OpenAIProvider(api_key)(request)
        return _string(_first(response.get("choices")).get("message", {}).get("content"))
    response = GeminiProvider(api_key)(request)
    candidate = _first(response.get("candidates"))
    return _string(_first(candidate.get("content", {}).get("parts")).get("text"))


def call_streaming(provider: str, api_key: str, request: dict[str, Any]) -> str:
    final = ""

    def emit(event: dict[str, Any]) -> None:
        nonlocal final
        if event["type"] == "assistant_message":
            final = _string(event["payload"].get("text"))

    if provider == "anthropic":
        AnthropicStreamProvider(api_key)(request, emit)
    elif provider == "openai":
        OpenAIStreamProvider(api_key)(request, emit)
    else:
        GeminiStreamProvider(api_key)(request, emit)
    return final


def require_text(mode: str, text: str) -> None:
    if text.strip():
        return
    print(f"error: {mode} response contained no text", file=sys.stderr)
    raise SystemExit(1)


def _first(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0]
    return {}


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


if __name__ == "__main__":
    raise SystemExit(main())
