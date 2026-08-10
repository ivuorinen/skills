#!/usr/bin/env python3
"""One-shot patch: split _writes_protected so each half states one thing.

`scripts/hooks/` is under permissions.deny for the Edit/Write tools. Delete this
file once applied.

    python3 docs/audit/apply-cr-round3.py --check
    python3 docs/audit/apply-cr-round3.py

Codacy reports `_writes_protected` at cyclomatic complexity 12 against a limit
of 10. The function grew that way honestly — the unscoped-worktree arm was
bolted onto a body that already handled redirections, operands and `cd` bases —
and it now does three separable things in one scope.

Context worth recording: this repo does not enforce a complexity limit. `C901`
is absent from `[tool.ruff.lint] select`, and running it by hand reports far
worse pre-existing functions (`validate` at 20 and 30, `_check_file` at 25,
`validate_file` at 26). Codacy flags this one only because it is new. The split
is taken on its own merits rather than because 12 is a meaningful threshold: the
redirection scan and the per-stage decision each read better named than inline.

Behaviour is unchanged — same predicates, same order, same short-circuits.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "hooks" / "deny-agents-path-hook.py"

EDITS: list[tuple[str, str, str]] = [
    (
        "guard: split _writes_protected into named halves",
        '''def _writes_protected(command: str) -> bool:
    """True if the command writes to scripts/hooks/ or .claude/settings.json."""
    c = _canonicalize(command)
    for match in _REDIR_RE.finditer(c):
        if _token_writes_protected(match.group(1), c):
            return True
    stages = [t for t in shell_stages(c) if _stage_is_mutating(t)]
    if not stages:
        return False
    for tokens in stages:
        # An unscoped worktree rewrite reaches the protected paths without ever
        # naming them, so no operand check below would catch it.
        if PurePosixPath(tokens[0]).name == "git" and _git_rewrites_worktree(tokens):
            return True
        if any(_token_writes_protected(a, c) for a in tokens[1:]):
            return True
    # `cd scripts/hooks && sed -i s/a/b/ ruff-hook.py` — the operand carries no
    # directory, so the protected root appears only in the `cd` target.
    return any(_protected_path(base) for base in _cd_bases(c))''',
        '''def _redirects_into_protected(c: str) -> bool:
    """True if any redirection target lands under a protected-write root.

    Checked separately from the verb scan because `> scripts/hooks/x.py` names
    no command at all — the shell does the writing.
    """
    return any(_token_writes_protected(m.group(1), c) for m in _REDIR_RE.finditer(c))


def _stage_writes_protected(tokens: list[str], c: str) -> bool:
    """True if this one mutating stage writes a protected path.

    The git arm runs first: an unscoped worktree rewrite reaches the protected
    paths without ever naming them, so the operand scan below cannot see it.
    """
    if PurePosixPath(tokens[0]).name == "git" and _git_rewrites_worktree(tokens):
        return True
    return any(_token_writes_protected(a, c) for a in tokens[1:])


def _writes_protected(command: str) -> bool:
    """True if the command writes to scripts/hooks/ or .claude/settings.json."""
    c = _canonicalize(command)
    if _redirects_into_protected(c):
        return True
    stages = [t for t in shell_stages(c) if _stage_is_mutating(t)]
    if not stages:
        return False
    if any(_stage_writes_protected(t, c) for t in stages):
        return True
    # `cd scripts/hooks && sed -i s/a/b/ ruff-hook.py` — the operand carries no
    # directory, so the protected root appears only in the `cd` target.
    return any(_protected_path(base) for base in _cd_bases(c))''',
    ),
]


def apply_to(path: Path, edits: list[tuple[str, str, str]], write: bool) -> bool:
    """Apply `edits` to `path`. Returns True on success, False on drift."""
    rel = path.relative_to(REPO)
    if not path.exists():
        print(f"ERROR  {rel} not found", file=sys.stderr)
        return False
    text = original = path.read_text(encoding="utf-8")
    for desc, anchor, replacement in edits:
        if replacement in text:
            print(f"SKIP   {desc} (already applied)")
            continue
        found = text.count(anchor)
        if found != 1:
            print(
                f"ERROR  {desc}: anchor matched {found} times, want exactly 1.\n"
                f"       {rel} drifted — re-read it and update this script.",
                file=sys.stderr,
            )
            return False
        text = text.replace(anchor, replacement, 1)
        print(f"OK     {desc}")
    if write and text != original:
        path.write_text(text, encoding="utf-8")
        print(f"       -> wrote {rel}")
    return True


def main() -> int:
    """Verify the anchor, then write."""
    ap = argparse.ArgumentParser(description="Split _writes_protected.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    if not apply_to(GUARD, EDITS, write=False):
        return 1
    if args.check:
        print("\nAll anchors matched. Re-run without --check to apply.")
        return 0
    print()
    if not apply_to(GUARD, EDITS, write=True):
        return 1
    print("\nApplied. Next: run `make check`, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
