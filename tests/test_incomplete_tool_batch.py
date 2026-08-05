from harnas.agent_loop import AgentLoop
from harnas.session import Session


class UnexpectedRunner:
    def run(self, *_args, **_kwargs):
        raise AssertionError("truncated tool call must not dispatch")


def test_complete_tool_call_under_max_tokens_is_closed_without_dispatch():
    session = Session.create()

    def ingestor(_response):
        return [
            {
                "type": "assistant_message",
                "payload": {"text": "", "stop_reason": "max_tokens", "usage": {}},
            },
            {
                "type": "tool_use",
                "payload": {"id": "toolu_truncated", "name": "echo", "arguments": {}},
            },
        ]

    reason = AgentLoop(
        session=session,
        projection=lambda _log: {"model": "test", "messages": []},
        provider=lambda _request: {},
        ingestor=ingestor,
        runner=UnexpectedRunner(),
    ).run()

    assert reason == "incomplete_tool_batch"
    result = next(event for event in session.log if event.type == "tool_result")
    assert result.payload["tool_use_id"] == "toolu_truncated"
    assert result.payload["error_class"] == "IncompleteToolResult"
    assert result.payload["reason"] == "incomplete_tool_result"
    assert result.payload["stop_reason"] == "max_tokens"
