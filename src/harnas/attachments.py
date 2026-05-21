"""AttachmentStore helpers for multimodal content blocks."""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class AttachmentReference:
    uri: str | None
    media_type: str
    byte_size: int
    sha256: str
    source: dict[str, Any]


class AttachmentStore(Protocol):
    def put(self, data: bytes, media_type: str) -> AttachmentReference: ...
    def get(self, uri: str) -> tuple[bytes, str]: ...
    def delete(self, uri: str) -> None: ...
    def exists(self, uri: str) -> bool: ...
    def list_referenced(self, log) -> list[str]: ...


class FilesystemStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(self, data: bytes, media_type: str) -> AttachmentReference:
        digest = _sha256(data)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / f"{digest}{_extension(media_type)}").write_bytes(data)
        return _ref(digest, media_type, len(data), digest)

    def get(self, uri: str) -> tuple[bytes, str]:
        path = self._path_for(uri)
        return path.read_bytes(), _media_type_for_ext(path.suffix)

    def delete(self, uri: str) -> None:
        attachment_id = _attachment_id(uri)
        for path in self.root.glob(f"{attachment_id}.*"):
            path.unlink(missing_ok=True)

    def exists(self, uri: str) -> bool:
        try:
            attachment_id = _attachment_id(uri)
        except ValueError:
            return False
        return any(self.root.glob(f"{attachment_id}.*"))

    def list_referenced(self, log) -> list[str]:
        return list_referenced(log)

    def _path_for(self, uri: str) -> Path:
        attachment_id = _attachment_id(uri)
        match = next(self.root.glob(f"{attachment_id}.*"), None)
        if match is None:
            raise FileNotFoundError(uri)
        return match


class MemoryStore:
    def __init__(self) -> None:
        self._items: dict[str, tuple[bytes, str, str]] = {}

    def put(self, data: bytes, media_type: str) -> AttachmentReference:
        digest = _sha256(data)
        uri = f"attachment://{digest}"
        self._items[uri] = (bytes(data), media_type, digest)
        return _ref(digest, media_type, len(data), digest)

    def get(self, uri: str) -> tuple[bytes, str]:
        data, media_type, _digest = self._items[uri]
        return bytes(data), media_type

    def delete(self, uri: str) -> None:
        self._items.pop(uri, None)

    def exists(self, uri: str) -> bool:
        return uri in self._items

    def list_referenced(self, log) -> list[str]:
        return list_referenced(log)


class InlineStore:
    def put(self, data: bytes, media_type: str) -> AttachmentReference:
        return AttachmentReference(
            uri=None,
            media_type=media_type,
            byte_size=len(data),
            sha256=_sha256(data),
            source={
                "kind": "base64",
                "data": base64.b64encode(data).decode("ascii"),
            },
        )

    def get(self, uri: str) -> tuple[bytes, str]:
        raise RuntimeError("InlineStore does not resolve attachment:// refs")

    def delete(self, uri: str) -> None:
        return None

    def exists(self, uri: str) -> bool:
        return False

    def list_referenced(self, log) -> list[str]:
        return list_referenced(log)


def list_referenced(log) -> list[str]:
    seen: set[str] = set()
    refs: list[str] = []
    for event in log:
        if event.type not in {"user_message", "assistant_message"}:
            continue
        for block in event.payload.get("content") or []:
            if not isinstance(block, dict):
                continue
            source = block.get("source")
            if not isinstance(source, dict) or source.get("kind") != "ref":
                continue
            uri = source.get("uri")
            if uri and uri not in seen:
                seen.add(uri)
                refs.append(uri)
    return refs


def _ref(
    attachment_id: str,
    media_type: str,
    byte_size: int,
    digest: str,
) -> AttachmentReference:
    uri = f"attachment://{attachment_id}"
    return AttachmentReference(
        uri=uri,
        media_type=media_type,
        byte_size=byte_size,
        sha256=digest,
        source={"kind": "ref", "uri": uri},
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _attachment_id(uri: str) -> str:
    prefix = "attachment://"
    if not uri.startswith(prefix):
        raise ValueError(f"invalid attachment uri: {uri}")
    attachment_id = uri[len(prefix):]
    if not attachment_id or "/" in attachment_id:
        raise ValueError(f"invalid attachment uri: {uri}")
    return attachment_id


def _extension(media_type: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }.get(media_type, ".bin")


def _media_type_for_ext(ext: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }.get(ext, "application/octet-stream")
