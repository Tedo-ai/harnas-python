"""Capability manifest references for subagent spawn events."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def capability_manifest_ref(manifest: Any) -> str:
    encoded = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "cap_sha256_" + hashlib.sha256(encoded).hexdigest()


class MemoryCapabilityManifestStore:
    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def put(self, manifest: Any) -> str:
        manifest_ref = capability_manifest_ref(manifest)
        self._items[manifest_ref] = manifest
        return manifest_ref

    def get(self, manifest_ref: str) -> Any | None:
        return self._items.get(manifest_ref)
