#!/usr/bin/env python3
"""One-shot patch: close the symlinked-checkout bypass in the protected-write guard.

`scripts/hooks/` is under permissions.deny for the Edit/Write tools. Delete this
file once applied.

    python3 docs/audit/apply-cr-round5.py --check
    python3 docs/audit/apply-cr-round5.py

`_token_writes_protected` compared an absolute token against the UNRESOLVED
`_REPO_ROOT`, while `_protected_path` in the same file resolves both sides. Under
a symlinked checkout the two disagree, and an absolute token naming the real
underlying path falls through `relative_to`'s ValueError and reads as "not
protected". The glob arm below cannot recover it: a plain absolute path carries
no metacharacter.

Reproduced before fixing, with REPO_ROOT pointed at a symlink:

    /tmp/symtest/link/scripts/hooks/ruff-hook.py   blocked=True
    /tmp/symtest/real/scripts/hooks/ruff-hook.py   blocked=False   <- bypass

The real path is trivially discoverable, so this is a live hole rather than a
theoretical one. The repo already treats a symlinked root as supported —
validate-audit-findings-hook.py carries a regression test for exactly that case.

`Path.resolve()` raises OSError on some platforms for an unresolvable path, so
the except widens to `(OSError, ValueError)` rather than ValueError alone.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

HOOK_EDITS: list[tuple[str, str, str]] = [
    (
        "guard: resolve an absolute token before relative_to",
        """    pure = PurePosixPath(token)
    if pure.is_absolute():
        try:
            token = str(pure.relative_to(_REPO_ROOT))
        except ValueError:
            return False  # absolute but outside the repo — nothing to protect""",
        """    pure = PurePosixPath(token)
    if pure.is_absolute():
        # Resolved on both sides, matching _protected_path. Comparing against an
        # unresolved _REPO_ROOT made a symlinked checkout a bypass: an absolute
        # token naming the real underlying path raised ValueError here and read
        # as "not protected", and the glob arm below cannot recover it because a
        # plain absolute path carries no metacharacter.
        try:
            token = str(Path(token).resolve().relative_to(_REPO_ROOT.resolve()))
        except (OSError, ValueError):
            return False  # absolute but outside the repo — nothing to protect""",
    ),
]

TEST_EDITS: list[tuple[str, str, str]] = [
    (
        "tests: the symlinked-checkout bypass",
        '''def test_git_rewrites_worktree_ignores_a_bare_git():
    """A `git` with no subcommand names nothing to rewrite."""
    assert _load("deny-agents-path-hook")._git_rewrites_worktree(["git"]) is False''',
        '''def test_git_rewrites_worktree_ignores_a_bare_git():
    """A `git` with no subcommand names nothing to rewrite."""
    assert _load("deny-agents-path-hook")._git_rewrites_worktree(["git"]) is False


def test_guard_blocks_an_absolute_path_under_a_symlinked_checkout(monkeypatch, tmp_path):
    """An absolute token naming the REAL path under a symlinked root must still
    be protected. Comparing against an unresolved _REPO_ROOT made relative_to
    raise, which read as "not protected" — and the glob arm cannot recover it,
    because a plain absolute path carries no metacharacter."""
    real = tmp_path / "real"
    (real / "scripts" / "hooks").mkdir(parents=True)
    target = real / "scripts" / "hooks" / "ruff-hook.py"
    target.write_text("x = 1\\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    mod = _load("deny-agents-path-hook")
    monkeypatch.setattr(mod, "_REPO_ROOT", link)

    via_link = link / "scripts" / "hooks" / "ruff-hook.py"
    assert mod._writes_protected(f"sed -i s/a/b/ {via_link}")
    assert mod._writes_protected(f"sed -i s/a/b/ {target}"), (
        "the real underlying path bypassed the guard under a symlinked checkout"
    )


def test_guard_ignores_an_absolute_path_outside_the_repo(monkeypatch, tmp_path):
    """Resolving both sides must not start capturing paths outside the root."""
    mod = _load("deny-agents-path-hook")
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    outside = tmp_path.parent / "elsewhere" / "scripts" / "hooks" / "x.py"
    assert not mod._writes_protected(f"sed -i s/a/b/ {outside}")''',
    ),
]

TARGETS: list[tuple[Path, list[tuple[str, str, str]]]] = [
    (REPO / "scripts" / "hooks" / "deny-agents-path-hook.py", HOOK_EDITS),
    (REPO / "tests" / "test_hooks.py", TEST_EDITS),
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
    """Verify every anchor across both files, then write."""
    ap = argparse.ArgumentParser(description="Close the symlinked-checkout bypass.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    for path, edits in TARGETS:
        if not apply_to(path, edits, write=False):
            return 1
    if args.check:
        print("\nAll anchors matched. Re-run without --check to apply.")
        return 0
    print()
    for path, edits in TARGETS:
        if not apply_to(path, edits, write=True):
            return 1
    print("\nApplied. Next: run `make check`, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
