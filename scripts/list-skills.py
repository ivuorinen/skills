#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""List all skills (and their commands, if any) with names and descriptions."""

import argparse
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import collect_skills

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
    desc_width = max(20, MAX_WIDTH - len(prefix))
    for name, description in skills:
        # wrap("") returns [] — fall back to one blank line so lines[0] is safe.
        lines = textwrap.wrap(description, width=desc_width) or [""]
        print(f"  {name:<{name_width}}  {lines[0]}")
        for line in lines[1:]:
            print(f"{prefix}{line}")
        print()


def collect_commands(skill_dir: Path) -> list[tuple[str, str]]:
    """Return (command, purpose) from a skill's commands/*.md files.

    The purpose is the first non-empty line after the h1.
    """
    results = []
    for cmd_md in sorted(skill_dir.glob("commands/*.md")):
        if cmd_md.name.startswith("_"):
            continue
        purpose = ""
        for line in cmd_md.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            purpose = line.strip()
            break
        results.append((cmd_md.stem, purpose or "(no purpose line)"))
    return results


def _parser() -> argparse.ArgumentParser:
    """The CLI. It had none, so `--help` printed the listing at exit 0 and an
    unknown flag was ignored; argparse answers `--help` and rejects the rest at
    exit 2 (audit-d73756b3)."""
    return argparse.ArgumentParser(
        prog="list-skills",
        description="List every skill (skills/ and .claude/skills/) and the public "
        "skills' commands, with names and descriptions. Takes no arguments.",
        epilog="Exit codes: 0 listed, 2 usage error.",
    )


def main(argv: list[str] | None = None) -> int:
    """Print the inventory `make list` shows, after parsing argv (none accepted)."""
    _parser().parse_args(argv)
    public = collect_skills(REPO_ROOT / "skills")
    private = collect_skills(REPO_ROOT / ".claude" / "skills")

    print(f"Skills in {REPO_ROOT.name}")
    print_section("Public  (skills/)", public)
    for skill_dir in sorted((REPO_ROOT / "skills").glob("*/")):
        commands = collect_commands(skill_dir)
        if commands:
            print_section(f"Commands (/{skill_dir.name} <command>)", commands)
    print_section("Private (.claude/skills/)", private)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
