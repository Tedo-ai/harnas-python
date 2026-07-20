"""Small HTTP helpers shared by live providers."""

from __future__ import annotations

import json
import codecs
import re
import urllib.error
import urllib.request
from typing import Any, Callable, Iterable

from .errors import HTTPError, ProviderError


def post_json(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    *,
    timeout: float | None = 60,
    opener: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, method="POST")
    for key, value in headers.items():
        request.add_header(key, value)

    try:
        response = (opener or urllib.request.urlopen)(request, timeout=timeout)
        with response:
            parsed = _parse_json(response.read())
            status = getattr(response, "status", response.getcode())
    except urllib.error.HTTPError as error:
        raise HTTPError(error.code, _parse_error_body(error.read())) from error
    except urllib.error.URLError as error:
        raise ProviderError(str(error.reason)) from error

    if status < 200 or status >= 300:
        raise HTTPError(status, parsed)
    return parsed


def stream_sse(
    endpoint: str,
    headers: dict[str, str],
    body: dict[str, Any],
    on_data: Callable[[str], None],
    *,
    timeout: float | None = 60,
    opener: Callable[..., Any] | None = None,
) -> None:
    data = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=data, method="POST")
    for key, value in headers.items():
        request.add_header(key, value)

    try:
        response = (opener or urllib.request.urlopen)(request, timeout=timeout)
        with response:
            status = getattr(response, "status", response.getcode())
            if status < 200 or status >= 300:
                raise HTTPError(status, _parse_error_body(response.read()))
            _read_sse_lines(response, on_data)
    except urllib.error.HTTPError as error:
        raise HTTPError(error.code, _parse_error_body(error.read())) from error
    except urllib.error.URLError as error:
        raise ProviderError(str(error.reason)) from error


def _read_sse_lines(response: Any, on_data: Callable[[str], None]) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")(errors="strict")
    buffer = ""
    read_chunk = getattr(response, "read1", None)
    if not callable(read_chunk):
        read_chunk = response.read
    while True:
        raw = read_chunk(8192)
        if not raw:
            break
        try:
            buffer += decoder.decode(raw, final=False)
        except UnicodeDecodeError as error:
            raise ProviderError(f"invalid UTF-8 provider stream: {error}") from error
        while True:
            match = re.search(r"\r?\n\r?\n", buffer)
            if match is None:
                break
            _dispatch_block(buffer[:match.start()].splitlines(), on_data)
            buffer = buffer[match.end():]
    try:
        buffer += decoder.decode(b"", final=True)
    except UnicodeDecodeError as error:
        raise ProviderError(f"invalid UTF-8 provider stream: {error}") from error
    if buffer:
        _dispatch_block(buffer.splitlines(), on_data)


def _dispatch_block(lines: Iterable[str], on_data: Callable[[str], None]) -> None:
    data_lines: list[str] = []
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line.removeprefix("data:")
        if data.startswith(" "):
            data = data[1:]
        data_lines.append(data)
    if data_lines:
        data = "\n".join(data_lines)
        if data:
            on_data(data)


def _parse_json(raw: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as error:
        raise ProviderError(f"invalid JSON response: {error}") from error
    if not isinstance(parsed, dict):
        raise ProviderError("invalid JSON response: top-level value is not an object")
    return parsed


def _parse_error_body(raw: bytes) -> object:
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return raw.decode("utf-8", errors="replace")
