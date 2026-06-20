import json
import os
from pathlib import Path
from typing import Any

import pytest

from harnas.ingestors.anthropic import Anthropic as AnthropicIngestor
from harnas.ingestors.gemini import Gemini as GeminiIngestor
from harnas.ingestors.openai import OpenAI as OpenAIIngestor
from harnas.log import Log
from harnas.projections.anthropic import Anthropic as AnthropicProjection
from harnas.projections.gemini import Gemini as GeminiProjection
from harnas.projections.openai import OpenAI as OpenAIProjection


def _spec_root() -> Path:
    if os.environ.get("HARNAS_SPEC"):
        return Path(os.environ["HARNAS_SPEC"])
    sibling = Path(__file__).resolve().parents[2] / "harnas"
    if (sibling / "conformance" / "provider-carriers").is_dir():
        return sibling
    raise RuntimeError("HARNAS_SPEC is required to locate provider-carrier fixtures")


def _carrier_fixtures() -> list[Path]:
    root = _spec_root() / "conformance" / "provider-carriers"
    return sorted(root.glob("*/fixture.json"))


@pytest.mark.parametrize("fixture_path", _carrier_fixtures(), ids=lambda p: p.parent.name)
def test_provider_carrier_fixtures(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    provider = fixture["provider"]
    projection = _projection(provider)
    ingestor = _ingestor(provider["kind"])

    ingested = ingestor(fixture["ingest"]["provider_response"])[0]
    assert ingested["type"] == fixture["ingest"]["expect_event"]["type"]
    if not ingested["payload"].get("model"):
        ingested["payload"]["model"] = provider["model"]
    assert ingested["payload"] == fixture["ingest"]["expect_event"]["payload"]

    request = projection(_log_from_rows(fixture["project"]["log"]))
    assert request == fixture["project"]["expect_request"]

    roundtrip = ingestor(_path_value(fixture, fixture["round_trip"]["reingest_response_path"]))[0]
    if not roundtrip["payload"].get("model"):
        roundtrip["payload"]["model"] = provider["model"]
    expected_payload = fixture["ingest"]["expect_event"]["payload"]
    for key in ("provider_items", "content", "reasoning"):
        if key in expected_payload:
            assert roundtrip["payload"].get(key) == expected_payload[key]


def _projection(provider: dict[str, Any]):
    match provider["kind"]:
        case "anthropic":
            return AnthropicProjection(model=provider["model"])
        case "openai":
            return OpenAIProjection(model=provider["model"])
        case "gemini":
            return GeminiProjection(model=provider["model"])
        case _:
            raise AssertionError(f"unsupported carrier provider {provider['kind']}")


def _ingestor(kind: str):
    match kind:
        case "anthropic":
            return AnthropicIngestor()
        case "openai":
            return OpenAIIngestor()
        case "gemini":
            return GeminiIngestor()
        case _:
            raise AssertionError(f"unsupported carrier provider {kind}")


def _log_from_rows(rows: list[dict[str, Any]]) -> Log:
    log = Log()
    for row in rows:
        log.append(type=row["type"], payload=row["payload"])
    return log


def _path_value(root: dict[str, Any], path: str) -> Any:
    value: Any = root
    for part in path.split("."):
        if "[" in part:
            name, index = part.rstrip("]").split("[", 1)
            value = value[name][int(index)]
        else:
            value = value[part]
    return value
