#!/usr/bin/env python3
"""Round-trip conformance runner.

Phase 1 runs a fixture and saves Session JSONL. Phase 2 loads that
JSONL, continues the Session, and compares the final Log to the
fixture's expected log.
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from harnas.conformance import runner  # noqa: E402
from harnas.session import Session  # noqa: E402


def _spec_root() -> str:
    if os.environ.get("HARNAS_SPEC"):
        return os.environ["HARNAS_SPEC"]
    sibling = os.path.abspath(os.path.join(HERE, "..", "..", "harnas"))
    if os.path.isdir(os.path.join(sibling, "conformance", "round-trips")):
        return sibling
    return os.path.abspath(os.path.join(HERE, "..", "..", "spec"))


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--phase", required=True, type=int, choices=(1, 2))
    parser.add_argument("--save")
    parser.add_argument("--load")
    parser.add_argument("--check")
    args = parser.parse_args()

    fixture_dir = os.path.join(_spec_root(), "conformance", "round-trips", args.fixture)
    manifest = _read_json(os.path.join(fixture_dir, "manifest.json"))
    script = _read_json(os.path.join(fixture_dir, f"phase-{args.phase}-provider-script.json"))
    inputs = _read_json(os.path.join(fixture_dir, f"phase-{args.phase}-inputs.json"))

    if args.phase == 1:
        if not args.save:
            parser.error("--save is required for phase 1")
        session = runner.run_session(manifest, script, inputs)
        session.save(args.save)
        print(f"saved {args.fixture} ({session.log.size} events)")
        return 0

    if not args.load:
        parser.error("--load is required for phase 2")
    if not args.check:
        parser.error("--check is required for phase 2")
    session = Session.load(args.load)
    session = runner.run_session(manifest, script, inputs, session=session)
    actual = runner._serialize_log(session.log)
    expected = runner._load_expected(args.check)
    diff = runner._first_mismatch(actual, expected)
    if diff:
        sys.stderr.write(f"round-trip mismatch at seq {diff['at_seq']}\n")
        sys.stderr.write("expected: " + json.dumps(diff["expected"], indent=2) + "\n")
        sys.stderr.write("actual: " + json.dumps(diff["actual"], indent=2) + "\n")
        return 1
    print(f"checked {args.fixture} ({len(actual)} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
