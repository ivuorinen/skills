#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Verify the Makefile and `make help` describe the same set of targets.

`make help` is a hand-maintained block of `@echo` lines, so it is a second copy
of a list the Makefile already holds — and it drifts the way every second copy
does. It drifted here: `typecheck` was a target `make check` depends on and
`make help` did not mention it, so the only surface that documents the commands
omitted one of them.

Three checks, all deterministic because both lists are in one file:

    a target absent from help   — a command nobody can discover
    a help entry with no target — `make <it>` fails for anyone who tries
    a target absent from .PHONY — Make skips a target whose name matches a real
                                  file, silently, and the gate stops running

`help` and `all` are exempt: `help` documenting itself is noise, and `all` is
the conventional default alias rather than a command a reader looks up.

Exits 1 on any drift, 0 when the two agree, 2 on a usage error.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
_EXEMPT = {"help", "all"}

# `foo:` at column 0, not `foo := value`.
_TARGET_RE = re.compile(r"^([a-z][a-z0-9_-]*):(?!=)", re.M)
# The recipe lines of `help`, which look like: @echo "  name  — description"
_HELP_ENTRY_RE = re.compile(r'@echo\s+"\s+([a-z][a-z0-9_-]*)\s')
_PHONY_RE = re.compile(r"^\.PHONY:\s*(.+)$", re.M)


def read_makefile(path: Path) -> tuple[set[str], set[str], set[str]]:
    """(targets, help entries, .PHONY names) parsed from one Makefile.

    The help block is taken as the lines from `help:` to the next blank line —
    the recipe itself. Scanning the whole file for `@echo` would collect every
    other target's output as though it were a help entry.
    """
    text = path.read_text(encoding="utf-8")
    targets = {m.group(1) for m in _TARGET_RE.finditer(text)}

    # Prefixed with a newline so `help:` is found as the first line too. Without
    # it the search misses a Makefile that opens with the help target, no help
    # entries are collected, and every target is reported as undocumented — a
    # confident wrong answer rather than an error.
    prefixed = "\n" + text
    help_body = ""
    if "\nhelp:" in prefixed:
        help_body = prefixed.split("\nhelp:", 1)[1].split("\n\n", 1)[0]
    listed = set(_HELP_ENTRY_RE.findall(help_body))

    phony: set[str] = set()
    for m in _PHONY_RE.finditer(text):
        phony.update(m.group(1).split())
    return targets, listed, phony


def drift(targets: set[str], listed: set[str], phony: set[str]) -> list[str]:
    """Every disagreement between the three sets, as reportable lines."""
    problems = []
    for name in sorted(targets - listed - _EXEMPT):
        problems.append(f"target '{name}' is not listed in `make help` — nobody can discover it")
    for name in sorted(listed - targets):
        problems.append(f"`make help` lists '{name}', which is not a target — `make {name}` fails")
    for name in sorted(targets - phony - _EXEMPT):
        problems.append(
            f"target '{name}' is missing from .PHONY — Make skips it silently "
            f"if a file of that name ever appears"
        )
    return problems


def main() -> None:
    """CLI entry point: parse argv, report drift, exit per the outcome."""
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return
    if len(sys.argv) > 2:
        print("Usage: check-make-help.py [<makefile>]", file=sys.stderr)
        sys.exit(2)

    path = Path(sys.argv[1]) if sys.argv[1:] else REPO_ROOT / "Makefile"
    try:
        targets, listed, phony = read_makefile(path)
    except OSError as e:
        print(f"ERROR  cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)

    problems = drift(targets, listed, phony)
    if problems:
        for p in problems:
            print(f"  MISMATCH  {p}")
        print(f"\n{len(problems)} target/help mismatch(es) in {path.name}.")
        sys.exit(1)

    print(f"OK  {len(targets)} target(s); `make help` and .PHONY agree.")


if __name__ == "__main__":
    main()
