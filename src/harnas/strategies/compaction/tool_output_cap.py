"""ToolOutputCap compaction strategy."""

from __future__ import annotations

from ... import hooks as global_hooks
from ...actions import compact as compact_action
from ... import mutations


class ToolOutputCap:
    DEFAULT_SUMMARY_FORMAT = (
        "[tool `$TOOL` output capped at $CAP bytes "
        "(original $ORIGINAL bytes)]\n$PREFIX"
    )

    @classmethod
    def install(
        cls,
        session=None,
        max_bytes: int = 4096,
        prefix_bytes: int = 1024,
        summary_format: str = DEFAULT_SUMMARY_FORMAT,
    ):
        instance = cls(
            max_bytes=max_bytes,
            prefix_bytes=prefix_bytes,
            summary_format=summary_format,
        )
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_projection", instance.on_pre_projection)
        return instance.on_pre_projection

    def __init__(self, max_bytes: int, prefix_bytes: int, summary_format: str) -> None:
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive int")
        if (
            not isinstance(prefix_bytes, int)
            or prefix_bytes < 0
            or prefix_bytes > max_bytes
        ):
            raise ValueError("prefix_bytes must be between 0 and max_bytes")
        self._max_bytes = max_bytes
        self._prefix_bytes = prefix_bytes
        self._summary_format = summary_format

    def on_pre_projection(self, *, session) -> None:
        tool_use_index = {
            event.payload["id"]: event.seq
            for event in session.log
            if event.type == "tool_use"
        }
        for event in mutations.apply(session.log):
            if event.type != "tool_result":
                continue
            output = str(event.payload.get("output") or "")
            if len(output.encode("utf-8")) <= self._max_bytes:
                continue
            use_seq = tool_use_index.get(event.payload["tool_use_id"])
            if use_seq is None:
                continue
            compact_action.call(
                session,
                replaces=sorted([use_seq, event.seq]),
                summary=self._summary(session.log, event, output),
            )

    def _summary(self, log, result_event, output: str) -> str:
        tool_name = self._tool_name(log, result_event.payload["tool_use_id"])
        prefix = output.encode("utf-8")[: self._prefix_bytes].decode(
            "utf-8", errors="ignore"
        )
        return (
            self._summary_format
            .replace("$TOOL", tool_name)
            .replace("$CAP", str(self._max_bytes))
            .replace("$ORIGINAL", str(len(output.encode("utf-8"))))
            .replace("$PREFIX", prefix)
        )

    def _tool_name(self, log, tool_use_id: str) -> str:
        for event in log.reverse_each():
            if event.type == "tool_use" and event.payload["id"] == tool_use_id:
                return str(event.payload.get("name", "unknown"))
        return "unknown"
