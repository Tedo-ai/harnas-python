import hashlib
import json
import os
from pathlib import Path

import pytest

from harnas.jcs import InvalidUnicodeError, canonicalize_json, content_hash_json


def spec_root() -> Path:
    return Path(os.environ.get("HARNAS_SPEC", Path(__file__).resolve().parents[2] / "harnas"))


def test_jcs_v1_oracle_vectors() -> None:
    corpus = json.loads((spec_root() / "conformance/oracle-corpus/event-content-hash/vectors.json").read_text())
    for vector in corpus["valid"]:
        canonical = canonicalize_json(vector["input_json"], exclude_keys=vector.get("exclude_keys"))
        assert canonical == vector["expected_canonical"], vector["name"]
        assert hashlib.sha256(canonical.encode()).hexdigest() == vector["expected_content_hash"], vector["name"]


def test_jcs_v1_invalid_unicode() -> None:
    corpus = json.loads((spec_root() / "conformance/oracle-corpus/event-content-hash/vectors.json").read_text())
    for vector in corpus["invalid"]:
        with pytest.raises(InvalidUnicodeError, match=vector["expected_error"]):
            canonicalize_json(vector["input_json"])


def test_event_row_content_hash_excludes_self() -> None:
    root = spec_root() / "conformance/oracle-corpus/event-content-hash"
    row = (root / "event-row-with-content-hash.json").read_text()
    expected = (root / "expected-content-hash.txt").read_text().strip()
    assert content_hash_json(row) == expected
