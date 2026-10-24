#!/usr/bin/env python3
"""Check skill metadata, local Markdown links, and optional text exclusions."""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


def scalar(value):
    value = value.strip()
    if value.startswith('"'):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    return value


def field(text, name):
    match = re.search(r"^\s*" + re.escape(name) + r":\s*(.+)$", text, re.M)
    if not match:
        raise ValueError("Missing metadata field: " + name)
    return scalar(match.group(1))


def check(root, exclusions):
    errors = []
    try:
        entry = (root / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = re.match(r"\A---\n(.*?)\n---(?:\n|$)", entry, re.S)
        if not frontmatter:
            raise ValueError("SKILL.md must start with YAML frontmatter")
        name = field(frontmatter.group(1), "name")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
            raise ValueError("Invalid skill name")
        description = field(frontmatter.group(1), "description")
        if not isinstance(description, str) or not description.strip():
            raise ValueError("The skill description must be a nonempty string")
        if field(frontmatter.group(1), "license") != "MIT":
            raise ValueError("Skill license metadata must match the MIT release")
        interface = (root / "agents/openai.yaml").read_text(encoding="utf-8")
        if "$" + name not in field(interface, "default_prompt"):
            raise ValueError("The default prompt must invoke the declared skill")
        if not 25 <= len(field(interface, "short_description")) <= 64:
            raise ValueError("The interface description must contain 25 to 64 characters")
        if not (root / "LICENSE").is_file():
            raise ValueError("LICENSE is missing")
    except (OSError, ValueError, TypeError) as exc:
        errors.append(str(exc))

    files = sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and not any(part in {".git", "__pycache__", ".venv", "node_modules"}
                    for part in path.relative_to(root).parts)
    )
    link_count = 0
    for path in files:
        relative = path.relative_to(root)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for phrase in exclusions:
            if phrase.casefold() in content.casefold() or phrase.casefold() in str(relative).casefold():
                errors.append(str(relative) + ": excluded text found")
        if path.suffix != ".md":
            continue
        outside_fences = re.sub(r"```[^\n]*\n.*?```", "", content, flags=re.S)
        for href in re.findall(r"\[[^\]]*\]\(([^)]+)\)", outside_fences):
            parsed = urlsplit(href.strip("<>"))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            link_count += 1
            target = (path.parent / unquote(parsed.path)).resolve()
            if not target.exists():
                errors.append(str(relative) + ": missing local link " + href)

    if errors:
        for error in errors[:20]:
            print("ERROR:", error, file=sys.stderr)
        if len(errors) > 20:
            print("Additional errors:", len(errors) - 20, file=sys.stderr)
        return 1
    print("Validated skill metadata and", link_count, "local links across", len(files), "files.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--scan-text", action="append", default=[], metavar="TEXT")
    args = parser.parse_args()
    return check(args.root.resolve(), args.scan_text)


if __name__ == "__main__":
    sys.exit(main())
