#!/usr/bin/env python3
"""Run raw provider-wire conformance through the production parsers."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from harnas.conformance.provider_streams import run_provider_stream_corpus  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", default=os.environ.get("HARNAS_SPEC", "../harnas"))
    args = parser.parse_args()
    try:
        report = run_provider_stream_corpus(args.spec)
    except Exception as error:
        print(f"provider-wire conformance failed: {error}", file=sys.stderr)
        return 1
    print(
        f"{report.cases}/{report.cases} provider-wire cases; "
        f"{report.profiles} chunked executions passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
