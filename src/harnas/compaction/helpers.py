"""Compaction helpers — shared utilities for compaction strategies.

Mirrors `Harnas::Compaction::Helpers`.
"""

from __future__ import annotations

from .. import mutations
from ..log import Log

MESSAGE_TYPES = {"user_message", "assistant_message", "tool_use", "tool_result"}


def message_events(log: Log) -> list:
    """Effective events filtered to the four real message types.

    Excludes :summary so a compaction's own output never re-triggers
    the strategy on the next pre_projection invocation.
    """
    return [e for e in mutations.apply(log) if e.type in MESSAGE_TYPES]


def tool_pair_safe_range(log: Log, candidate_seqs: list[int]) -> list[int]:
    """Trim a candidate seq list so we never compact one half of a
    tool_use/tool_result pair without the other.
    """
    candidate_set = set(candidate_seqs)
    safe = set(candidate_seqs)
    for use_seq, result_seq in _tool_pairs(log):
        use_in = use_seq in candidate_set
        if result_seq is None:
            safe.discard(use_seq)
            continue
        result_in = result_seq in candidate_set
        if use_in == result_in:
            continue
        safe.discard(use_seq)
        safe.discard(result_seq)
    return sorted(safe)


def estimate_tokens(events: list) -> int:
    chars = 0
    for event in events:
        for value in event.payload.values():
            if isinstance(value, str):
                chars += len(value)
    return (chars + 3) // 4


def _tool_pairs(log: Log) -> list[tuple[int, int | None]]:
    use_seqs: dict[str, int] = {}
    result_seqs: dict[str, int] = {}
    for event in log:
        if event.type == "tool_use":
            use_seqs[event.payload["id"]] = event.seq
        elif event.type == "tool_result":
            result_seqs[event.payload["tool_use_id"]] = event.seq
    return [
        (us, result_seqs.get(id_))
        for id_, us in use_seqs.items()
    ]
