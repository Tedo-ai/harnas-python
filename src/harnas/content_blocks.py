"""Content block normalization and attachment source resolution."""

from __future__ import annotations

import base64
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .attachments import AttachmentStore


def from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "content" in payload:
        return [dict(block) for block in payload.get("content") or [] if isinstance(block, dict)]
    if "text" in payload:
        return [{"type": "text", "text": payload.get("text", "")}]
    return []


def resolve_data(block: dict[str, Any], store: AttachmentStore | None) -> dict[str, Any]:
    source = dict(block.get("source") or {})
    media_type = block.get("media_type")
    kind = source.get("kind")
    if kind == "base64":
        data = str(source.get("data", ""))
        return {
            "data": data,
            "media_type": media_type,
            "byte_size": len(base64.b64decode(data or b"", validate=False)),
        }
    if kind == "ref":
        uri = str(source.get("uri", ""))
        if store is None:
            raise ValueError(f"attachment store required to resolve {uri}")
        data, resolved_media_type = store.get(uri)
        return {
            "data": base64.b64encode(data).decode("ascii"),
            "media_type": media_type or resolved_media_type,
            "byte_size": len(data),
            "uri": uri,
        }
    if kind == "url":
        data, resolved_media_type = fetch_url(str(source.get("url", "")))
        return {
            "data": base64.b64encode(data).decode("ascii"),
            "media_type": media_type or resolved_media_type,
            "byte_size": len(data),
        }
    raise ValueError(f"unsupported content source kind: {kind}")


def fetch_url(url: str) -> tuple[bytes, str]:
    if not url:
        raise ValueError("content source url is required")
    try:
        with urlopen(Request(url), timeout=30) as response:  # noqa: S310 - explicit user content URL.
            return response.read(), response.headers.get("Content-Type", "")
    except HTTPError as exc:
        raise ValueError(f"fetch attachment url {url}: status {exc.code}") from exc
    except URLError as exc:
        raise ValueError(f"fetch attachment url {url}: {exc.reason}") from exc
