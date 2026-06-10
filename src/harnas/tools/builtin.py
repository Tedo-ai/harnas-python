"""Canonical built-in tool handlers."""

from __future__ import annotations

import glob as glob_module
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse

from harnas import skills

DEFAULT_SHELL_TIMEOUT_SECONDS = 30
GREP_MAX_MATCHES = 200
MAX_FETCH_BYTES = 256 * 1024
MAX_FETCH_REDIRECTS = 5
DEFAULT_BASH_SESSION_MAX_OUTPUT_BYTES = 64 * 1024
ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*[mGKHF]|\r")
ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BASH_SESSION_REGISTRY = None


def _default_bash_session_shell_type() -> str:
    if sys.platform != "win32":
        return "posix"
    if shutil.which("pwsh") or shutil.which("powershell.exe"):
        return "powershell"
    return "cmd"


def _resolve_bash_session_shell(config: dict[str, Any]) -> tuple[str, str]:
    shell = str(config.get("shell") or "")
    if not shell or shell == "auto":
        if sys.platform == "win32":
            shell = shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("cmd.exe") or "cmd.exe"
        else:
            shell = "bash"
    if shell == "bash" and shutil.which("bash") is None:
        shell = "sh"

    shell_type = str(config.get("shell_type") or "")
    if not shell_type or shell_type == "auto":
        if sys.platform != "win32":
            shell_type = "posix"
        elif "powershell" in shell.lower() or "pwsh" in shell.lower():
            shell_type = "powershell"
        else:
            shell_type = "cmd"
    return shell, shell_type


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _cmd_env_quote(value: str) -> str:
    escaped = value.replace("^", "^^")
    for char in ('"', "&", "|", "<", ">", "(", ")"):
        escaped = escaped.replace(char, "^" + char)
    escaped = escaped.replace("%", "%%")
    return escaped


def handlers() -> dict[str, Callable[[dict[str, Any]], str]]:
    bash_sessions = BashSessionRegistry()
    return {
        "harnas.builtin.read_file": read_file,
        "harnas.builtin.write_file": write_file,
        "harnas.builtin.edit_file": edit_file,
        "harnas.builtin.list_dir": list_dir,
        "harnas.builtin.glob": glob,
        "harnas.builtin.grep": grep,
        "harnas.builtin.run_shell": run_shell,
        "harnas.builtin.fetch_url": fetch_url,
        "harnas.builtin.spawn_agent": spawn_agent,
        "harnas.builtin.load_skill": load_skill,
        "harnas.builtin.bash_session": bash_sessions.handle,
    }


DESCRIPTORS = [
    {
        "name": "read_file",
        "handler": "harnas.builtin.read_file",
        "description": "Read a text file with cat -n style line numbers. Supports optional offset and limit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {
                    "type": "integer",
                    "description": "Start at line N (0-indexed). Default 0.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Read at most N lines. Default 2000.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "handler": "harnas.builtin.write_file",
        "description": "Write text content to a file at the given path, overwriting any existing content.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "handler": "harnas.builtin.edit_file",
        "description": "Replace one occurrence of old_string with new_string in the file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_string": {"type": "string"},
                "new_string": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "list_dir",
        "handler": "harnas.builtin.list_dir",
        "description": "List the entries of the directory at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "glob",
        "handler": "harnas.builtin.glob",
        "description": "Find files matching a glob pattern under the optional path root.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}},
            "required": ["pattern"],
        },
    },
    {
        "name": "grep",
        "handler": "harnas.builtin.grep",
        "description": "Search for a regular expression in file contents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "glob": {"type": "string"},
                "case_insensitive": {"type": "boolean"},
            },
            "required": ["pattern", "path"],
        },
    },
    {
        "name": "run_shell",
        "handler": "harnas.builtin.run_shell",
        "description": "Run a shell command and return stdout, stderr, and exit status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_seconds": {"type": "integer", "minimum": 1},
            },
            "required": ["command"],
        },
    },
    {
        "name": "fetch_url",
        "handler": "harnas.builtin.fetch_url",
        "description": "Fetch a URL via HTTP GET and return the response body as text.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "headers": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "load_skill",
        "handler": "harnas.builtin.load_skill",
        "description": "Load the body of a named skill from the configured skills directory.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "bash_session",
        "handler": "harnas.builtin.bash_session",
        "description": (
            "Run a command in a persistent bash session. Sessions preserve working directory "
            "and environment variables across calls. stdin is /dev/null; interactive programs "
            "cannot receive input."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "command": {"type": "string"},
                "action": {"type": "string", "enum": ["run", "status", "kill"]},
                "timeout_ms": {"type": "integer", "minimum": 1},
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
        "config": {
            "shell": "auto",
            "shell_type": _default_bash_session_shell_type(),
            "max_output_bytes": DEFAULT_BASH_SESSION_MAX_OUTPUT_BYTES,
        },
    },
    {
        "name": "spawn_agent",
        "handler": "harnas.builtin.spawn_agent",
        "description": (
            "Create a child agent Session receipt for a delegated task. Products run "
            "and join the child according to their supervisor policy."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string"},
                "label": {"type": "string"},
                "role": {"type": "string"},
                "tools_deny": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task"],
        },
    },
]


def descriptors() -> list[dict[str, Any]]:
    return DESCRIPTORS


def read_file(args: dict[str, Any]) -> str:
    path = _require(args, "path")
    data = Path(path).read_bytes()
    if b"\0" in data[:8192]:
        raise ValueError(
            f"Cannot read binary file '{path}'. Use bash_session to inspect binary files."
        )
    offset = max(_optional_int(args, "offset"), 0)
    limit = _optional_int(args, "limit")
    if limit <= 0:
        limit = 2000
    limit = min(limit, 10_000)
    return _format_numbered_file(data, offset, limit)


def write_file(args: dict[str, Any]) -> str:
    path = _require(args, "path")
    content = _require(args, "content")
    Path(path).write_text(content, encoding="utf-8")
    return f"wrote {len(content.encode('utf-8'))} bytes to {path}"


def spawn_agent(args: dict[str, Any]) -> str:
    raise RuntimeError("spawn_agent is handled by harnas.tools.runner.Runner")


def edit_file(args: dict[str, Any]) -> str:
    path = _require(args, "path")
    old_string = _fetch(args, "old_string")
    new_string = _fetch(args, "new_string")
    replace_all = bool(args.get("replace_all", False))
    if old_string == new_string:
        raise ValueError("old_string and new_string must differ")
    target = Path(path)
    content = target.read_text(encoding="utf-8")
    count = content.count(old_string)
    if count == 0:
        raise ValueError(f"old_string not found in {path}")
    if count > 1 and not replace_all:
        raise ValueError(
            f"old_string appears {count} times in {path}; "
            "pass replace_all: true or add surrounding context"
        )
    updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    target.write_text(updated, encoding="utf-8")
    suffix = "" if count == 1 else "s"
    return f"edited {path} ({count} replacement{suffix})"


def list_dir(args: dict[str, Any]) -> str:
    path = Path(_require(args, "path"))
    if not path.is_dir():
        raise ValueError(f"not a directory: {path}")
    return "\n".join(sorted(child.name for child in path.iterdir()))


def glob(args: dict[str, Any]) -> str:
    pattern = _require(args, "pattern")
    root = str(args.get("path") or ".")
    full = pattern if Path(pattern).is_absolute() else str(Path(root) / pattern)
    return "\n".join(sorted(glob_module.glob(full, recursive=True)))


def grep(args: dict[str, Any]) -> str:
    pattern = _require(args, "pattern")
    path = _require(args, "path")
    flags = re.IGNORECASE if args.get("case_insensitive") else 0
    try:
        regex = re.compile(pattern, flags)
    except re.error as error:
        raise ValueError(f"invalid regex: {error}") from error
    matches: list[str] = []
    for file in _grep_files(path, str(args.get("glob") or "")):
        try:
            lines = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if regex.search(line):
                matches.append(f"{file}:{lineno}:{line}")
                if len(matches) >= GREP_MAX_MATCHES:
                    return "\n".join(matches) + f"\n... (truncated at {GREP_MAX_MATCHES} matches)"
    return "no matches" if not matches else "\n".join(matches)


def run_shell(args: dict[str, Any]) -> str:
    command = _require(args, "command")
    timeout = int(args.get("timeout_seconds") or DEFAULT_SHELL_TIMEOUT_SECONDS)
    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TimeoutError(f"command timed out after {timeout}s") from error
    return _format_shell_result(result.stdout, result.stderr, result.returncode)


def fetch_url(args: dict[str, Any]) -> str:
    url = _require(args, "url")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("only http(s) is supported")
    with _open_fetch_url(url, _fetch_headers(args)) as response:
        body = response.read(MAX_FETCH_BYTES).decode("utf-8", errors="replace")
        status = getattr(response, "status", response.getcode())
    return f"HTTP {status}\n{body}"


def _open_fetch_url(url: str, headers: dict[str, str]):
    opener = urllib.request.build_opener(_NoRedirectHandler)
    current_url = url
    current_headers = dict(headers)
    for _redirect in range(MAX_FETCH_REDIRECTS + 1):
        request = urllib.request.Request(current_url, headers=current_headers)
        try:
            return opener.open(request, timeout=30)
        except HTTPError as error:
            if error.code not in {301, 302, 303, 307, 308}:
                raise
            location = error.headers.get("Location")
            if not location:
                raise
            next_url = urljoin(current_url, location)
            if _url_host(next_url) != _url_host(current_url):
                current_headers = {}
            current_url = next_url
    raise RuntimeError(f"too many redirects fetching {url}")


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        return None


def _url_host(url: str) -> str | None:
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def _fetch_headers(args: dict[str, Any]) -> dict[str, str]:
    headers = args.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be an object")
    return {str(key): str(value) for key, value in headers.items()}


def load_skill(args: dict[str, Any], *, config: dict[str, Any] | None = None) -> str:
    name = _require(args, "name")
    if not skills.valid_name(name):
        raise RuntimeError(f"invalid skill name: {name}")
    config = config or {}
    skills_dir = str(config.get("skills_dir") or "")
    if not skills_dir:
        raise RuntimeError("missing skills_dir config")
    allowed = {path.stem for path in Path(skills_dir).glob("*.md")}
    if name not in allowed:
        raise RuntimeError(f"unknown skill: {name}")
    path = Path(skills_dir) / f"{name}.md"
    strip_frontmatter = bool(config.get("strip_frontmatter", True))
    if not strip_frontmatter:
        return path.read_text(encoding="utf-8")
    _frontmatter, body = skills.parse_skill_file(path)
    return body


def _bash_session_handler() -> Callable[..., str]:
    global _BASH_SESSION_REGISTRY
    if _BASH_SESSION_REGISTRY is None:
        _BASH_SESSION_REGISTRY = BashSessionRegistry()
    return _BASH_SESSION_REGISTRY.handle


def bash_session(args: dict[str, Any], *, config: dict[str, Any] | None = None) -> str:
    return _bash_session_handler()(args, config=config or {})


class BashSessionRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, BashSession] = {}

    def handle(self, args: dict[str, Any], *, config: dict[str, Any] | None = None) -> str:
        config = config or {}
        action = str(args.get("action") or "")
        command = str(args.get("command") or "")
        if not action and command:
            action = "run"
        if not action:
            action = "status"
        session_id = str(args.get("session_id") or "")
        if action == "run":
            if not command:
                raise ValueError("missing required argument: command")
            session = self._session(session_id, config, create=True)
            return _json_result(
                session.run(
                    command,
                    _command_env(args.get("env")),
                    _duration_ms(args.get("timeout_ms")),
                )
            )
        if action == "status":
            return _json_result(self._session(session_id, config, create=False).status())
        if action == "kill":
            return _json_result(self._session(session_id, config, create=False).kill())
        raise ValueError(f"unknown bash_session action: {action}")

    def close(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions = {}
        for session in sessions:
            session.close()

    def _session(self, session_id: str, config: dict[str, Any], *, create: bool) -> "BashSession":
        with self._lock:
            if session_id and session_id in self._sessions:
                return self._sessions[session_id]
            if session_id and not create:
                raise ValueError(f"unknown bash_session session_id: {session_id}")
            if not session_id and not create:
                raise ValueError("missing required argument: session_id")
            if not session_id:
                session_id = "sh_" + uuid.uuid4().hex[:16]
            session = BashSession(session_id, config)
            self._sessions[session_id] = session
            return session


class BashCommand:
    def __init__(self) -> None:
        self.token = uuid.uuid4().hex[:16]
        self.stdout_start = 0
        self.stderr_start = 0
        self.exit_code: int | None = None
        self.stdout_done = False
        self.stderr_done = False

    @property
    def done(self) -> bool:
        return self.stdout_done and self.stderr_done


class BashSession:
    def __init__(self, session_id: str, config: dict[str, Any]) -> None:
        self.id = session_id
        max_bytes = int(config.get("max_output_bytes") or DEFAULT_BASH_SESSION_MAX_OUTPUT_BYTES)
        if max_bytes <= 0:
            max_bytes = DEFAULT_BASH_SESSION_MAX_OUTPUT_BYTES
        self.stdout = RingBuffer(max_bytes)
        self.stderr = RingBuffer(max_bytes)
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.current: BashCommand | None = None
        self.closed = False

        self.shell, self.shell_type = _resolve_bash_session_shell(config)
        cwd = str(config.get("cwd") or ".")
        popen_kwargs: dict[str, Any] = {
            "cwd": str(Path(cwd).resolve()),
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
        }
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        self.process = subprocess.Popen([self.shell], **popen_kwargs)
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        self.stdin = self.process.stdin
        threading.Thread(target=self._read_stdout, args=(self.process.stdout,), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(self.process.stderr,), daemon=True).start()
        threading.Thread(target=self._wait_shell, daemon=True).start()

    def run(self, command: str, env: dict[str, str], timeout: float | None) -> dict[str, Any]:
        with self.condition:
            while self.current is not None:
                self.condition.wait()
            if self.closed:
                return self._snapshot("killed", None, None)
            current = BashCommand()
            current.stdout_start = self.stdout.offset()
            current.stderr_start = self.stderr.offset()
            self.current = current
            command = self._command_with_env(command, env)
            framed = self._framed_command(command, current.token)
            try:
                self.stdin.write(framed)
                self.stdin.flush()
            except OSError:
                self.current = None
                self.condition.notify_all()
                return self._snapshot("killed", None, current)
            if timeout is not None:
                self.condition.wait_for(lambda: current.done, timeout)
                if not current.done:
                    return self._snapshot("running", None, current)
            else:
                self.condition.wait_for(lambda: current.done)
            return self._snapshot("completed", current.exit_code, current)

    def _command_with_env(self, command: str, env: dict[str, str]) -> str:
        if not env:
            return command
        if self.shell_type == "powershell":
            assignments = [
                f"$__harnas_old_{key}=$env:{key}; $env:{key}={_powershell_quote(env[key])}"
                for key in sorted(env)
            ]
            restores = [f"$env:{key}=$__harnas_old_{key}" for key in sorted(env)]
            return f"{'; '.join(assignments)}; try {{ {command} }} finally {{ {'; '.join(restores)} }}"
        if self.shell_type == "cmd":
            assignments = [f'set "{key}={_cmd_env_quote(env[key])}"' for key in sorted(env)]
            return " & ".join(["setlocal", *assignments, command, "endlocal"])
        assignments = [
            f"{key}={shlex.quote(env[key])}"
            for key in sorted(env)
        ]
        parts = ["env", *assignments, shlex.quote(self.shell), "-c", shlex.quote(command)]
        return " ".join(parts)

    def status(self) -> dict[str, Any]:
        with self.condition:
            if self.current is not None:
                return self._snapshot("running", None, self.current)
            if self.closed:
                return self._snapshot("killed", None, None)
            return self._snapshot("completed", None, None)

    def kill(self) -> dict[str, Any]:
        with self.condition:
            if self.current is None:
                return self._snapshot("completed", None, None)
            current = self.current
            self._killpg(signal.SIGTERM)
            self.condition.wait_for(lambda: current.done, 3)
            if not current.done:
                self._killpg(getattr(signal, "SIGKILL", signal.SIGTERM))
                self.condition.wait_for(lambda: current.done)
            self.closed = True
            return self._snapshot("killed", None, current)

    def close(self) -> None:
        with self.condition:
            self.closed = True
            self._killpg(getattr(signal, "SIGKILL", signal.SIGTERM))

    def _read_stdout(self, stream: Any) -> None:
        for line in stream:
            before, matched = self._stdout_sentinel(line)
            if before:
                self.stdout.write(_strip_ansi(before))
            if not matched:
                self.stdout.write(_strip_ansi(line))

    def _read_stderr(self, stream: Any) -> None:
        for line in stream:
            before, matched = self._stderr_sentinel(line)
            if before:
                self.stderr.write(_strip_ansi(before))
            if not matched:
                self.stderr.write(_strip_ansi(line))

    def _stdout_sentinel(self, line: str) -> tuple[str, bool]:
        prefix = "__HARNAS_DONE_"
        index = line.find(prefix)
        if index < 0:
            return "", False
        before = line[:index]
        parts = line[index:].strip().removeprefix(prefix).split(":", 1)
        if len(parts) != 2:
            return "", False
        with self.condition:
            if self.current is not None and self.current.token == parts[0]:
                self.current.exit_code = int(parts[1])
                self.current.stdout_done = True
                if self.current.done:
                    self.current = None
                self.condition.notify_all()
        return before, True

    def _stderr_sentinel(self, line: str) -> tuple[str, bool]:
        prefix = "__HARNAS_ERR_DONE_"
        index = line.find(prefix)
        if index < 0:
            return "", False
        before = line[:index]
        token = line[index:].strip().removeprefix(prefix)
        with self.condition:
            if self.current is not None and self.current.token == token:
                self.current.stderr_done = True
                if self.current.done:
                    self.current = None
                self.condition.notify_all()
        return before, True

    def _wait_shell(self) -> None:
        code = self.process.wait()
        with self.condition:
            self.closed = True
            if self.current is not None:
                self.current.exit_code = code
                self.current.stdout_done = True
                self.current.stderr_done = True
                self.current = None
                self.condition.notify_all()

    def _killpg(self, sig: int) -> None:
        try:
            if sys.platform == "win32":
                self.process.kill() if sig == signal.SIGKILL else self.process.terminate()
            else:
                os.killpg(self.process.pid, sig)
        except OSError:
            pass

    def _framed_command(self, command: str, token: str) -> str:
        if self.shell_type == "powershell":
            return (
                f"\n& {{ {command} }}; $__harnas_status=$LASTEXITCODE; "
                "if ($null -eq $__harnas_status) { $__harnas_status=0 }; "
                f"[Console]::Error.WriteLine('__HARNAS_ERR_DONE_{token}'); "
                f"[Console]::Out.WriteLine('__HARNAS_DONE_{token}:' + $__harnas_status)\n"
            )
        if self.shell_type == "cmd":
            return (
                f"\r\n{command}\r\nset __harnas_status=%ERRORLEVEL%\r\n"
                f"echo __HARNAS_ERR_DONE_{token} 1>&2\r\n"
                f"echo __HARNAS_DONE_{token}:%__harnas_status%\r\n"
            )
        return (
            f"\n{{ {command}\n}} </dev/null; __harnas_status=$?; "
            f"printf '__HARNAS_ERR_DONE_{token}\\n' >&2; "
            f"printf '__HARNAS_DONE_{token}:%s\\n' \"$__harnas_status\"\n"
        )

    def _snapshot(self, status: str, exit_code: int | None, command: BashCommand | None) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "status": status,
            "exit_code": exit_code,
            "stdout": self.stdout.string(),
            "stderr": self.stderr.string(),
            "command_stdout": self.stdout.string_from(command.stdout_start) if command else "",
            "command_stderr": self.stderr.string_from(command.stderr_start) if command else "",
            "truncated": self.stdout.truncated or self.stderr.truncated,
        }


class RingBuffer:
    def __init__(self, max_bytes: int) -> None:
        self.max = max_bytes
        self.data = b""
        self.total = 0
        self.truncated = False
        self.lock = threading.Lock()

    def write(self, value: str) -> None:
        chunk = value.encode("utf-8")
        with self.lock:
            self.total += len(chunk)
            self.data += chunk
            if self.max > 0 and len(self.data) > self.max:
                self.truncated = True
                self.data = self.data[-self.max:]

    def offset(self) -> int:
        with self.lock:
            return self.total

    def string(self) -> str:
        with self.lock:
            return self.data.decode("utf-8", errors="replace")

    def string_from(self, offset: int) -> str:
        with self.lock:
            start_offset = self.total - len(self.data)
            offset = max(start_offset, min(offset, self.total))
            start = offset - start_offset
            return self.data[start:].decode("utf-8", errors="replace")


def _require(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if value is None or value == "":
        raise ValueError(f"missing required argument: {key}")
    return str(value)


def _fetch(args: dict[str, Any], key: str) -> str:
    if key not in args or args[key] is None:
        raise ValueError(f"missing required argument: {key}")
    return str(args[key])


def _grep_files(path: str, glob_pattern: str) -> list[str]:
    root = Path(path)
    if root.is_file():
        return [str(root)]
    if not root.is_dir():
        raise ValueError(f"path does not exist: {path}")
    pattern = glob_pattern or "**/*"
    files = [
        str(candidate)
        for candidate in root.glob(pattern)
        if candidate.is_file()
    ]
    return sorted(files)


def _format_shell_result(stdout: str, stderr: str, exit_code: int) -> str:
    parts = [f"[exit {exit_code}]"]
    if stdout:
        parts.append(f"--- stdout ---\n{stdout}")
    if stderr:
        parts.append(f"--- stderr ---\n{stderr}")
    return "\n".join(parts)


def _duration_ms(value: Any) -> float | None:
    try:
        ms = int(value or 0)
    except (TypeError, ValueError):
        ms = 0
    return ms / 1000 if ms > 0 else None


def _optional_int(args: dict[str, Any], key: str) -> int:
    try:
        return int(args.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _format_numbered_file(data: bytes, offset: int, limit: int) -> str:
    if not data:
        return "... [file has 0 total lines; showing 0–0]\n"
    text = data.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    total = len(lines)
    if offset >= total:
        return f"... [file has {total} total lines; offset {offset} is past EOF]\n"
    finish = min(offset + limit, total)
    output = "".join(
        f"{line_no:6d}\t{line}\n"
        for line_no, line in enumerate(lines[offset:finish], start=offset + 1)
    )
    if total > offset + limit:
        output += f"... [file has {total} total lines; showing {offset}–{offset + limit}]\n"
    return output


def _command_env(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("bash_session env must be an object")
    env: dict[str, str] = {}
    for key, item in value.items():
        key = str(key)
        if not ENV_NAME_PATTERN.match(key):
            raise ValueError(f"invalid bash_session env key: {key}")
        if not isinstance(item, str):
            raise ValueError(f"bash_session env value for {key} must be a string")
        env[key] = item
    return env


def _strip_ansi(value: str) -> str:
    return ANSI_PATTERN.sub("", value)


def _json_result(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
