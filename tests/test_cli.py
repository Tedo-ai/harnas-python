import json
from pathlib import Path

from harnas.cli import main
from harnas.session import Session


def write_manifest(path: Path) -> Path:
    manifest = {
        "harnas_version": "0.1",
        "name": "cli-test",
        "provider": {
            "kind": "mock",
            "model": "mock-test",
            "max_tokens": 1024,
        },
        "tools": [],
        "strategies": [],
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_inspect_json(tmp_path, capsys):
    session = Session(id="ses_json")
    session.log.append("user_message", {"text": "hello"})
    path = tmp_path / "session.jsonl"
    session.save(str(path))

    assert main(["inspect", str(path), "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["session"]["id"] == "ses_json"
    assert parsed["event_counts"] == {"user_message": 1}
    assert parsed["events"][0] == {
        "seq": 0,
        "type": "user_message",
        "summary": "hello",
    }


def test_fork_writes_prefix(tmp_path, capsys):
    session = Session(id="ses_parent", metadata={"label": "demo"})
    session.log.append("user_message", {"text": "hello"})
    session.log.append("assistant_message", {"text": "hi", "stop_reason": "end_turn", "usage": {}})
    session.log.append("user_message", {"text": "again"})
    source = tmp_path / "source.jsonl"
    target = tmp_path / "forked.jsonl"
    session.save(str(source))

    assert main(["fork", str(source), "--at-seq", "1", "--out", str(target)]) == 0
    forked = Session.load(str(target))

    assert "forked ses_parent at seq 1" in capsys.readouterr().out
    assert forked.id != session.id
    assert forked.metadata["forked_from"] == "ses_parent"
    assert forked.metadata["forked_at_seq"] == 1
    assert [event.id for event in forked.log] == [event.id for event in list(session.log)[:2]]


def test_diff_reports_match_and_difference(tmp_path, capsys):
    left = Session(id="ses_diff")
    left.log.append("user_message", {"text": "hello"})
    right = Session(id="ses_diff")
    right.log.append("user_message", {"text": "goodbye"})
    left_path = tmp_path / "left.jsonl"
    same_path = tmp_path / "same.jsonl"
    right_path = tmp_path / "right.jsonl"
    left.save(str(left_path))
    left.save(str(same_path))
    right.save(str(right_path))

    assert main(["diff", str(left_path), str(same_path)]) == 0
    assert "sessions match (1 events)" in capsys.readouterr().out

    assert main(["diff", str(left_path), str(right_path)]) == 3
    out = capsys.readouterr().out
    assert "sessions differ at seq 0" in out
    assert '"hello"' in out
    assert '"goodbye"' in out


def test_project_renders_provider_request(tmp_path, capsys):
    session = Session(id="ses_project")
    session.log.append("user_message", {"text": "hello"})
    session.log.append("assistant_message", {"text": "hi", "stop_reason": "end_turn", "usage": {}})
    session.log.append("user_message", {"text": "again"})
    session_path = tmp_path / "session.jsonl"
    session.save(str(session_path))
    manifest = write_manifest(tmp_path / "manifest.json")

    assert main(["project", str(session_path), "--manifest", str(manifest), "--to-seq", "1"]) == 0
    request = json.loads(capsys.readouterr().out)

    assert request["model"] == "mock-test"
    assert request["max_tokens"] == 1024
    assert request["messages"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_run_drives_agent_and_saves_session(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    manifest = write_manifest(tmp_path / "manifest.json")

    assert main(["run", str(manifest), "--input", "hello"]) == 0

    captured = capsys.readouterr()
    assert captured.out == "ok\n"
    assert "saved: " in captured.err
    saved = list(tmp_path.glob(".harnas/runs/*-cli-test.jsonl"))
    assert len(saved) == 1
    session = Session.load(str(saved[0]))
    assert [event.type for event in session.log] == ["user_message", "assistant_message"]


def test_chat_drives_agent_until_quit(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HOME", str(tmp_path))
    manifest = write_manifest(tmp_path / "manifest.json")
    inputs = iter(["hello", "quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))

    assert main(["chat", str(manifest)]) == 0

    captured = capsys.readouterr()
    assert "harnas chat · agent=cli-test" in captured.out
    assert "ok" in captured.out
    assert "saved: " in captured.err
