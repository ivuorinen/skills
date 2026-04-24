"""Shared utilities for ivuorinen-skills scripts."""

from pathlib import Path


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse YAML frontmatter from a SKILL.md file.

    Returns (frontmatter_dict, body_text). Returns ({}, text) if no frontmatter found.
    """
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    fm: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            fm[k.strip()] = v.strip()
    return fm, text[end + 5 :]


def collect_skills(base: Path) -> list[tuple[str, str]]:
    """Return (name, description) for all skills under base, sorted by name."""
    results = []
    for skill_md in sorted(base.glob("*/SKILL.md")):
        fm, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = fm.get("name", skill_md.parent.name)
        description = fm.get("description", "(no description)")
        results.append((name, description))
    return results
