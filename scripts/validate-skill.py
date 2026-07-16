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

# Vendored skills — authored by someone else and installed into this repo (e.g.
# via `/graphify`), NOT held to our SKILL.md conventions. Skills named here are
# skipped by the validator (their descriptions, body length, etc. are their
# authors' concern, not ours).
#
# GOVERNANCE: this list is human-curated. It may contain ONLY vendored skills
# the repo owner has explicitly approved. An agent MUST NOT add an entry on its
# own — any skill not authored by us requires the owner's explicit confirmation
# before it goes here. `test_allowlist_contains_only_approved_entries` guards
# this; if it fails because of a new entry, that entry needs approval, not a
# test edit.
VENDORED_SKILLS: frozenset[str] = frozenset({"graphify"})


def filter_vendored(targets: list[Path]) -> tuple[list[Path], list[str]]:
    """Split SKILL.md targets into (validate, skipped-vendored-names).

    A target is vendored when its skill directory (the SKILL.md's parent) is
    named in VENDORED_SKILLS. Applies to both explicit args and auto-discovery,
    so an edited vendored SKILL.md is skipped rather than failing our checks.
    """
    kept: list[Path] = []
    skipped: list[str] = []
    for t in targets:
        if t.parent.name in VENDORED_SKILLS:
            skipped.append(t.parent.name)
        else:
            kept.append(t)
    return kept, skipped


def strip_fences(lines: list[str]) -> list[str]:
    """Return lines outside fenced code blocks.

    Handles indented fences and distinct markers: a block opened with ```
    is only closed by ```, and one opened with ~~~ only by ~~~.
    """
    result: list[str] = []
    fence = ""
    for line in lines:
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            continue
        if stripped.startswith(("```", "~~~")):
            fence = stripped[:3]
            continue
        result.append(line)
    return result


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

    text = text.replace("\r\n", "\n")  # normalize CRLF so frontmatter checks and slicing work

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
    else:
        if "Use when" not in description:
            err("description must contain 'Use when' trigger clause")
        if len(description) > 1024:
            err(f"description is {len(description)} chars; must be ≤1024")

    end_fm = text.find("\n---\n", 4)
    for line in text[4:end_fm].splitlines():
        if line.startswith("description: "):
            raw_val = line[len("description: ") :].strip()
            is_quoted = len(raw_val) >= 2 and raw_val[0] == "'" and raw_val[-1] == "'"
            if ": " in raw_val and not is_quoted:
                err("description contains ': ' — wrap in single quotes (project convention)")
            break

    expected_name = path.parent.name
    if name and name != expected_name:
        err(f"name '{name}' does not match directory '{expected_name}'")

    # Header level progression — no skipping levels (ignores fenced code blocks)
    headers: list[tuple[int, str]] = []
    for line in strip_fences(body.splitlines()):
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            headers.append((level, line.lstrip("# ")))

    prev_level = 1  # body follows frontmatter; treat skill title (h1) as baseline
    for level, title in headers:
        if level > prev_level + 1:
            err(f"header level jumps from h{prev_level} to h{level}: '{'#' * level} {title}'")
        prev_level = level

    # Duplicate headers — the same heading must not appear twice (ignores fenced code blocks)
    seen_headers: set[tuple[int, str]] = set()
    for level, title in headers:
        key = (level, title.strip())
        if key in seen_headers:
            err(f"duplicate header: '{'#' * level} {title.strip()}'")
        seen_headers.add(key)

    # Body length — official best-practices recommend ≤500 lines for optimal performance
    body_lines = len(body.splitlines())
    if body_lines > 500:
        warn(
            f"SKILL.md body is {body_lines} lines; "
            "official best-practices recommend ≤500 — split into separate files"
        )

    # Legacy output paths — scan prose and inline code, but skip fenced code blocks
    # (example/format documentation) and table rows (behavior documentation).
    body_no_doc = re.sub(r"```[\s\S]*?```", "", body)
    body_no_doc = re.sub(r"^\|.*\|$", "", body_no_doc, flags=re.MULTILINE)
    for legacy in ("./codereview.md", "./fixreport.md", "codereview.md", "fixreport.md"):
        if legacy in body_no_doc:
            warn(f"references legacy output path '{legacy}' — use docs/audit/ instead")

    commands_dir = path.parent / "commands"
    if commands_dir.is_dir():
        validate_commands(commands_dir, name or expected_name, body, errors)
    else:
        table_cmds = table_commands(body)
        if table_cmds:
            err(f"Commands table lists {len(table_cmds)} commands but commands/ does not exist")


_CMD_ROW = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|")


def table_commands(skill_body: str) -> set[str]:
    """Return command names listed in the SKILL.md Commands table."""
    cmds: set[str] = set()
    for line in strip_fences(skill_body.splitlines()):
        m = _CMD_ROW.match(line.strip())
        if m and m.group(1) != "command":
            cmds.add(m.group(1))
    return cmds


def validate_commands(
    commands_dir: Path, skill_name: str, skill_body: str, errors: list[str]
) -> None:
    """Cross-check the SKILL.md Commands table against commands/*.md files."""

    table_cmds = table_commands(skill_body)

    file_cmds = {p.stem: p for p in sorted(commands_dir.glob("*.md")) if not p.name.startswith("_")}

    for cmd in sorted(table_cmds - set(file_cmds)):
        errors.append(
            f"  ERROR  {commands_dir.parent / 'SKILL.md'}: Commands table lists `{cmd}` "
            f"but no commands/{cmd}.md exists"
        )
    for cmd in sorted(set(file_cmds) - table_cmds):
        errors.append(f"  ERROR  {file_cmds[cmd]}: not in the Commands table of SKILL.md")

    for cmd, cpath in file_cmds.items():

        def cerr(msg: str, cpath: Path = cpath) -> None:
            errors.append(f"  ERROR  {cpath}: {msg}")

        try:
            text = cpath.read_text(encoding="utf-8")
        except OSError as e:
            cerr(f"cannot read file: {e}")
            continue

        if text.startswith("---\n"):
            cerr("command files must not have YAML frontmatter (only the router SKILL.md does)")

        # All structural checks ignore fenced code blocks.
        content_lines = strip_fences(text.splitlines())

        first_header = next((ln for ln in content_lines if ln.startswith("#")), "")
        expected_h1 = f"# /{skill_name} {cmd} — "
        if not (first_header.startswith(expected_h1) and first_header[len(expected_h1) :].strip()):
            cerr(f"h1 must be '# /{skill_name} {cmd} — <Title>' (found {first_header!r})")

        h1_count = sum(1 for ln in content_lines if ln.startswith("#") and not ln.startswith("##"))
        if h1_count > 1:
            cerr(f"command file has {h1_count} h1 headers; exactly one allowed")

        if not any(ln.rstrip() == "## When to use" for ln in content_lines):
            cerr("missing '## When to use' section")

        prev_level = 0
        for line in content_lines:
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                if prev_level and level > prev_level + 1:
                    cerr(f"header level jumps from h{prev_level} to h{level}: {line!r}")
                prev_level = level


def main() -> None:
    errors: list[str] = []
    warnings: list[str] = []

    targets = [Path(a) for a in sys.argv[1:]] if sys.argv[1:] else []

    if not targets:
        repo_root = Path(__file__).parent.parent
        targets = sorted(
            [*repo_root.glob("skills/*/SKILL.md"), *repo_root.glob(".claude/skills/*/SKILL.md")]
        )

    targets, skipped = filter_vendored(targets)
    for name in skipped:
        print(f"  SKIP   {name} (vendored — not authored by us, not validated)")

    if not targets:
        if not skipped:
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
