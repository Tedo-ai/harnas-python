"""Run Harnas conformance fixtures from an installed package."""

from __future__ import annotations

import sys

from . import runner
from .cli import main


if __name__ == "__main__":
    sys.exit(main(runner_module=runner))
