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
    ]:
        assert name in handlers


def test_builtin_descriptors_expose_canonical_tool_schemas():
    descriptors = builtin.descriptors()
    assert len(descriptors) == 8
    by_name = {descriptor["name"]: descriptor for descriptor in descriptors}
    for name in ["read_file", "write_file", "edit_file", "list_dir", "glob", "grep", "run_shell", "fetch_url"]:
        assert by_name[name]["handler"]
        assert by_name[name]["description"]
        assert by_name[name]["input_schema"]
    assert by_name["grep"]["input_schema"]["required"] == ["pattern", "path"]


def test_builtin_read_write_edit_file(tmp_path):
    path = tmp_path / "note.txt"
    result = builtin.write_file({"path": str(path), "content": "alpha\nbravo\n"})

    assert "12 bytes" in result
    assert builtin.read_file({"path": str(path)}) == "alpha\nbravo\n"
    builtin.edit_file({"path": str(path), "old_string": "bravo", "new_string": "BRAVO"})
    assert path.read_text(encoding="utf-8") == "alpha\nBRAVO\n"


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


def test_builtin_fetch_url_rejects_unsupported_schemes():
    with pytest.raises(ValueError, match="only http"):
        builtin.fetch_url({"url": "file:///etc/passwd"})
