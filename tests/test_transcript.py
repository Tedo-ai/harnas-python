from harnas.log import Log
from harnas import transcript


def test_project_messages_tools_and_errors():
    log = Log()
    log.append("user_message", {"text": "hello"})
    log.append("assistant_message", {"text": "", "stop_reason": "tool_use", "usage": {}})
    log.append("tool_use", {"id": "call_1", "name": "read_file", "arguments": {"path": "README.md"}})
    log.append("tool_result", {"tool_use_id": "call_1", "output": "body", "error": None})
    log.append("provider_error", {"message": "rate limited", "terminal": True})

    items = transcript.project(log)

    assert [item["kind"] for item in items] == [
        "user",
        "assistant",
        "tool_use",
        "tool_result",
        "provider_error",
    ]
    assert items[2]["name"] == "read_file"
    assert items[3]["status"] == "ok"
    assert items[4]["error"] == "rate limited"


def test_project_can_hide_tools():
    log = Log()
    log.append("tool_use", {"id": "call_1", "name": "grep", "arguments": {}})

    assert transcript.project(log, include_tools=False) == []


def test_project_renders_content_blocks():
    log = Log()
    log.append("user_message", {"content": [
        {"type": "text", "text": "see this"},
        {
            "type": "image",
            "media_type": "image/png",
            "name": "chart.png",
            "source": {"kind": "base64", "data": "aW1n"},
        },
    ]})

    assert transcript.project(log)[0]["text"] == "see this\n[image: chart.png: image/png: 3 bytes]"


def test_project_accepts_custom_content_placeholder():
    log = Log()
    log.append("user_message", {"content": [{"type": "document", "media_type": "application/pdf"}]})

    items = transcript.project(log, content_placeholder=lambda _block: "[attachment]")

    assert items[0]["text"] == "[attachment]"
