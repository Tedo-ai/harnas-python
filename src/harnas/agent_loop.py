"""AgentLoop — drives Log -> Projection -> Provider -> Ingestor.

Mirrors `Harnas::AgentLoop` for the buffered path and the deterministic
streaming path that conformance fixtures exercise. Provider error
handling lands later.
"""

from __future__ import annotations

from typing import Any, Callable

from .session import Session

DEFAULT_MAX_TURNS = 10
STREAM_DELTA_TYPES = {"assistant_text_delta", "tool_use_argument_delta"}
RETRYABLE_HTTP_STATUSES = {408, 429, 500, 502, 503, 504}


class AgentLoop:
    def __init__(
        self,
        session: Session,
        projection: Callable[[Any], dict[str, Any]],
        provider: Callable[[dict[str, Any]], dict[str, Any]],
        ingestor: Callable[[dict[str, Any]], list[dict[str, Any]]] | None,
        stream_provider: Callable[[dict[str, Any], Callable[[dict[str, Any]], None]], None] | None = None,
        on_stream_event: Callable[[Any], None] | None = None,
        runner: Any | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self._session = session
        self._projection = projection
        self._provider = provider
        self._ingestor = ingestor
        self._stream_provider = stream_provider
        self._on_stream_event = on_stream_event
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
        if not self._call_provider_with_retry(request):
            return "provider_failed"

        last_assistant = next(
            (e for e in self._session.log.reverse_each() if e.type == "assistant_message"),
            None,
        )
        return last_assistant.payload["stop_reason"] if last_assistant else "end_turn"

    def _call_provider_with_retry(self, request: dict[str, Any]) -> bool:
        attempt = 1
        while True:
            try:
                if self._stream_provider is not None:
                    self._stream_provider(request, self._append_event)
                else:
                    response = self._provider(request)
                    events = self._ingestor(response)
                    for evt in events:
                        self._append_event(evt)
                return True
            except Exception as e:  # noqa: BLE001
                terminal = not self._retryable(e, attempt)
                self._append_provider_error(e, attempt=attempt, terminal=terminal)
                if terminal:
                    return False
                attempt += 1

    def _retryable(self, error: Exception, attempt: int) -> bool:
        if attempt >= 3:
            return False
        status = getattr(error, "status", None)
        return status in RETRYABLE_HTTP_STATUSES

    def _append_provider_error(self, error: Exception, attempt: int, terminal: bool) -> None:
        self._session.log.append(
            type="provider_error",
            payload={
                "provider": "unknown",
                "status": getattr(error, "status", None),
                "error_class": "Harnas::Providers::HTTPError"
                if hasattr(error, "status")
                else f"{type(error).__module__}.{type(error).__name__}",
                "message": str(error),
                "attempt": attempt,
                "terminal": terminal,
            },
        )

    def _append_event(self, evt: dict[str, Any]) -> None:
        event = self._session.log.append(type=evt["type"], payload=evt["payload"])
        if self._on_stream_event is not None and event.type in STREAM_DELTA_TYPES:
            self._on_stream_event(event)

    def _dispatch_pending_tools(self) -> list:
        if self._runner is None:
            return []
        pending = self._pending_tool_uses()
        for tu in pending:
            decisions = self._session.hooks.invoke(
                "pre_tool_use", session=self._session, tool_use=tu
            )
            denied = next(
                (
                    d for d in decisions
                    if isinstance(d, dict) and d.get("allow") is False
                ),
                None,
            )
            if denied is not None:
                self._session.log.append(
                    type="tool_result",
                    payload={
                        "tool_use_id": tu.payload["id"],
                        "output": None,
                        "error": f"denied by hook: {denied.get('reason') or 'no reason given'}",
                    },
                )
            else:
                self._runner.run(tu, into_log=self._session.log)

            tool_result = next(
                (
                    e for e in self._session.log.reverse_each()
                    if e.type == "tool_result"
                    and e.payload.get("tool_use_id") == tu.payload["id"]
                ),
                None,
            )
            self._session.hooks.invoke(
                "post_tool_use",
                session=self._session,
                tool_use=tu,
                tool_result=tool_result,
                denied=denied is not None,
            )
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
