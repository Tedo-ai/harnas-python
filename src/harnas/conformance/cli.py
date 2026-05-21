"""CLI helpers for running conformance from source or installed package."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def main(argv: list[str] | None = None, *, runner_module: Any) -> int:
    parser = argparse.ArgumentParser(prog="python -m harnas.conformance")
    parser.add_argument("--fixtures-from")
    parser.add_argument("fixtures", nargs="*")
    args = parser.parse_args(argv)
    spec_root = _resolve_spec_root(args.fixtures_from)
    fixtures_dir = _fixtures_dir(spec_root)

    if not os.path.isdir(fixtures_dir):
        sys.stderr.write(f"no fixtures directory at {fixtures_dir}\n")
        return 1

    if args.fixtures:
        names = args.fixtures
    else:
        names = sorted(
            n for n in os.listdir(fixtures_dir)
            if os.path.isdir(os.path.join(fixtures_dir, n))
        )

    if not names:
        sys.stderr.write("no fixtures to run\n")
        return 0

    results = []
    for name in names:
        dir_path = os.path.join(fixtures_dir, name)
        if not os.path.isdir(dir_path):
            sys.stderr.write(f"no such fixture: {name}\n")
            return 1
        try:
            results.append(runner_module.run(dir_path))
        except NotImplementedError as error:
            print(f"  -  {name}  SKIP ({error})")

    failed = 0
    for result in results:
        if result.passed:
            print(f"  ✓  {result.summary()}")
        else:
            failed += 1
            print(f"  ✗  {result.summary()}")
            print()
            print("    expected:")
            print("      " + json.dumps(result.diff["expected"], indent=2).replace("\n", "\n      "))
            print()
            print("    actual:")
            print("      " + json.dumps(result.diff["actual"], indent=2).replace("\n", "\n      "))
            print()

    version = runner_module.fixture_version(spec_root)
    suffix = f" against fixtures v{version}" if version else ""
    print()
    print(f"{len(results)} fixtures · {len(results) - failed} passed · {failed} failed{suffix}")
    return 1 if failed else 0


def _resolve_spec_root(explicit: str | None = None) -> str:
    if explicit:
        return os.path.abspath(explicit)
    if os.environ.get("HARNAS_SPEC"):
        return os.environ["HARNAS_SPEC"]
    here = os.path.dirname(os.path.abspath(__file__))
    sibling = os.path.abspath(os.path.join(here, "..", "..", "..", "..", "harnas"))
    if os.path.isdir(os.path.join(sibling, "conformance", "agents")):
        return sibling
    return os.path.abspath(os.path.join(here, "..", "..", "..", "..", "spec"))


def _fixtures_dir(spec_root: str) -> str:
    if spec_root.endswith(os.path.join("conformance", "agents")):
        return spec_root
    return os.path.join(spec_root, "conformance", "agents")
