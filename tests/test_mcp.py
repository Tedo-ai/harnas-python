import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from harnas import mcp
from harnas.mcp import content, tool_adapter


def test_content_flatten_samples():
    samples_path = os.path.join(os.path.dirname(__file__), "testdata", "mcp-content-samples.json")
    with open(samples_path, encoding="utf-8") as fh:
        samples = json.load(fh)

    for sample in samples:
        assert content.flatten(sample["content"]) == sample["expected"]


def test_tool_adapter_from_mcp():
    descriptor = tool_adapter.from_mcp({
        "name": "fetch_story",
        "description": "Fetch a story",
        "inputSchema": {"type": "object"},
    }, server_name="editorial-ai")

    assert descriptor == {
        "name": "editorial-ai.fetch_story",
        "description": "Fetch a story",
        "input_schema": {"type": "object"},
        "handler": "mcp_passthrough.editorial-ai",
        "config": {
            "mcp_server_name": "editorial-ai",
            "mcp_tool_name": "fetch_story",
        },
    }


def test_http_client_handshake_tools_call_and_headers():
    seen = {"auth": False}

    def handler(body, headers):
        if headers.get("Authorization") == "Bearer test":
            seen["auth"] = True
        request = json.loads(body)
        if request["method"] == "initialize":
            return 200, {"jsonrpc": "2.0", "id": request["id"], "result": {}}
        if request["method"] == "notifications/initialized":
            return 200, {"jsonrpc": "2.0", "result": {}}
        if request["method"] == "tools/list":
            return 200, {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {"tools": [{
                    "name": "fetch_story",
                    "description": "Fetch a story",
                    "inputSchema": {"type": "object"},
                }]},
            }
        if request["method"] == "tools/call":
            return 200, {
                "jsonrpc": "2.0",
                "id": request["id"],
                "result": {"content": [{"type": "text", "text": "story body"}]},
            }
        raise AssertionError(request["method"])

    with http_server(handler) as url:
        client = mcp.connect(
            server_name="editorial-ai",
            url=url,
            headers={"Authorization": "Bearer test"},
        )
        tools = client.tools()
        assert tools[0]["name"] == "editorial-ai.fetch_story"
        assert seen["auth"]
        assert client.call_tool("fetch_story", {"uid": "abc"}) == "story body"
        assert client.tool_handlers()["mcp_passthrough.editorial-ai"](
            {"uid": "abc"}, config={"mcp_tool_name": "fetch_story"}
        ) == "story body"


def test_http_client_errors_and_degraded_startup():
    with http_server(lambda _body, _headers: (500, "boom")) as url:
        client = mcp.HttpClient(url=url, server_name="bad")
        with pytest.raises(mcp.TransportError, match="HTTP 500"):
            client.initialize_session()
        assert client.tools() == []
        assert client.degraded is True
        with pytest.raises(mcp.TransportError, match="degraded state"):
            client.call_tool("x", {})

    with http_server(lambda _body, _headers: (200, "not-json")) as url:
        client = mcp.HttpClient(url=url, server_name="bad")
        with pytest.raises(mcp.TransportError, match="malformed JSON"):
            client.initialize_session()

    def slow(_body, _headers):
        time.sleep(0.1)
        return 200, {"jsonrpc": "2.0", "result": {}}

    with http_server(slow) as url:
        client = mcp.HttpClient(url=url, server_name="slow", timeout=0.01)
        with pytest.raises((mcp.TimeoutError, mcp.TransportError)):
            client.initialize_session()


def test_stdio_client_handshake_tools_and_call(tmp_path):
    script = fake_server(tmp_path, """
import json, sys
for line in sys.stdin:
    req=json.loads(line)
    if req["method"] == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":{}}), flush=True)
    elif req["method"] == "notifications/initialized":
        pass
    elif req["method"] == "tools/list":
        print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":{"tools":[{"name":"fetch_story","description":"Fetch a story","inputSchema":{"type":"object"}}]}}), flush=True)
    elif req["method"] == "tools/call":
        print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":{"content":[{"type":"text","text":"stdio body"}]}}), flush=True)
""")
    client = mcp.StdioClient(command=sys.executable, args=[str(script)], server_name="editorial-ai")
    try:
        assert client.tools()[0]["name"] == "editorial-ai.fetch_story"
        assert client.call_tool("fetch_story", {"uid": "abc"}) == "stdio body"
    finally:
        client.close()


def test_stdio_client_failures(tmp_path):
    with pytest.raises(mcp.StartupError):
        mcp.StdioClient(command="/definitely/not/harnas-mcp", args=[], server_name="bad")

    exits = fake_server(tmp_path, """
import json, sys
for line in sys.stdin:
    req=json.loads(line)
    if req["method"] == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":{}}), flush=True)
    elif req["method"] == "tools/list":
        sys.exit(0)
""")
    client = mcp.StdioClient(command=sys.executable, args=[str(exits)], server_name="bad")
    try:
        client.initialize_session()
        with pytest.raises(mcp.TransportError):
            client.list_tools()
    finally:
        client.close()

    slow = fake_server(tmp_path, """
import json, sys, time
for line in sys.stdin:
    req=json.loads(line)
    if req["method"] == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":req["id"],"result":{}}), flush=True)
    elif req["method"] == "tools/list":
        time.sleep(1)
""")
    client = mcp.StdioClient(command=sys.executable, args=[str(slow)], server_name="slow", timeout=0.2)
    try:
        client.initialize_session()
        with pytest.raises(mcp.TimeoutError):
            client.list_tools()
    finally:
        client.close()


def fake_server(tmp_path, source):
    path = tmp_path / "server.py"
    path.write_text(source, encoding="utf-8")
    return path


class http_server:
    def __init__(self, handler):
        self.handler = handler

    def __enter__(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length).decode("utf-8")
                status, response = outer.handler(body, self.headers)
                if isinstance(response, str):
                    encoded = response.encode("utf-8")
                else:
                    encoded = json.dumps(response).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, *_args):
                return None

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}/"

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.thread.join()
