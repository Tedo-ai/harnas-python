"""Health-check guard strategy."""

from __future__ import annotations

import subprocess
from typing import Any

from ... import hooks as global_hooks


class Health:
    @classmethod
    def install(
        cls,
        session=None,
        command: str = "",
        timeout_seconds: int = 60,
        on_failure: str = "refuse_turn",
    ):
        instance = cls(command=command, timeout_seconds=timeout_seconds, on_failure=on_failure)
        target_hooks = session.hooks if session is not None else global_hooks
        target_hooks.on("pre_projection", instance.on_pre_projection)
        return instance.on_pre_projection

    def __init__(self, *, command: str, timeout_seconds: int = 60, on_failure: str = "refuse_turn") -> None:
        self.command = command
        self.timeout_seconds = int(timeout_seconds)
        self.on_failure = str(on_failure)
        self.checks = 0

    def on_pre_projection(self, *, session, **_: Any) -> None:
        self.checks += 1
        if self.checks == 1:
            return
        result = self._run_check()
        if result["success"]:
            return
        if self.on_failure == "warn_only":
            self._annotate(session, result)
        else:
            self._refuse(session, result)

    def _run_check(self) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                self.command,
                shell=True,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            output = "\n".join(part for part in [completed.stderr, completed.stdout] if part)
            return {
                "success": completed.returncode == 0,
                "output": output,
                "exit_code": completed.returncode,
            }
        except subprocess.TimeoutExpired as exc:
            output = exc.stderr or exc.stdout or f"health check timed out after {self.timeout_seconds}s"
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            return {"success": False, "output": output, "exit_code": None}

    def _refuse(self, session, result: dict[str, Any]) -> None:
        session.log.append(
            type="runtime_error",
            payload={
                "source": "strategy",
                "handler": "guard/health",
                "error_class": "Harnas::HealthGuard",
                "message": "health_check_failed",
                "reason": "health_check_failed",
                "output": result["output"],
                "exit_code": result["exit_code"],
                "terminal": True,
            },
        )

    def _annotate(self, session, result: dict[str, Any]) -> None:
        session.log.append(
            type="annotation",
            payload={
                "kind": "guard.health_failed",
                "data": {"output": result["output"], "exit_code": result["exit_code"]},
            },
        )
