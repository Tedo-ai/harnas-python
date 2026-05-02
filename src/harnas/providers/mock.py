"""Small mock provider used by manifests and CLI tests."""

from __future__ import annotations

from typing import Any


class MockProvider:
    def __init__(self, text: str = "ok") -> None:
        self.text = text

    def __call__(self, _request: dict[str, Any]) -> dict[str, Any]:
        return {
            "content": [{"type": "text", "text": self.text}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
