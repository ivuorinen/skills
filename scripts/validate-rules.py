#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Validate .claude/rules/ files for structural correctness and glob freshness."""

import importlib.util
import re
import sys
from pathlib import Path

# Single source of truth for the frontmatter parser and the symlink-safe rules
# walker: the shipped, stdlib-only check-rules-anatomy.py. Internal tooling
# depending on the shipped tool points the dependency the safe direction (the
# shipped tool can never import back into scripts/). Loaded by path because the
# module name contains hyphens and cannot be `import`ed by name.
_ANATOMY_PATH = (
    Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "check-rules-anatomy.py"
)
_spec = importlib.util.spec_from_file_location("check_rules_anatomy", _ANATOMY_PATH)
_anatomy = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_anatomy)  # type: ignore[union-attr]

# Re-exported so callers (and tests) keep importing it from this module.
parse_rules_frontmatter = _anatomy._parse_frontmatter


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


def _discover_targets(repo_root: Path) -> list[Path]:
    """Return sorted rule files (and dangling symlinks) under .claude/rules/.

    Uses the shipped tool's symlink-safe walker (returns sorted) as the single
    source of truth, so the two validators can never disagree on discovery.
    """
    rules_dir = repo_root / ".claude" / "rules"
    return _anatomy._iter_rules(rules_dir)


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
