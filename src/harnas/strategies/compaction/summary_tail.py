"""SummaryTail compaction strategy."""

from __future__ import annotations

from typing import Any, Callable

from ... import hooks as global_hooks
from ...actions import compact as compact_action
from ...compaction import helpers
from ...log import Log


class SummaryTail:
    DEFAULT_PROMPT = (
        "Summarize the preceding conversation tersely, preserving facts "
        "the agent will need to continue the work. Return only the summary "
        "text, no preamble."
    )

    @classmethod
    def install(
        cls,
        session=None,
        *,
        projection: Callable[[Log], dict[str, Any]],
        provider: Callable[[dict[str, Any]], dict[str, Any]],
        ingestor: Callable[[dict[str, Any]], list[dict[str, Any]]],
        max_messages: int = 20,
        keep_recent: int = 10,
        prompt: str = DEFAULT_PROMPT,
    ):
        instance = cls(
            projection=projection,
            provider=provider,
            ingestor=ingestor,
            max_messages=max_messages,
            keep_recent=keep_recent,
            prompt=prompt,
        )
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_projection", instance.on_pre_projection)
        return instance.on_pre_projection

    def __init__(
        self,
        *,
        projection: Callable[[Log], dict[str, Any]],
        provider: Callable[[dict[str, Any]], dict[str, Any]],
        ingestor: Callable[[dict[str, Any]], list[dict[str, Any]]],
        max_messages: int,
        keep_recent: int,
        prompt: str = DEFAULT_PROMPT,
    ) -> None:
        if not callable(projection):
            raise ValueError("projection must be callable")
        if not callable(provider):
            raise ValueError("provider must be callable")
        if not callable(ingestor):
            raise ValueError("ingestor must be callable")
        if not (
            isinstance(max_messages, int)
            and isinstance(keep_recent, int)
            and max_messages > keep_recent >= 0
        ):
            raise ValueError("max_messages must be > keep_recent >= 0")
        self._projection = projection
        self._provider = provider
        self._ingestor = ingestor
        self._max_messages = max_messages
        self._keep_recent = keep_recent
        self._prompt = prompt

    def on_pre_projection(self, *, session) -> None:
        messages = helpers.message_events(session.log)
        if len(messages) <= self._max_messages:
            return

        candidate_seqs = [event.seq for event in messages[: len(messages) - self._keep_recent]]
        safe_seqs = helpers.tool_pair_safe_range(session.log, candidate_seqs)
        if not safe_seqs:
            return

        summary = self._summarize([event for event in messages if event.seq in set(safe_seqs)])
        if summary == "":
            return
        compact_action.call(session, replaces=safe_seqs, summary=summary)

    def _summarize(self, events: list[Any]) -> str:
        sub_log = Log()
        for event in events:
            sub_log.append(type=event.type, payload=event.payload)
        sub_log.append(type="user_message", payload={"text": self._prompt})
        response = self._provider(self._projection(sub_log))
        for event in self._ingestor(response):
            sub_log.append(type=event["type"], payload=event["payload"])
        assistant = next(
            (event for event in sub_log.reverse_each() if event.type == "assistant_message"),
            None,
        )
        return "" if assistant is None else str(assistant.payload.get("text") or "")
