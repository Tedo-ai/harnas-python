import http.server
import socketserver
import threading

import pytest

from harnas.tools import builtin


def test_builtin_handlers_contains_canonical_tools():
    handlers = builtin.handlers()
    for name in [
        "harnas.builtin.read_file",
        "harnas.builtin.write_file",
        "harnas.builtin.edit_file",
        "harnas.builtin.list_dir",
        "harnas.builtin.glob",
        "harnas.builtin.grep",
        "harnas.builtin.run_shell",
        "harnas.builtin.fetch_url",
        "harnas.builtin.spawn_agent",
        "harnas.builtin.load_skill",
        "harnas.builtin.bash_session",
    ]:
        assert name in handlers


def test_builtin_descriptors_expose_canonical_tool_schemas():
    descriptors = builtin.descriptors()
    assert len(descriptors) == 11
    by_name = {descriptor["name"]: descriptor for descriptor in descriptors}
    for name in [
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "glob",
        "grep",
        "run_shell",
        "fetch_url",
        "spawn_agent",
        "load_skill",
        "bash_session",
    ]:
        assert by_name[name]["handler"]
        assert by_name[name]["description"]
        assert by_name[name]["input_schema"]
    assert by_name["grep"]["input_schema"]["required"] == ["pattern", "path"]
    assert by_name["bash_session"]["config"]["shell_type"] in {"posix", "powershell", "cmd"}


def test_builtin_read_write_edit_file(tmp_path):
    path = tmp_path / "note.txt"
    result = builtin.write_file({"path": str(path), "content": "alpha\nbravo\n"})

    assert "12 bytes" in result
    assert builtin.read_file({"path": str(path)}) == "     1\talpha\n     2\tbravo\n"
    builtin.edit_file({"path": str(path), "old_string": "bravo", "new_string": "BRAVO"})
    assert path.read_text(encoding="utf-8") == "alpha\nBRAVO\n"


def test_builtin_read_file_offset_limit_and_binary_guard(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    assert builtin.read_file({"path": str(path), "offset": 1, "limit": 1}) == (
        "     2\ttwo\n... [file has 3 total lines; showing 1–2]\n"
    )
    assert builtin.read_file({"path": str(path), "offset": 10}) == (
        "... [file has 3 total lines; offset 10 is past EOF]\n"
    )

    binary = tmp_path / "data.bin"
    binary.write_bytes(b"abc\0def")
    with pytest.raises(ValueError, match="Cannot read binary file"):
        builtin.read_file({"path": str(binary)})


def test_builtin_list_glob_and_grep(tmp_path):
    (tmp_path / "a.txt").write_text("Needle\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("needle\n", encoding="utf-8")

    assert builtin.list_dir({"path": str(tmp_path)}) == "a.txt\nb.py"
    assert "b.py" in builtin.glob({"path": str(tmp_path), "pattern": "*.py"})
    result = builtin.grep({
        "path": str(tmp_path),
        "pattern": "needle",
        "case_insensitive": True,
    })
    assert "a.txt:1:Needle" in result


def test_builtin_run_shell():
    result = builtin.run_shell({"command": "echo hello"})

    assert "[exit 0]" in result
    assert "hello" in result


def test_builtin_bash_session_persists_working_directory_and_env(tmp_path):
    registry = builtin.BashSessionRegistry()
    try:
        first = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "export MYVAR=hello && cd /tmp",
        }, config={"cwd": str(tmp_path), "max_output_bytes": 4096}))

        assert first["status"] == "completed"
        assert first["exit_code"] == 0

        second = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "echo $MYVAR && pwd",
        }, config={"cwd": str(tmp_path), "max_output_bytes": 4096}))

        assert "hello\n/tmp\n" in second["stdout"]
    finally:
        registry.close()


def test_builtin_bash_session_reports_command_local_output(tmp_path):
    registry = builtin.BashSessionRegistry()
    try:
        first = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "printf first",
        }, config={"cwd": str(tmp_path), "max_output_bytes": 4096}))

        assert first["stdout"] == "first"
        assert first["command_stdout"] == "first"

        second = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "printf second >&2",
        }, config={"cwd": str(tmp_path), "max_output_bytes": 4096}))

        assert second["stdout"] == "first"
        assert second["command_stdout"] == ""
        assert second["stderr"] == "second"
        assert second["command_stderr"] == "second"
    finally:
        registry.close()


def test_builtin_bash_session_per_command_env_does_not_persist(tmp_path):
    registry = builtin.BashSessionRegistry()
    try:
        first = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "echo $MYVAR",
            "env": {"MYVAR": "hello $USER"},
        }, config={"cwd": str(tmp_path), "max_output_bytes": 4096}))

        assert first["command_stdout"] == "hello $USER\n"

        second = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "echo $MYVAR",
        }, config={"cwd": str(tmp_path), "max_output_bytes": 4096}))

        assert second["command_stdout"] == "\n"

        with pytest.raises(ValueError, match="invalid bash_session env key"):
            registry.handle({
                "session_id": "s1",
                "command": "true",
                "env": {"BAD KEY": "value"},
            }, config={"cwd": str(tmp_path)})
    finally:
        registry.close()


def test_bash_session_cmd_env_escapes_shell_metacharacters():
    session = object.__new__(builtin.BashSession)
    session.shell_type = "cmd"
    session.shell = "cmd.exe"

    command = session._command_with_env("echo %MYVAR%", {"MYVAR": 'hello" & echo PWNED'})

    assert 'hello" & echo PWNED' not in command
    assert '^&' in command
    assert '^"' in command


def test_builtin_bash_session_timeout_status_and_kill(tmp_path):
    registry = builtin.BashSessionRegistry()
    try:
        running = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "sleep 5",
            "timeout_ms": 50,
        }, config={"cwd": str(tmp_path)}))

        assert running["status"] == "running"
        assert running["exit_code"] is None

        status = _bash_result(registry.handle({"session_id": "s1", "action": "status"}))
        assert status["status"] == "running"

        killed = _bash_result(registry.handle({"session_id": "s1", "action": "kill"}))
        assert killed["status"] == "killed"
    finally:
        registry.close()


def test_builtin_bash_session_truncates_and_strips_ansi(tmp_path):
    registry = builtin.BashSessionRegistry()
    try:
        result = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "printf '\\033[31m0123456789\\033[0m'",
        }, config={"cwd": str(tmp_path), "max_output_bytes": 5}))

        assert result["truncated"] is True
        assert result["stdout"] == "56789"
        assert "\x1b" not in result["stdout"]
    finally:
        registry.close()


def test_builtin_bash_session_nonzero_exit_is_tool_output(tmp_path):
    registry = builtin.BashSessionRegistry()
    try:
        result = _bash_result(registry.handle({
            "session_id": "s1",
            "command": "python3 -c 'import sys; sys.exit(7)'",
        }, config={"cwd": str(tmp_path)}))

        assert result["status"] == "completed"
        assert result["exit_code"] == 7
    finally:
        registry.close()


def test_builtin_bash_session_unknown_status_errors():
    registry = builtin.BashSessionRegistry()
    try:
        with pytest.raises(ValueError, match="unknown bash_session session_id"):
            registry.handle({"session_id": "missing", "action": "status"})
    finally:
        registry.close()


def test_builtin_fetch_url():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hello")

        def log_message(self, *_args):
            return

    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever)
        thread.daemon = True
        thread.start()
        try:
            result = builtin.fetch_url({"url": f"http://127.0.0.1:{server.server_address[1]}"})
        finally:
            server.shutdown()
            thread.join()

    assert "HTTP 200" in result
    assert "hello" in result


def test_builtin_fetch_url_strips_headers_on_cross_host_redirect():
    seen_headers: dict[str, str | None] = {}

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen_headers["target_authorization"] = self.headers.get("Authorization")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"redirected")

        def log_message(self, *_args):
            return

    with socketserver.TCPServer(("127.0.0.1", 0), Target) as target:
        target_thread = threading.Thread(target=target.serve_forever)
        target_thread.daemon = True
        target_thread.start()

        class Redirector(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen_headers["redirector_authorization"] = self.headers.get("Authorization")
                self.send_response(302)
                self.send_header("Location", f"http://localhost:{target.server_address[1]}/")
                self.end_headers()

            def log_message(self, *_args):
                return

        with socketserver.TCPServer(("127.0.0.1", 0), Redirector) as redirector:
            redirector_thread = threading.Thread(target=redirector.serve_forever)
            redirector_thread.daemon = True
            redirector_thread.start()
            try:
                result = builtin.fetch_url({
                    "url": f"http://127.0.0.1:{redirector.server_address[1]}/",
                    "headers": {"Authorization": "Bearer SECRET"},
                })
            finally:
                redirector.shutdown()
                redirector_thread.join()
                target.shutdown()
                target_thread.join()

    assert "HTTP 200" in result
    assert "redirected" in result
    assert seen_headers["redirector_authorization"] == "Bearer SECRET"
    assert seen_headers["target_authorization"] is None


def test_builtin_load_skill_strips_frontmatter(tmp_path):
    (tmp_path / "git_workflow.md").write_text(
        "---\nname: git_workflow\ndescription: Git conventions\n---\nWrite crisp PR descriptions.\n",
        encoding="utf-8",
    )

    result = builtin.load_skill({"name": "git_workflow"}, config={"skills_dir": str(tmp_path)})

    assert result == "Write crisp PR descriptions.\n"


def test_builtin_load_skill_rejects_invalid_names(tmp_path):
    with pytest.raises(RuntimeError, match="invalid skill name: foo-bar"):
        builtin.load_skill({"name": "foo-bar"}, config={"skills_dir": str(tmp_path)})


def test_builtin_fetch_url_rejects_unsupported_schemes():
    with pytest.raises(ValueError, match="only http"):
        builtin.fetch_url({"url": "file:///etc/passwd"})


def _bash_result(value):
    import json

    return json.loads(value)
