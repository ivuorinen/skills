#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Validate SKILL.md files for the ivuorinen-skills plugin."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import parse_frontmatter  # noqa: E402  # type: ignore[import-not-found]


def validate(path: Path, errors: list[str], warnings: list[str]) -> None:
    def err(msg: str) -> None:
        errors.append(f"  ERROR  {path}: {msg}")

    def warn(msg: str) -> None:
        warnings.append(f"  WARN   {path}: {msg}")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        err(f"cannot read file: {e}")
        return

    if not text.startswith("---\n"):
        err("missing YAML frontmatter (file must start with ---)")
        return

    fm, body = parse_frontmatter(text)

    name = fm.get("name", "")
    description = fm.get("description", "")

    if not name:
        err("frontmatter missing 'name' field")
    if not description:
        err("frontmatter missing 'description' field")
        return

    if not description.startswith("Use when"):
        err("description must start with 'Use when'")
    if len(description) > 500:
        err(f"description is {len(description)} chars; must be ≤500")

    end_fm = text.find("\n---\n", 4)
    for line in text[4:end_fm].splitlines():
        if line.startswith("description: "):
            raw_val = line[len("description: "):]
            if ": " in raw_val and not (raw_val.startswith("'") and raw_val.endswith("'")):
                err(
                    "description contains ': ' but is not quoted"
                    " — wrap in single quotes for yaml.v3 compatibility"
                )
            break

    expected_name = path.parent.name
    if name and name != expected_name:
        err(f"name '{name}' does not match directory '{expected_name}'")

    # Header level progression — no skipping levels (ignores fenced code blocks)
    headers: list[tuple[int, str]] = []
    in_fence = False
    for line in body.splitlines():
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
        if not in_fence and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            headers.append((level, line.lstrip("# ")))

    prev_level = 1  # body follows frontmatter; treat skill title (h1) as baseline
    for level, title in headers:
        if level > prev_level + 1:
            err(f"header level jumps from h{prev_level} to h{level}: '{'#' * level} {title}'")
        prev_level = level

    # Legacy output paths — scan prose and inline code, but skip fenced code blocks
    # (example/format documentation) and table rows (behavior documentation).
    body_no_doc = re.sub(r"```[\s\S]*?```", "", body)
    body_no_doc = re.sub(r"^\|.*\|$", "", body_no_doc, flags=re.MULTILINE)
    for legacy in ("./codereview.md", "./fixreport.md", "codereview.md", "fixreport.md"):
        if legacy in body_no_doc:
            warn(f"references legacy output path '{legacy}' — use docs/audit/ instead")


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    targets = [Path(a) for a in sys.argv[1:]] if sys.argv[1:] else []

    if not targets:
        repo_root = Path(__file__).parent.parent
        targets = sorted(repo_root.glob("skills/*/SKILL.md"))

    if not targets:
        print("No SKILL.md files found.")
        sys.exit(0)

    for t in targets:
        validate(t, errors, warnings)

    if warnings:
        for w in warnings:
            print(w)

    if errors:
        for e in errors:
            print(e)
        print(f"\n{len(errors)} error(s). Fix before committing.")
        sys.exit(1)

    print(f"OK  {len(targets)} skill(s) validated.")


if __name__ == "__main__":
    main()
