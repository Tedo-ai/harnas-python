#!/usr/bin/env python3
"""Check current README/status claims against package metadata and the spec."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    print(f"drift check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def spec_root() -> Path:
    explicit = os.environ.get("HARNAS_SPEC")
    if explicit and Path(explicit).is_dir():
        return Path(explicit)
    sibling = ROOT.parent / "harnas"
    if (sibling / "conformance" / "agents").is_dir():
        return sibling
    fail("set HARNAS_SPEC to a Harnas spec checkout")


def version_fields(root: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in (root / "VERSION").read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


def fixture_count(root: Path) -> int:
    agents = root / "conformance" / "agents"
    return sum(1 for path in agents.iterdir() if path.is_dir() and (path / "manifest.json").exists())


def package_version() -> str:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, flags=re.MULTILINE)
    if match is None:
        fail("could not read pyproject.toml version")
    return match.group(1)


def main() -> None:
    root = spec_root()
    fields = version_fields(root)
    spec_version = fields.get("harnas_version") or fail("spec VERSION has no harnas_version")
    fixtures_version = fields.get("fixtures_version") or fail("spec VERSION has no fixtures_version")
    count = fixture_count(root)
    version = package_version()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    if version != spec_version:
        fail(f"package version {version} does not match spec {spec_version}")
    required = [
        f"Passes {count}/{count} conformance",
        f"**Version {version}**",
        f"Tracks Harnas spec {spec_version}",
    ]
    for needle in required:
        if needle not in readme:
            fail(f"README does not contain {needle!r}")
    for stale in ("0.19.3", "70/70", "65/65"):
        if stale in readme:
            fail(f"README contains stale {stale}")

    print(f"drift ok: harnas-python {version}, fixtures v{fixtures_version}, {count} agent fixtures")


if __name__ == "__main__":
    main()
