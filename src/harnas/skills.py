"""Skills helpers for Markdown skills loaded through load_skill."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
INDEX_HEADER = "## Skills"
INDEX_GUARD = (
    "You have access to local skills. The skill index below is enough to answer "
    "what skills are available. Do not call `load_skill` just to list skills. "
    "Call `load_skill` only when a user request matches a skill and you need "
    "its full instructions."
)


def valid_name(name: str) -> bool:
    return bool(SKILL_NAME_RE.fullmatch(name))


def build_index(skills_dir: str) -> str:
    entries = skill_entries(skills_dir)
    if not entries:
        return ""
    lines = [INDEX_HEADER, "", INDEX_GUARD, ""]
    lines.extend(_format_entry(entry) for entry in entries)
    return "\n".join(lines)


def skill_entries(skills_dir: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted(Path(skills_dir).glob("*.md")):
        frontmatter, _body = parse_skill_file(path)
        name = str(frontmatter.get("name") or path.stem)
        if not valid_name(name) or name != path.stem:
            continue
        description = str(frontmatter.get("description") or "")
        if not description:
            continue
        triggers = frontmatter.get("triggers") or []
        if not isinstance(triggers, list):
            triggers = [str(triggers)]
        entries.append({
            "name": name,
            "description": description,
            "category": frontmatter.get("category"),
            "triggers": [str(trigger) for trigger in triggers],
        })
    return sorted(entries, key=lambda entry: entry["name"])


def parse_skill_file(path: str | Path) -> tuple[dict[str, Any], str]:
    content = Path(path).read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        return {}, content
    lines = content.splitlines(keepends=True)
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"),
        None,
    )
    if closing is None:
        return {}, content
    raw_frontmatter = "".join(lines[1:closing])
    body = "".join(lines[closing + 1:])
    return parse_frontmatter(raw_frontmatter), body


def parse_frontmatter(raw: str) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if current_list_key and stripped.startswith("- "):
            fields[current_list_key].append(stripped[2:].strip())
            continue
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not value:
            fields[key] = []
            current_list_key = key
        elif value.startswith("[") and value.endswith("]"):
            fields[key] = [
                item.strip()
                for item in value[1:-1].split(",")
                if item.strip()
            ]
            current_list_key = None
        else:
            fields[key] = value
            current_list_key = None
    return fields


def _format_entry(entry: dict[str, Any]) -> str:
    line = f"- `{entry['name']}`: {entry['description']}"
    category = str(entry.get("category") or "")
    if category:
        line += f" Category: {category}."
    triggers = [trigger for trigger in entry.get("triggers", []) if trigger]
    if triggers:
        line += f" Triggers: {', '.join(triggers)}."
    return line
