"""AgentLoop — drives Log -> Projection -> Provider -> Ingestor.

Mirrors `Harnas::AgentLoop` for the buffered path and the deterministic
streaming path that conformance fixtures exercise. Provider error
handling lands later.
"""

from __future__ import annotations

from typing import Any, Callable

from .session import Session

DEFAULT_MAX_TURNS = 10


class AgentLoop:
    def __init__(
        self,
        session: Session,
        projection: Callable[[Any], dict[str, Any]],
        provider: Callable[[dict[str, Any]], dict[str, Any]],
        ingestor: Callable[[dict[str, Any]], list[dict[str, Any]]] | None,
        stream_provider: Callable[[dict[str, Any], Callable[[dict[str, Any]], None]], None] | None = None,
        runner: Any | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self._session = session
        self._projection = projection
        self._provider = provider
        self._ingestor = ingestor
        self._stream_provider = stream_provider
        self._runner = runner
        self._max_turns = max_turns

    def run(self) -> str:
        reason = "max_turns_reached"

        for _turn in range(self._max_turns):
            stop_reason = self._run_turn()

            if stop_reason != "tool_use":
                reason = "end_turn"
                break

            if not self._dispatch_pending_tools():
                reason = "no_pending_tools"
                break

        return reason

    def _run_turn(self) -> str:
        self._session.hooks.invoke("pre_projection", session=self._session)
        request = self._projection(self._session.log)
        if self._stream_provider is not None:
            self._stream_provider(request, self._append_event)
        else:
            response = self._provider(request)
            events = self._ingestor(response)
            for evt in events:
                self._append_event(evt)

        last_assistant = next(
            (e for e in self._session.log.reverse_each() if e.type == "assistant_message"),
            None,
        )
        return last_assistant.payload["stop_reason"] if last_assistant else "end_turn"

    def _append_event(self, evt: dict[str, Any]) -> None:
        self._session.log.append(type=evt["type"], payload=evt["payload"])

    def _dispatch_pending_tools(self) -> list:
        if self._runner is None:
            return []
        pending = self._pending_tool_uses()
        for tu in pending:
            self._runner.run(tu, into_log=self._session.log)
        return pending

    def _pending_tool_uses(self) -> list:
        fulfilled = {
            e.payload["tool_use_id"]
            for e in self._session.log
            if e.type == "tool_result"
        }
        return [
            e for e in self._session.log
            if e.type == "tool_use" and e.payload["id"] not in fulfilled
        ]
