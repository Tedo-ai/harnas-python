"""AlwaysAllow permission strategy."""

from __future__ import annotations

from ... import hooks as global_hooks


class AlwaysAllow:
    @classmethod
    def install(cls, session=None):
        instance = cls()
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_tool_use", instance.on_pre_tool_use)
        return instance.on_pre_tool_use

    def on_pre_tool_use(self, **_):
        return {"allow": True}
