"""Gemini projection — Log -> generateContent request body.

Mirrors `Harnas::Projections::Gemini`. functionCall parts on a
"model"-role entry; functionResponse parts on a "user"-role entry.
Looks up the matching :tool_use's name to populate functionResponse.
Reattaches thoughtSignature from the :annotation event that follows
each :tool_use.
"""

from __future__ import annotations

from typing import Any

from .. import mutations
from .. import content_blocks
from .. import capabilities as provider_capabilities
from ..attachments import AttachmentStore
from ..log import Log

THOUGHT_SIGNATURE_KIND = "gemini.thought_signature"


class Gemini:
    def __init__(
        self,
        model: str,
        registry: Any | None = None,
        system: str | None = None,
        thinking_budget: int | None = 0,
        attachment_store: AttachmentStore | None = None,
        provider_kind: str = "gemini",
        capabilities: dict[str, bool] | None = None,
        capability_mismatch_behavior: str = "metadata_fallback",
    ) -> None:
        self._model = model
        self._registry = registry
        self._system = system
        self._thinking_budget = thinking_budget
        self._attachment_store = attachment_store
        self._provider_kind = provider_kind
        self._capabilities = capabilities or {}
        self._capability_mismatch_behavior = capability_mismatch_behavior

    @property
    def provider_kind(self) -> str:
        return self._provider_kind

    def __call__(self, log: Log) -> dict[str, Any]:
        effective = mutations.apply(log)
        contents = self._build_contents(effective)

        request: dict[str, Any] = {"model": self._model, "contents": contents}
        if self._system:
            request["systemInstruction"] = {"parts": [{"text": self._system}]}
        if self._registry is not None and self._registry.size > 0:
            request["tools"] = self._tool_descriptors()
        if self._thinking_budget is not None:
            request["generationConfig"] = {
                "thinkingConfig": {"thinkingBudget": self._thinking_budget}
            }
        return request

    def _build_contents(self, events: list) -> list[dict[str, Any]]:
        self._tool_use_names = {
            e.payload["id"]: e.payload["name"]
            for e in events if e.type == "tool_use"
        }
        contents: list[dict[str, Any]] = []
        for idx, evt in enumerate(events):
            next_evt = events[idx + 1] if idx + 1 < len(events) else None
            self._append_event(contents, evt, next_evt)
        return contents

    def _append_event(self, contents: list[dict[str, Any]], evt, next_evt) -> None:
        match evt.type:
            case "user_message" | "summary":
                contents.append({"role": "user", "parts": self._parts(evt.payload)})
            case "assistant_message":
                parts = self._parts(evt.payload)
                if parts:
                    contents.append({"role": "model", "parts": parts})
            case "tool_use":
                self._append_function_call(contents, evt, self._signature_from(next_evt))
            case "tool_result":
                self._append_function_response(contents, evt)

    def _signature_from(self, event) -> str | None:
        if event is None or event.type != "annotation":
            return None
        if event.payload.get("kind") != THOUGHT_SIGNATURE_KIND:
            return None
        return event.payload.get("data", {}).get("signature")

    def _append_function_call(
        self, contents: list[dict[str, Any]], evt, signature: str | None
    ) -> None:
        part: dict[str, Any] = {
            "functionCall": {
                "name": evt.payload["name"],
                "args": evt.payload.get("arguments") or {},
            }
        }
        if signature:
            part["thoughtSignature"] = signature

        prev = contents[-1] if contents else None
        if prev and prev.get("role") == "model":
            prev["parts"].append(part)
        else:
            contents.append({"role": "model", "parts": [part]})

    def _parts(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        parts = []
        for block in content_blocks.from_payload(payload):
            match block.get("type"):
                case "text":
                    text = str(block.get("text", ""))
                    if text:
                        parts.append({"text": text})
                case "image" | "document":
                    fallback = self._fallback_if_unsupported(block)
                    if fallback is not None:
                        parts.append({"text": fallback["text"]})
                        continue
                    resolved = content_blocks.resolve_data(block, self._attachment_store)
                    parts.append({
                        "inline_data": {
                            "mime_type": resolved["media_type"],
                            "data": resolved["data"],
                        }
                    })
                case _:
                    raise ValueError(f"unsupported Gemini content block type: {block.get('type')}")
        return parts

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

    def _append_function_response(self, contents: list[dict[str, Any]], evt) -> None:
        if evt.payload.get("error"):
            response = {"error": evt.payload["error"]}
        else:
            response = {"content": str(evt.payload.get("output", ""))}

        tool_use_id = evt.payload["tool_use_id"]
        wire_name = self._tool_use_names.get(tool_use_id, tool_use_id)

        contents.append({
            "role": "user",
            "parts": [{
                "functionResponse": {
                    "name": wire_name,
                    "response": response,
                }
            }],
        })

    def _tool_descriptors(self) -> list[dict[str, Any]]:
        return [{
            "functionDeclarations": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                }
                for t in self._registry.tools
            ]
        }]
