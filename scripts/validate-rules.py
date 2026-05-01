#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Validate .claude/rules/ files for structural correctness and glob freshness."""

import os
import re
import sys
from pathlib import Path


def parse_rules_frontmatter(text: str) -> tuple[dict | None, str]:
    """Parse optional YAML frontmatter from a rules file.

    Returns (frontmatter_dict, body_str). Returns ({}, text) if no frontmatter.
    Returns (None, text) if frontmatter is opened but never closed.
    """
    if not text.startswith("---\n"):
        return {}, text

    lines = text.splitlines(keepends=True)
    fm_lines: list[str] = []
    body_start: int | None = None

    for i, line in enumerate(lines[1:], start=1):
        if line in {"---\n", "---"}:
            body_start = i + 1
            break
        fm_lines.append(line)

    if body_start is None:
        return None, text  # signals parse failure

    fm_text = "".join(fm_lines)
    body = "".join(lines[body_start:])

    fm: dict = {}
    current_key: str | None = None
    current_list: list[str] | None = None

    for line in fm_text.splitlines():
        if line.startswith("  - ") and current_key is not None:
            item = line[4:].strip().strip("\"'")
            if current_list is None:
                current_list = []
                fm[current_key] = current_list
            current_list.append(item)
        elif ":" in line and not line.startswith(" "):
            current_list = None
            key, _, val = line.partition(":")
            current_key = key.strip()
            val = val.strip().strip("\"'")
            if val:
                fm[current_key] = val
        else:
            current_list = None

    return fm, body


KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def validate(path: Path, errors: list[str], warnings: list[str], repo_root: Path) -> None:
    def err(msg: str) -> None:
        errors.append(f"  ERROR  {path}: {msg}")

    def warn(msg: str) -> None:
        warnings.append(f"  WARN   {path}: {msg}")

    if path.is_symlink() and not path.exists():
        err("dangling symlink — rule file will not load")
        return

    if path.suffix != ".md":
        err(f"filename must have .md extension (got '{path.suffix}')")

    if not KEBAB_RE.match(path.stem):
        err(f"filename stem must be kebab-case (got '{path.stem}')")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        err(f"cannot read file: {e}")
        return

    if not text.strip():
        err("file is empty")
        return

    if not text.startswith("---\n"):
        # No frontmatter is valid — body is the whole file
        return

    fm, body = parse_rules_frontmatter(text)

    if fm is None:
        err("frontmatter block opened with '---' but never closed")
        return

    if "paths" not in fm:
        if not body.strip():
            warn("body is empty after frontmatter")
        return

    paths_val = fm["paths"]
    if not isinstance(paths_val, list):
        err("'paths:' must be a list of glob strings, not a scalar")
        return

    for pattern in paths_val:
        if pattern == "":
            err("'paths:' contains an empty glob string")
            continue
        if pattern.startswith("/"):
            err(f"'paths:' glob must be relative, not absolute: '{pattern}'")
            continue
        if ".." in Path(pattern).parts:
            err(f"'paths:' glob must not traverse outside repo root: '{pattern}'")
            continue
        matched = False
        for _ in repo_root.glob(pattern):
            matched = True
            break
        if not matched:
            warn(f"'paths:' glob matches no files — may be stale: '{pattern}'")

    if not body.strip():
        warn("body is empty after frontmatter")


def _iter_rules_dir(rules_dir: Path, seen: set[Path] | None = None) -> list[Path]:
    """Collect .md files and dangling symlinks from rules_dir recursively.

    Uses os.scandir instead of rglob so dangling symlinks are not silently skipped.
    Tracks resolved real paths to prevent symlink loop hangs.
    """
    if seen is None:
        seen = set()
    real_dir = rules_dir.resolve()
    if real_dir in seen:
        return []
    seen.add(real_dir)

    results: list[Path] = []
    with os.scandir(rules_dir) as it:
        for entry in it:
            p = Path(entry.path)
            if entry.is_symlink() and not p.exists():
                results.append(p)
            elif entry.is_dir(follow_symlinks=True):
                results.extend(_iter_rules_dir(p, seen))
            elif entry.name.endswith(".md"):
                results.append(p)
    return results


def _discover_targets(repo_root: Path) -> list[Path]:
    """Return sorted rule files (and dangling symlinks) under .claude/rules/."""
    rules_dir = repo_root / ".claude" / "rules"
    return sorted(_iter_rules_dir(rules_dir))


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    repo_root = Path(__file__).parent.parent

    if sys.argv[1:]:
        targets = [Path(a) for a in sys.argv[1:]]
    else:
        rules_dir = repo_root / ".claude" / "rules"
        if not rules_dir.exists():
            sys.exit(0)
        targets = _discover_targets(repo_root)

    if not targets:
        print("OK  0 rule(s) validated.")
        sys.exit(0)

    for t in targets:
        validate(t, errors, warnings, repo_root)

    if warnings:
        for w in warnings:
            print(w)

    if errors:
        for e in errors:
            print(e)
        print(f"\n{len(errors)} error(s). Fix before committing.")
        sys.exit(1)

    print(f"OK  {len(targets)} rule(s) validated.")


if __name__ == "__main__":
    main()
