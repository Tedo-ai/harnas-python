from harnas.ingestors.anthropic import Anthropic
from harnas.providers.mock import MockProvider
from harnas.projections.anthropic import Anthropic as AnthropicProjection
from harnas.session import Session
from harnas.strategies.compaction.summary_tail import SummaryTail
from harnas.strategies.compaction.token_marker_tail import TokenMarkerTail
from harnas.strategies.permission.always_allow import AlwaysAllow
from harnas.strategies.permission.human_approval import HumanApproval


def test_token_marker_tail_compacts_when_token_estimate_exceeds_threshold():
    session = Session.create()
    session.log.append("user_message", {"text": "one long message"})
    session.log.append("assistant_message", {
        "text": "two long message",
        "stop_reason": "end_turn",
        "usage": {},
    })
    session.log.append("user_message", {"text": "three long message"})

    TokenMarkerTail(max_tokens=1, threshold=1, keep_recent=1).on_pre_projection(session=session)

    assert session.log[-1].type == "compact"


def test_token_marker_tail_keeps_tool_pairs_together():
    session = Session.create()
    session.log.append("user_message", {"text": "hello"})
    tool = session.log.append("tool_use", {"id": "toolu_1", "name": "read", "arguments": {}})
    session.log.append("user_message", {"text": "tail"})

    TokenMarkerTail(max_tokens=1, threshold=1, keep_recent=1).on_pre_projection(session=session)

    assert session.log[-1].type == "compact"
    assert tool.seq not in session.log[-1].payload["replaces"]


def test_summary_tail_uses_provider_summary():
    session = Session.create()
    session.log.append("user_message", {"text": "one"})
    session.log.append("assistant_message", {
        "text": "two",
        "stop_reason": "end_turn",
        "usage": {},
    })
    session.log.append("user_message", {"text": "three"})
    strategy = SummaryTail(
        projection=AnthropicProjection(model="mock", max_tokens=128),
        provider=MockProvider(text="short summary"),
        ingestor=Anthropic(),
        max_messages=2,
        keep_recent=1,
    )

    strategy.on_pre_projection(session=session)

    assert session.log[-1].type == "compact"
    assert session.log[-1].payload["summary"] == "short summary"


def test_always_allow_returns_allow_decision():
    session = Session.create()
    AlwaysAllow.install(session)
    decisions = session.hooks.invoke(
        "pre_tool_use",
        tool_use=session.log.append("tool_use", {"id": "t1", "name": "read_file", "arguments": {}}),
    )

    assert decisions == [{"allow": True}]


def test_human_approval_allows_and_denies():
    allowed = Session.create()
    HumanApproval.install(allowed, prompt=lambda _tool_use: True)
    tool_use = allowed.log.append("tool_use", {"id": "t1", "name": "read_file", "arguments": {}})
    assert allowed.hooks.invoke("pre_tool_use", tool_use=tool_use) == [{"allow": True}]

    denied = Session.create()
    HumanApproval.install(denied, prompt=lambda _tool_use: False)
    tool_use = denied.log.append("tool_use", {"id": "t1", "name": "read_file", "arguments": {}})
    assert denied.hooks.invoke("pre_tool_use", tool_use=tool_use) == [
        {"allow": False, "reason": "human declined"}
    ]
