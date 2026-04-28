"""Action: append a :compact Mutation Event to a Session's Log.

Mirrors `Harnas::Actions::Compact`.
"""

from __future__ import annotations

from ..session import Session


def call(session: Session, replaces: list[int], summary: str):
    return session.log.append(
        type="compact",
        payload={"replaces": list(replaces), "summary": summary},
    )
