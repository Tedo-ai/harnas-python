"""Canonical built-in tool handlers."""

from __future__ import annotations

import glob as glob_module
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_SHELL_TIMEOUT_SECONDS = 30
GREP_MAX_MATCHES = 200
MAX_FETCH_BYTES = 256 * 1024


def handlers() -> dict[str, Callable[[dict[str, Any]], str]]:
    return {
        "harnas.builtin.read_file": read_file,
        "harnas.builtin.write_file": write_file,
        "harnas.builtin.edit_file": edit_file,
        "harnas.builtin.list_dir": list_dir,
        "harnas.builtin.glob": glob,
        "harnas.builtin.grep": grep,
        "harnas.builtin.run_shell": run_shell,
        "harnas.builtin.fetch_url": fetch_url,
    }


DESCRIPTORS = [
    {
        "name": "read_file",
        "handler": "harnas.builtin.read_file",
        "description": "Read the contents of a file at the given path. Returns the file body as text.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
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
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
]


def descriptors() -> list[dict[str, Any]]:
    return DESCRIPTORS


def read_file(args: dict[str, Any]) -> str:
    return Path(_require(args, "path")).read_text(encoding="utf-8")


def write_file(args: dict[str, Any]) -> str:
    path = _require(args, "path")
    content = _require(args, "content")
    Path(path).write_text(content, encoding="utf-8")
    return f"wrote {len(content.encode('utf-8'))} bytes to {path}"


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
    with urllib.request.urlopen(url, timeout=30) as response:
        body = response.read(MAX_FETCH_BYTES).decode("utf-8", errors="replace")
        status = getattr(response, "status", response.getcode())
    return f"HTTP {status}\n{body}"


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
