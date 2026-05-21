#!/usr/bin/env python3
"""Conformance runner for source checkouts."""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from harnas.conformance import runner  # noqa: E402
from harnas.conformance.cli import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main(runner_module=runner))
