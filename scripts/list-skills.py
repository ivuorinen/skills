#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""List all skills with their names and descriptions."""

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import collect_skills  # noqa: E402  # type: ignore[import-not-found]

MAX_WIDTH = 100

REPO_ROOT = Path(__file__).parent.parent


def print_section(title: str, skills: list[tuple[str, str]]) -> None:
    print(f"\n{title}")
    print("─" * len(title))
    if not skills:
        print("  (none)")
        return
    name_width = max(len(name) for name, _ in skills)
    prefix = " " * (2 + name_width + 2)
    desc_width = MAX_WIDTH - len(prefix)
    for name, description in skills:
        lines = textwrap.wrap(description, width=desc_width)
        print(f"  {name:<{name_width}}  {lines[0]}")
        for line in lines[1:]:
            print(f"{prefix}{line}")
        print()


public = collect_skills(REPO_ROOT / "skills")
private = collect_skills(REPO_ROOT / ".claude" / "skills")

print(f"Skills in {REPO_ROOT.name}")
print_section("Public  (skills/)", public)
print_section("Private (.claude/skills/)", private)
print()
