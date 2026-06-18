import json
import os
from pathlib import Path

import pytest

from harnas.storage import (
    EventDraft,
    FileStorageAdapter,
    MemoryStorageAdapter,
    SessionHeader,
    StorageConflictError,
)


def spec_root() -> Path:
    return Path(os.environ.get("HARNAS_SPEC", Path(__file__).resolve().parents[2] / "harnas"))


def draft_from_dict(value: dict) -> EventDraft:
    return EventDraft(
        id=value["id"],
        timestamp=value["timestamp"],
        type=value["type"],
        payload=value["payload"],
    )


def assert_row(row, expected: dict) -> None:
    assert row.seq == expected["seq"]
    assert row.id == expected["id"]
    assert row.timestamp == expected["timestamp"]
    assert row.type == expected["type"]
    assert row.payload == expected["payload"]


def test_occ_conditional_append_law_fixture() -> None:
    law = json.loads((spec_root() / "conformance/storage-laws/occ-conditional-append/law.json").read_text())
    adapter = MemoryStorageAdapter()
    for operation in law["operations"]:
        if operation["op"] == "append_event":
            if operation["expect"]["ok"]:
                row = adapter.append_event(
                    draft_from_dict(operation["draft"]),
                    expected_next_seq=operation.get("expected_next_seq"),
                )
                assert_row(row, operation["expect"]["row"])
            else:
                with pytest.raises(StorageConflictError) as error:
                    adapter.append_event(
                        draft_from_dict(operation["draft"]),
                        expected_next_seq=operation.get("expected_next_seq"),
                    )
                assert error.value.reason == operation["expect"]["reason"]
                assert error.value.current_next_seq == operation["expect"]["current_next_seq"]
        elif operation["op"] == "events_since":
            rows = adapter.events_since(operation.get("cursor"))
            assert len(rows) == len(operation["expect"]["rows"])
            for row, expected in zip(rows, operation["expect"]["rows"], strict=True):
                assert_row(row, expected)
        else:
            raise AssertionError(f"unknown op {operation['op']}")


def test_file_storage_adapter_laws_s1_to_s8(tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    adapter = FileStorageAdapter(path)
    header = SessionHeader(id="ses_storage", metadata={"label": "storage"})
    adapter.save_header(header)
    assert adapter.load_session() == header

    row0 = adapter.append_event(EventDraft(
        id="evt_0",
        timestamp="2026-06-16T10:00:00Z",
        type="user_message",
        payload={"content": [{"type": "text", "text": "one"}]},
    ))
    assert row0.seq == 0
    row1 = FileStorageAdapter(path).append_event(EventDraft(
        id="evt_1",
        timestamp="2026-06-16T10:00:01Z",
        type="assistant_message",
        payload={"content": [{"type": "text", "text": "two"}]},
    ))
    assert row1.seq == 1
    assert [row.id for row in adapter.events_since(0)] == ["evt_1"]

    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"seq":')
    with pytest.raises(json.JSONDecodeError):
        FileStorageAdapter(path).events_since(None)
