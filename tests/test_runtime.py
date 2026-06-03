from harnas.runtime import Runtime, default_attachment_root
from harnas.session import Session
import pytest


def manifest():
    return {
        "harnas_version": "0.1",
        "name": "runtime-test",
        "provider": {"kind": "mock", "model": "mock-test", "max_tokens": 128},
        "tools": [],
        "strategies": [],
    }


def test_runtime_builds_agent_with_metadata():
    runtime = Runtime.build(manifest=manifest(), metadata={"trace_id": "tr_1"})

    response = runtime.agent().chat("hi")

    assert response.text == "ok"
    assert runtime.session.metadata["trace_id"] == "tr_1"


def test_runtime_resumes_saved_session(tmp_path):
    session = Session.create()
    session.log.append("user_message", {"text": "old"})
    path = tmp_path / "session.jsonl"
    session.save(str(path))

    runtime = Runtime.build(manifest=manifest(), session_path=str(path), resume=True)

    assert runtime.session.id == session.id
    assert [event.payload["text"] for event in runtime.session.log] == ["old"]


def test_default_attachment_root_uses_session_path():
    assert default_attachment_root("/tmp/run.jsonl") == "/tmp/run.attachments"


def test_session_delegation_metadata_round_trips(tmp_path):
    session = Session(
        id="ses_child",
        metadata={"label": "child"},
        parent_session_id="ses_parent",
        root_session_id="ses_root",
        spawn_id="spn_1",
        spawned_by_event_id="evt_2_abc",
        delegation_chain=[
            {"session_id": "ses_root", "spawn_id": None},
            {"session_id": "ses_parent", "spawn_id": "spn_parent"},
        ],
    )
    path = tmp_path / "session.jsonl"
    session.save(str(path))

    loaded = Session.load(str(path))

    assert loaded.parent_session_id == "ses_parent"
    assert loaded.root_session_id == "ses_root"
    assert loaded.spawn_id == "spn_1"
    assert loaded.spawned_by_event_id == "evt_2_abc"
    assert loaded.delegation_chain[-1] == {
        "session_id": "ses_parent",
        "spawn_id": "spn_parent",
    }


def test_session_load_fails_loudly_on_torn_final_event_row(tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text(
        '\n'.join([
            '{"__session__":true,"id":"ses_test","metadata":{}}',
            '{"seq":0,"id":"evt_0","timestamp":"2026-06-01T00:00:00Z","type":"user_message","payload":{"text":"a"}}',
        ])
        + '\n{"seq":1,"id":"evt_1","timestamp":"2026-06-01T00:00:01Z","type":"user_message","payload":{"text":"b"}',
        encoding="utf-8",
    )

    with pytest.raises(Exception):
        Session.load(str(path))


@pytest.mark.parametrize(
    "rows",
    [
        [
            '{"seq":0,"id":"evt_0","timestamp":"2026-06-01T00:00:00Z","type":"user_message","payload":{"text":"a"}}',
            '{"seq":0,"id":"evt_dup","timestamp":"2026-06-01T00:00:01Z","type":"user_message","payload":{"text":"b"}}',
        ],
        [
            '{"seq":0,"id":"evt_0","timestamp":"2026-06-01T00:00:00Z","type":"user_message","payload":{"text":"a"}}',
            '{"seq":2,"id":"evt_2","timestamp":"2026-06-01T00:00:01Z","type":"user_message","payload":{"text":"b"}}',
        ],
        [
            '{"seq":1,"id":"evt_1","timestamp":"2026-06-01T00:00:00Z","type":"user_message","payload":{"text":"a"}}',
            '{"seq":0,"id":"evt_0","timestamp":"2026-06-01T00:00:01Z","type":"user_message","payload":{"text":"b"}}',
        ],
    ],
)
def test_session_load_rejects_duplicate_gapped_and_reordered_seq_rows(tmp_path, rows):
    path = tmp_path / "session.jsonl"
    path.write_text(
        '\n'.join(['{"__session__":true,"id":"ses_test","metadata":{}}', *rows]) + '\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid event seq"):
        Session.load(str(path))
