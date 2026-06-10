import json
import os
from pathlib import Path

from harnas.conformance import runner


def test_strict_diff_rejects_extra_actual_payload_fields():
    oracle = _spec_root() / "conformance" / "oracle-corpus" / "strict-diff-extra-payload-field"
    actual = _load_jsonl(oracle / "actual-log.jsonl")
    expected = _load_jsonl(oracle / "expected-log.jsonl")

    assert runner._first_mismatch(actual, expected) is not None


def _load_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _spec_root() -> Path:
    if os.environ.get("HARNAS_SPEC"):
        return Path(os.environ["HARNAS_SPEC"])
    sibling = Path(__file__).resolve().parents[2] / "harnas"
    if (sibling / "conformance" / "oracle-corpus").is_dir():
        return sibling
    raise RuntimeError("HARNAS_SPEC is required to locate conformance oracle corpus")
