"""DenyByName permission strategy."""

from __future__ import annotations

import json

from ... import hooks as global_hooks


class DenyByName:
    DEFAULT_REASON_FORMAT = "tool $NAME is on the deny-list"

    @classmethod
    def install(
        cls,
        session=None,
        names: list[str] | None = None,
        reason_format: str = DEFAULT_REASON_FORMAT,
    ):
        instance = cls(names=names or [], reason_format=reason_format)
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_tool_use", instance.on_pre_tool_use)
        return instance.on_pre_tool_use

    def __init__(self, names: list[str], reason_format: str = DEFAULT_REASON_FORMAT) -> None:
        if not names or not all(isinstance(name, str) for name in names):
            raise ValueError("names must be a non-empty list of strings")
        self._denylist = set(names)
        self._reason_format = reason_format

    def on_pre_tool_use(self, *, tool_use, **_):
        name = tool_use.payload["name"]
        if name in self._denylist:
            return {
                "allow": False,
                "reason": self._reason_format.replace(
                    "$NAME", json.dumps(name, ensure_ascii=False)
                ),
            }
        return {"allow": True}
