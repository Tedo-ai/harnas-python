"""Mutations.apply — resolve :compact and :revert against a Log.

Mirrors `Harnas::Mutations`. Mutation events are removed from the
effective stream; for each non-revoked :compact, its `replaces` seqs
are shadowed and a synthesized :summary event takes the place of the
lowest replaced seq.
"""

from __future__ import annotations

from .event import Event
from .log import Log

MUTATION_TYPES = {"compact", "revert"}


def apply(log: Log) -> list[Event]:
    state = _analyze(log)
    return _effective(log, state)


def _analyze(log: Log) -> dict:
    mutations = [e for e in log if e.type in MUTATION_TYPES]
    revoked = {e.payload["revokes"] for e in mutations if e.type == "revert"}
    compacts = [e for e in mutations if e.type == "compact" and e.seq not in revoked]
    shadowed: set[int] = set()
    summary_at: dict[int, Event] = {}
    for c in compacts:
        replaces = c.payload["replaces"]
        for s in replaces:
            shadowed.add(s)
        summary_at[min(replaces)] = c
    return {"shadowed": shadowed, "summary_at": summary_at}


def _effective(log: Log, state: dict) -> list[Event]:
    out: list[Event] = []
    for evt in log:
        if evt.type in MUTATION_TYPES:
            continue
        if evt.seq in state["summary_at"]:
            out.append(_synthesize_summary(state["summary_at"][evt.seq]))
        elif evt.seq in state["shadowed"]:
            continue
        else:
            out.append(evt)
    return out


def _synthesize_summary(compact: Event) -> Event:
    return Event(
        seq=compact.seq,
        id=compact.id,
        type="summary",
        payload={"text": compact.payload["summary"]},
    )
