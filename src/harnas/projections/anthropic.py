"""Anthropic projection — Log -> Messages API request body.

Mirrors `Harnas::Projections::Anthropic`. Adjacent events by the same
role collapse into a single wire message; a group of one text block
uses the legacy plain-string form so simple bodies stay simple (and
recorded text-only fixtures match byte-for-byte).
"""

from __future__ import annotations

from typing import Any

from .. import mutations
from .. import content_blocks
from .. import capabilities as provider_capabilities
from .. import provider_carriers
from ..attachments import AttachmentStore
from ..log import Log


class Anthropic:
    DEFAULT_MAX_TOKENS = 1024

    def __init__(
        self,
        model: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        registry: Any | None = None,
        system: str | None = None,
        attachment_store: AttachmentStore | None = None,
        provider_kind: str = "anthropic",
        capabilities: dict[str, bool] | None = None,
        capability_mismatch_behavior: str = "metadata_fallback",
    ) -> None:
        self._model = model
        self._max_tokens = max_tokens
        self._registry = registry
        self._system = system
        self._attachment_store = attachment_store
        self._provider_kind = provider_kind
        self._capabilities = capabilities or {}
        self._capability_mismatch_behavior = capability_mismatch_behavior

    @property
    def provider_kind(self) -> str:
        return self._provider_kind

    def __call__(self, log: Log) -> dict[str, Any]:
        effective = mutations.apply(log)
        messages = self._group_messages(effective)

        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if self._system:
            request["system"] = self._system
        if self._registry is not None and self._registry.size > 0:
            request["tools"] = self._tool_descriptors()
        return request

    def _group_messages(self, events: list) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        for evt in events:
            translated = self._translate(evt)
            if translated is None:
                continue
            role, block = translated
            blocks = block if isinstance(block, list) else [block]
            if current and current["role"] == role:
                current["blocks"].extend(blocks)
            else:
                if current is not None:
                    groups.append(current)
                current = {"role": role, "blocks": blocks}
        if current is not None:
            groups.append(current)
        return [self._finalize(g["role"], g["blocks"]) for g in groups]

    def _finalize(self, role: str, blocks: list[dict[str, Any]]) -> dict[str, Any]:
        if len(blocks) == 1 and blocks[0].get("type") == "text":
            return {"role": role, "content": blocks[0]["text"]}
        return {"role": role, "content": blocks}

    def _translate(self, evt) -> tuple[str, dict[str, Any]] | None:
        match evt.type:
            case "user_message" | "summary":
                return ("user", self._content_blocks(evt.payload))
            case "assistant_message":
                wire = provider_carriers.wires(evt.payload.get("provider_items"), "anthropic.messages")
                if wire is not None:
                    return ("assistant", wire)
                blocks = self._reasoning_blocks(evt)
                blocks.extend(
                    block for block in self._content_blocks(evt.payload)
                    if not (block.get("type") == "text" and block.get("text", "") == "")
                )
                if not blocks:
                    return None
                return ("assistant", blocks)
            case "tool_use":
                return ("assistant", {
                    "type": "tool_use",
                    "id": evt.payload["id"],
                    "name": evt.payload["name"],
                    "input": evt.payload.get("arguments", {}),
                })
            case "tool_result":
                block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": evt.payload["tool_use_id"],
                }
                if evt.payload.get("error"):
                    block["content"] = evt.payload["error"]
                    block["is_error"] = True
                else:
                    block["content"] = evt.payload.get("output", "")
                return ("user", block)
            case _:
                return None

    def _reasoning_blocks(self, evt) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        for block in evt.payload.get("reasoning") or []:
            if block.get("type") != "text":
                continue
            wire = provider_carriers.part_wire(block, "anthropic.messages")
            if wire is not None:
                blocks.append(wire)
                continue
            out = {"type": "thinking", "thinking": block.get("text", "")}
            if block.get("signature"):
                out["signature"] = block["signature"]
            blocks.append(out)
        return blocks

    def _content_blocks(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        rendered = []
        for block in content_blocks.from_payload(payload):
            match block.get("type"):
                case "text":
                    wire = provider_carriers.part_wire(block, "anthropic.messages")
                    if wire is not None:
                        rendered.append(wire)
                        continue
                    rendered.append({"type": "text", "text": str(block.get("text", ""))})
                case "image":
                    fallback = self._fallback_if_unsupported(block)
                    if fallback is not None:
                        rendered.append(fallback)
                        continue
                    rendered.append(self._media_block("image", block))
                case "document":
                    fallback = self._fallback_if_unsupported(block)
                    if fallback is not None:
                        rendered.append(fallback)
                        continue
                    rendered.append(self._media_block("document", block))
                case _:
                    raise ValueError(f"unsupported content block type: {block.get('type')}")
        return rendered

    def _fallback_if_unsupported(self, block: dict[str, Any]) -> dict[str, Any] | None:
        block_type = str(block.get("type", ""))
        if provider_capabilities.supported(
            provider_kind=self._provider_kind,
            model=self._model,
            overrides=self._capabilities,
            block_type=block_type,
        ):
            return None
        if provider_capabilities.mismatch_behavior(self._capability_mismatch_behavior) == "error":
            raise provider_capabilities.CapabilityMismatchError(
                self._provider_kind, self._model, block_type
            )
        return provider_capabilities.fallback_block(block, self._attachment_store)

    def _media_block(self, kind: str, block: dict[str, Any]) -> dict[str, Any]:
        source = dict(block.get("source") or {})
        if kind == "image" and source.get("kind") == "url":
            return {"type": "image", "source": {"type": "url", "url": str(source.get("url", ""))}}
        resolved = content_blocks.resolve_data(block, self._attachment_store)
        return {
            "type": kind,
            "source": {
                "type": "base64",
                "media_type": resolved["media_type"],
                "data": resolved["data"],
            },
        }

    def _tool_descriptors(self) -> list[dict[str, Any]]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in self._registry.tools
        ]
