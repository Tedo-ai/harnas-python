from pathlib import Path
import os

import pytest

from harnas.conformance.provider_streams import run_provider_stream_corpus


def test_provider_stream_fixtures() -> None:
    root = Path(os.environ.get("HARNAS_SPEC", "../harnas"))
    if not (root / "conformance" / "provider-streams" / "corpus.json").is_file():
        pytest.skip("provider-stream corpus is not present in this spec version")
    report = run_provider_stream_corpus(root)
    assert report.cases == 19
    assert report.profiles == 41
