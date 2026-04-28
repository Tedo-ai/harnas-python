#!/usr/bin/env python3
"""Conformance runner — replays every fixture under
spec/conformance/agents/ against the Python port.

Mirrors `reference/bin/conformance.rb`. Run from the repo root or
the python/ directory; resolves the fixtures path relative to this
script.

Usage:
  python bin/conformance.py              # run all fixtures
  python bin/conformance.py minimal-chat # run one
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from harnas.conformance import runner  # noqa: E402

# Resolution order for the Harnas spec's conformance fixtures:
#   1. HARNAS_SPEC env var pointing at a checkout of Tedo-ai/harnas
#   2. ../harnas/conformance/agents (sibling clone — the recommended layout)
#   3. ../../spec/conformance/agents (monorepo internal layout)
def _resolve_fixtures_dir() -> str:
    if os.environ.get("HARNAS_SPEC"):
        return os.path.join(os.environ["HARNAS_SPEC"], "conformance", "agents")
    sibling = os.path.abspath(os.path.join(HERE, "..", "..", "harnas", "conformance", "agents"))
    if os.path.isdir(sibling):
        return sibling
    return os.path.abspath(os.path.join(HERE, "..", "..", "spec", "conformance", "agents"))


FIXTURES_DIR = _resolve_fixtures_dir()


def main() -> int:
    if not os.path.isdir(FIXTURES_DIR):
        sys.stderr.write(f"no fixtures directory at {FIXTURES_DIR}\n")
        return 1

    if len(sys.argv) > 1:
        names = sys.argv[1:]
    else:
        names = sorted(
            n for n in os.listdir(FIXTURES_DIR)
            if os.path.isdir(os.path.join(FIXTURES_DIR, n))
        )

    if not names:
        sys.stderr.write("no fixtures to run\n")
        return 0

    results = []
    for name in names:
        dir_path = os.path.join(FIXTURES_DIR, name)
        if not os.path.isdir(dir_path):
            sys.stderr.write(f"no such fixture: {name}\n")
            return 1
        try:
            results.append(runner.run(dir_path))
        except NotImplementedError as e:
            print(f"  -  {name}  SKIP ({e})")

    failed = 0
    for r in results:
        if r.passed:
            print(f"  ✓  {r.summary()}")
        else:
            failed += 1
            print(f"  ✗  {r.summary()}")
            print()
            print("    expected:")
            print("      " + json.dumps(r.diff["expected"], indent=2).replace("\n", "\n      "))
            print()
            print("    actual:")
            print("      " + json.dumps(r.diff["actual"], indent=2).replace("\n", "\n      "))
            print()

    print()
    print(f"{len(results)} fixtures · {len(results) - failed} passed · {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
