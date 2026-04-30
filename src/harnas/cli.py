"""Small persisted-Session CLI for the Python Harnas port."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .log import Log
from .projections.anthropic import Anthropic
from .projections.gemini import Gemini
from .projections.openai import OpenAI
from .session import Session
from .tools.registry import Registry
from .tools.tool import Tool

EXIT_SUCCESS = 0
EXIT_USAGE = 1
EXIT_DIFFERENT = 3


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        match args.command:
            case "diff":
                return command_diff(args.left, args.right)
            case "fork":
                return command_fork(args.session, args.at_seq, args.out)
            case "inspect":
                return command_inspect(args.session, args.json)
            case "project":
                return command_project(args)
            case _:
                parser.print_usage(sys.stderr)
                return EXIT_USAGE
    except (OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harnas")
    subparsers = parser.add_subparsers(dest="command")

    diff = subparsers.add_parser("diff", help="compare two Session JSONL files")
    diff.add_argument("left")
    diff.add_argument("right")

    fork = subparsers.add_parser("fork", help="write a forked Session JSONL file")
    fork.add_argument("session")
    fork.add_argument("--at-seq", type=int, required=True)
    fork.add_argument("--out", required=True)

    inspect = subparsers.add_parser("inspect", help="summarize a Session JSONL file")
    inspect.add_argument("session")
    inspect.add_argument("--json", action="store_true")

    project = subparsers.add_parser("project", help="render a provider request from a Log slice")
    project.add_argument("session")
    project.add_argument("--manifest", required=True)
    project.add_argument("--from-seq", type=int)
    project.add_argument("--to-seq", type=int)
    project.add_argument("--provider")
    project.add_argument("--model")

    return parser


def command_inspect(path: str, as_json: bool) -> int:
    summary = inspect_session(Session.load(path))
    if as_json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(format_inspection(summary), end="")
    return EXIT_SUCCESS


def inspect_session(session: Session) -> dict[str, Any]:
    events = list(session.log)
    return {
        "session": {
            "id": session.id,
            "metadata": session.metadata,
            "event_count": len(events),
            "first_seq": events[0].seq if events else None,
            "last_seq": events[-1].seq if events else None,
        },
        "event_counts": event_counts(events),
        "events": [inspect_event(event) for event in events],
    }


def event_counts(events: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        counts[event.type] = counts.get(event.type, 0) + 1
    return dict(sorted(counts.items()))


def inspect_event(event: Any) -> dict[str, Any]:
    return {"seq": event.seq, "type": event.type, "summary": event_summary(event)}


def event_summary(event: Any) -> str:
    payload = event.payload
    match event.type:
        case "user_message" | "assistant_message" | "summary":
            return truncate(str(payload.get("text", "")))
        case "tool_use":
            args = json.dumps(payload.get("arguments", {}), ensure_ascii=False, separators=(",", ":"))
            return f"{payload.get('name')} {args}"
        case "tool_result":
            if payload.get("error"):
                return f"error for {payload.get('tool_use_id')}: {truncate(payload.get('error'))}"
            return f"ok for {payload.get('tool_use_id')}: {truncate(payload.get('output'))}"
        case "provider_error":
            return f"{payload.get('provider')} {payload.get('status') or 'error'} {payload.get('message')}"
        case "compact":
            return f"replaces={payload.get('replaces')} {truncate(payload.get('summary'))}"
        case "revert":
            return f"revokes={payload.get('revokes')}"
        case _:
            return truncate(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def format_inspection(summary: dict[str, Any]) -> str:
    session = summary["session"]
    lines = [
        f"session {session['id']}",
        f"metadata {json.dumps(session['metadata'], ensure_ascii=False, separators=(',', ':'))}",
        f"events {session['event_count']} seq={session['first_seq']!r}..{session['last_seq']!r}",
        f"counts {json.dumps(summary['event_counts'], ensure_ascii=False, separators=(',', ':'))}",
        "",
    ]
    for event in summary["events"]:
        lines.append(f"{str(event['seq']).rjust(4)}  {event['type'].ljust(26)}  {event['summary']}")
    return "\n".join(lines) + "\n"


def command_fork(path: str, at_seq: int, out: str) -> int:
    session = Session.load(path)
    forked = session.fork(at_seq)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    forked.save(str(target))
    print(f"forked {session.id} at seq {at_seq} -> {out} ({forked.log.size} events)")
    return EXIT_SUCCESS


def command_diff(left_path: str, right_path: str) -> int:
    left = comparable_rows(Session.load(left_path))
    right = comparable_rows(Session.load(right_path))
    if left == right:
        print(f"sessions match ({len(left) - 1} events)")
        return EXIT_SUCCESS

    index = next(idx for idx in range(max(len(left), len(right))) if row_at(left, idx) != row_at(right, idx))
    print(f"sessions differ at {diff_label(index)}")
    print(f"left:  {format_row(row_at(left, index))}")
    print(f"right: {format_row(row_at(right, index))}")
    return EXIT_DIFFERENT


def comparable_rows(session: Session) -> list[dict[str, Any]]:
    return [
        {"session": {"id": session.id, "metadata": session.metadata}},
        *[
            {
                "seq": event.seq,
                "id": event.id,
                "type": event.type,
                "payload": event.payload,
            }
            for event in session.log
        ],
    ]


def row_at(rows: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
    return rows[index] if index < len(rows) else None


def diff_label(index: int) -> str:
    return "session header" if index == 0 else f"seq {index - 1}"


def format_row(row: dict[str, Any] | None) -> str:
    if row is None:
        return "<missing>"
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))


def command_project(args: argparse.Namespace) -> int:
    session = Session.load(args.session)
    manifest = load_manifest(args.manifest, provider=args.provider, model=args.model)
    projection = build_projection(manifest)
    request = projection(slice_log(session.log, args.from_seq, args.to_seq))
    print(json.dumps(request, indent=2, ensure_ascii=False))
    return EXIT_SUCCESS


def load_manifest(path: str, provider: str | None, model: str | None) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    spec = manifest["provider"]
    if provider:
        spec["kind"] = provider
    if model:
        spec["model"] = model
    return manifest


def build_projection(manifest: dict[str, Any]) -> Any:
    provider = manifest["provider"]
    registry = build_registry(manifest.get("tools", []))
    system = manifest.get("system")
    match provider["kind"]:
        case "mock" | "anthropic":
            return Anthropic(
                model=provider["model"],
                max_tokens=provider.get("max_tokens", Anthropic.DEFAULT_MAX_TOKENS),
                registry=registry,
                system=system,
            )
        case "openai":
            return OpenAI(model=provider["model"], registry=registry, system=system)
        case "gemini":
            return Gemini(
                model=provider["model"],
                registry=registry,
                system=system,
                thinking_budget=provider.get("thinking_budget", 0),
            )
        case _:
            raise ValueError(f"unknown provider kind: {provider['kind']!r}")


def build_registry(tools: list[dict[str, Any]]) -> Registry:
    registry = Registry()
    for tool in tools:
        registry.register(Tool(
            name=tool["name"],
            description=tool["description"],
            input_schema=tool["input_schema"],
            handler=lambda _args: "",
        ))
    return registry


def slice_log(log: Log, from_seq: int | None, to_seq: int | None) -> Log:
    start = 0 if from_seq is None else from_seq
    end = log.size - 1 if to_seq is None else to_seq
    if start < 0:
        raise ValueError("--from-seq must be non-negative")
    if end < start:
        raise ValueError("--to-seq must be >= --from-seq")

    sliced = Log()
    for event in log:
        if start <= event.seq <= end:
            sliced._events.append(event)
    return sliced


def truncate(value: Any, limit: int = 96) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[:limit - 1]}..."


if __name__ == "__main__":
    raise SystemExit(main())
