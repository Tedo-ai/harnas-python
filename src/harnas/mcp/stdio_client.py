"""JSON-RPC over subprocess stdio MCP transport."""

from __future__ import annotations

from typing import Any
import json
import os
import queue
import signal
import subprocess
import threading

from .client import ClientBehavior, DEFAULT_TIMEOUT, initialize_params, request_payload
from .content import flatten
from .errors import StartupError, TimeoutError, TransportError


class StdioClient(ClientBehavior):
    def __init__(
        self,
        *,
        command: str,
        args: list[str] | None = None,
        server_name: str,
        env: dict[str, str] | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.command = command
        self.args = list(args or [])
        self.server_name = server_name
        self.env = dict(env or {})
        self.timeout = timeout
        self._next_id = 1
        self._pending: dict[int, queue.Queue] = {}
        self._lock = threading.Lock()
        self._closed = False
        self.degraded = False
        self.degraded_error: Exception | None = None
        self._tools_cache: list[dict[str, Any]] | None = None
        self._spawn()

    def initialize_session(self) -> None:
        self._request("initialize", initialize_params())
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        return list(result.get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if error := self._degraded_error():
            raise error
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        return flatten(result.get("content"))

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self.process.stdin:
                self.process.stdin.close()
        if self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
            self.process.wait(timeout=3)
        except Exception:  # noqa: BLE001 - best-effort teardown
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except Exception:
                self.process.kill()

    def _spawn(self) -> None:
        env = os.environ.copy()
        env.update(self.env)
        try:
            self.process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                start_new_session=True,
            )
        except OSError as error:
            raise StartupError(str(error)) from error
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        response_queue: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._pending[request_id] = response_queue
        try:
            self._write(request_payload(id=request_id, method=method, params=params))
            response = response_queue.get(timeout=self.timeout)
        except queue.Empty as error:
            with self._lock:
                self._pending.pop(request_id, None)
            raise TimeoutError(f"timed out waiting for MCP response {request_id}") from error
        if isinstance(response, Exception):
            raise response
        if response.get("error") is not None:
            raise TransportError(str(response["error"]))
        return dict(response.get("result") or {})

    def _notify(self, method: str) -> None:
        self._write(request_payload(id=None, method=method, params={}))

    def _write(self, payload: dict[str, Any]) -> None:
        if self.process.stdin is None:
            raise TransportError("MCP subprocess is not writable")
        try:
            self.process.stdin.write(json.dumps(payload) + "\n")
            self.process.stdin.flush()
        except OSError as error:
            raise TransportError(f"MCP subprocess is not writable: {error}") from error

    def _read_loop(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                response = json.loads(line)
            except json.JSONDecodeError as error:
                self._fail_pending(TransportError(f"malformed JSON response: {error}"))
                return
            request_id = response.get("id")
            if request_id is None:
                continue
            with self._lock:
                response_queue = self._pending.pop(int(request_id), None)
            if response_queue is not None:
                response_queue.put(response)
        self._fail_pending(TransportError("MCP subprocess exited"))

    def _fail_pending(self, error: Exception) -> None:
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
            self._closed = True
        for response_queue in pending:
            response_queue.put(error)

