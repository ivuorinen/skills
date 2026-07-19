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
        try:
            matched = any(True for _ in repo_root.glob(pattern))
        except ValueError:
            # '**' adjacent to other chars in a path component raises ValueError on
            # CPython <3.13; report it as a bad pattern rather than crashing the run.
            # Mirrors the guard in skills/nitpicker/scripts/check-rules-anatomy.py.
            err(f"'paths:' glob is not a valid pattern: '{pattern}'")
            continue
        if not matched:
            warn(f"'paths:' glob matches no files — may be stale: '{pattern}'")

    if not body.strip():
        warn("body is empty after frontmatter")


# Two rules document enforcement that nothing checked. These close the halves
# that are mechanically checkable; they are repo-wide, so main() runs them only
# in whole-tree mode, not when a hook passes a single rule file.

# skill-official-best-practices.md, "No Time-Sensitive Content": a shipped skill
# body must not pin itself to a date. Only the date half is enforced — a bare
# X.Y.Z literal is indistinguishable from the WCAG success criteria, IP masks,
# and spec versions the command files legitimately cite, so flagging it would be
# noise rather than a gate.
_DATE_RE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")

# use-uv-runner.md, internal half: every internal dev script runs under uv.
_UV_SHEBANG = "#!/usr/bin/env -S uv run --quiet"
# Import-only modules, never executed directly — a shebang would be a lie.
_NO_SHEBANG_OK = {"common.py", "_hooklib.py"}


def check_repo_rules(repo_root: Path, errors: list[str]) -> None:
    for path in sorted(repo_root.glob("skills/**/*.md")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = _DATE_RE.search(line)
            if m:
                rel = path.relative_to(repo_root)
                errors.append(
                    f"  ERROR  {rel}:{lineno}: time-sensitive content — "
                    f"date literal {m.group()!r} in a shipped skill body"
                )

    for path in sorted(repo_root.glob("scripts/**/*.py")):
        if path.name in _NO_SHEBANG_OK:
            continue
        first = path.read_text(encoding="utf-8").split("\n", 1)[0]
        if first != _UV_SHEBANG:
            rel = path.relative_to(repo_root)
            errors.append(f"  ERROR  {rel}: first line must be '{_UV_SHEBANG}' (got {first!r})")


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
        check_repo_rules(repo_root, errors)
        rules_dir = repo_root / ".claude" / "rules"
        if not rules_dir.exists():
            sys.exit(1 if errors else 0)
        targets = _discover_targets(repo_root)

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
