"""Raw provider-wire conformance through the production streaming parsers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..providers.anthropic_stream import AnthropicStreamProvider
from ..providers.errors import HTTPError, ProviderProtocolError, ProviderStreamError
from ..providers.gemini_stream import GeminiStreamProvider
from ..providers.openai_stream import OpenAIStreamProvider

SCHEMA_VERSION = "harnas.provider-streams.v1"


@dataclass(frozen=True)
class ProviderStreamReport:
    cases: int
    profiles: int


def run_provider_stream_corpus(spec_root: str | os.PathLike[str]) -> ProviderStreamReport:
    path = Path(spec_root) / "conformance" / "provider-streams" / "corpus.json"
    corpus = json.loads(path.read_text(encoding="utf-8"))
    if corpus.get("schema_version") != SCHEMA_VERSION:
        raise AssertionError(f"unsupported provider-stream schema {corpus.get('schema_version')!r}")
    profiles = corpus.get("chunking_profiles")
    cases = corpus.get("cases")
    if not isinstance(profiles, dict) or not isinstance(cases, list):
        raise AssertionError("provider-stream corpus has invalid top-level shape")
    executions = 0
    for case in cases:
        for profile_name in case["chunking_profiles"]:
            profile = profiles.get(profile_name)
            if not isinstance(profile, dict):
                raise AssertionError(f"{case['id']}: unknown chunking profile {profile_name!r}")
            executions += 1
            try:
                _run_case(case, profile)
            except Exception as error:
                raise AssertionError(f"{case['id']}/{profile_name}: {error}") from error
    return ProviderStreamReport(cases=len(cases), profiles=executions)


def _run_case(case: dict[str, Any], profile: dict[str, Any]) -> None:
    response = case["response"]
    chunks = _split_bytes(response["body"].encode("utf-8"), profile)

    def opener(_request: Any, timeout: float | None = None) -> _FixtureResponse:
        del timeout
        return _FixtureResponse(response["status"], response["headers"], chunks)

    events: list[dict[str, Any]] = []
    provider_kind = case["provider"]
    if provider_kind == "anthropic":
        provider = AnthropicStreamProvider(
            "conformance-key", endpoint="https://provider.invalid/anthropic", opener=opener
        )
    elif provider_kind == "openai":
        provider = OpenAIStreamProvider(
            "conformance-key", endpoint="https://provider.invalid/openai", opener=opener
        )
    elif provider_kind == "gemini":
        provider = GeminiStreamProvider(
            "conformance-key", endpoint_base="https://provider.invalid/gemini", opener=opener
        )
    else:
        raise AssertionError(f"unsupported provider {provider_kind!r}")

    caught: Exception | None = None
    try:
        provider(case["request"], events.append)
    except Exception as error:  # the fixture asserts the exact normalized class below
        caught = error

    actual_events = _normalize_events(events)
    expected = case["expected"]
    if actual_events != expected["events"]:
        raise AssertionError(
            "event artifact mismatch\n"
            f"expected: {json.dumps(expected['events'], sort_keys=True)}\n"
            f"actual:   {json.dumps(actual_events, sort_keys=True)}"
        )
    if expected["outcome"] == "success":
        if caught is not None:
            raise AssertionError(f"expected success, got {type(caught).__name__}: {caught}")
    elif expected["outcome"] == "failure":
        if caught is None:
            raise AssertionError("expected failure, got success")
        failure = _normalize_failure(provider_kind, caught)
        if failure != expected["failure"]:
            raise AssertionError(f"failure artifact mismatch: expected {expected['failure']!r}, got {failure!r}")
        forbidden = {"assistant_turn_completed", "assistant_message", "tool_use"}
        leaked = [event["type"] for event in actual_events if event["type"] in forbidden]
        if leaked:
            raise AssertionError(f"failed stream produced durable/completed events: {leaked!r}")
    else:
        raise AssertionError(f"unsupported expected outcome {expected['outcome']!r}")


class _FixtureResponse:
    def __init__(self, status: int, headers: dict[str, str], chunks: list[bytes]) -> None:
        self.status = status
        self.headers = headers
        self._chunks = list(chunks)
        self._offset = 0

    def __enter__(self) -> "_FixtureResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def getcode(self) -> int:
        return self.status

    def read1(self, size: int = -1) -> bytes:
        if not self._chunks:
            return b""
        chunk = self._chunks[0]
        if size >= 0 and len(chunk) > size:
            self._chunks[0] = chunk[size:]
            return chunk[:size]
        self._chunks.pop(0)
        return chunk

    def read(self, size: int = -1) -> bytes:
        if size is not None and size >= 0:
            return self.read1(size)
        body = b"".join(self._chunks)
        self._chunks.clear()
        return body


def _split_bytes(body: bytes, profile: dict[str, Any]) -> list[bytes]:
    sizes = profile.get("sizes")
    repeat = profile.get("repeat")
    if not isinstance(sizes, list) or not isinstance(repeat, bool):
        raise AssertionError("invalid chunking profile")
    if not sizes:
        return [body]
    chunks: list[bytes] = []
    offset = 0
    size_index = 0
    while offset < len(body):
        if size_index >= len(sizes):
            if not repeat:
                chunks.append(body[offset:])
                break
            size_index = 0
        size = sizes[size_index]
        size_index += 1
        if not isinstance(size, int) or size < 1:
            raise AssertionError(f"invalid chunk size {size!r}")
        chunks.append(body[offset:offset + size])
        offset += size
    return chunks or [b""]


def _normalize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = json.loads(json.dumps(events))
    for event in normalized:
        payload = event["payload"]
        if "turn_id" in payload:
            payload["turn_id"] = "<turn_id>"
        if event["type"] == "assistant_turn_failed":
            payload["error"] = "<provider_failure>"
    return normalized


def _normalize_failure(provider: str, error: Exception) -> dict[str, Any]:
    if isinstance(error, ProviderStreamError):
        return {
            "kind": "provider_stream_error",
            "provider": provider,
            "reason": "provider_error_frame",
            "provider_error_type": error.error_type,
            "request_id": error.request_id,
            "status": error.status,
        }
    if isinstance(error, ProviderProtocolError):
        return {
            "kind": "provider_protocol_error",
            "provider": provider,
            "reason": error.reason,
        }
    if isinstance(error, HTTPError):
        return {
            "kind": "http_error",
            "provider": provider,
            "reason": "http_status",
            "status": error.status,
        }
    return {
        "kind": "network_error",
        "provider": provider,
        "reason": "transport",
    }
