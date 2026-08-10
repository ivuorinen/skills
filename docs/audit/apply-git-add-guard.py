#!/usr/bin/env python3
"""One-shot patch: block `git add -A` and its equivalents in the Bash guard.

`scripts/hooks/` is under permissions.deny for the Edit/Write tools, so an agent
cannot apply this. Anchored string replacements, not a diff, so it fails loudly
on drift. Delete this file once applied — the change lives in git from then on.

    python3 docs/audit/apply-git-add-guard.py --check
    python3 docs/audit/apply-git-add-guard.py

Why the whole class and not just `-A`: `git add .` stages every untracked file
under the cwd exactly as `-A` does from the root, so blocking only `-A` moves
the hazard rather than removing it. `git add -u` (tracked files only) and
explicit pathspecs stay allowed, and the denial message names both.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "hooks" / "deny-unsafe-git-hook.py"
TESTS = REPO / "tests" / "test_hooks.py"

GUARD_EDITS: list[tuple[str, str, str]] = [
    (
        "guard: docstring lists the third mandate",
        """1. `git commit --no-verify` / `-n` skips the pre-commit validators that guard
   skill files, the version manifests, and the findings store
   (.claude/rules/commit-gate-integrity.md, which states no in-session hook
   enforces it).
2. `git push` onto a protected branch
   (skills/nitpicker/commands/cr.md Step 6: never push directly to main/master).""",
        """1. `git commit --no-verify` / `-n` skips the pre-commit validators that guard
   skill files, the version manifests, and the findings store
   (.claude/rules/commit-gate-integrity.md, which states no in-session hook
   enforces it).
2. `git push` onto a protected branch
   (skills/nitpicker/commands/cr.md Step 6: never push directly to main/master).
3. `git add -A` / `--all` / `.` — staging the whole tree is a recurring source
   of commits carrying files the change never touched: scratch output, local
   config, editor artifacts. Explicit pathspecs and `git add -u` (tracked files
   only) stay allowed.""",
    ),
    (
        "guard: the stage-everything pathspecs",
        """_NO_VERIFY = frozenset({"--no-verify", "-n"})""",
        """_NO_VERIFY = frozenset({"--no-verify", "-n"})
# Arguments that stage every change rather than a named path. `.` is included
# deliberately: from the repo root it stages the same set `-A` does, so blocking
# only the flags would move the hazard to `git add .` instead of removing it.
# `:/` is git's whole-repo pathspec magic — the same thing spelled differently.
_ADD_ALL = frozenset({"-A", "--all", "--no-ignore-removal", ".", ":/"})""",
    ),
    (
        "guard: the denial message",
        """_PUSH_DENIAL = (
    "  DENIED  push targets a protected branch (HEAD is '{branch}').\\n"
    "          Open a PR from a feature branch instead — see cr.md Step 6."
)""",
        """_PUSH_DENIAL = (
    "  DENIED  push targets a protected branch (HEAD is '{branch}').\\n"
    "          Open a PR from a feature branch instead — see cr.md Step 6."
)
_ADD_DENIAL = (
    "  DENIED  `git add {arg}` stages the whole tree, including files this change\\n"
    "          never touched — scratch output, local config, editor artifacts.\\n"
    "          Stage what you actually changed: git add <path> [<path> ...]\\n"
    "          `git add -u` restages tracked files only, if that is what you meant."
)""",
    ),
    (
        "guard: deny the call",
        '''def _denial(subcommand: str, args: list[str]) -> str | None:
    """The message to block this git call with, or None to allow it."""
    if subcommand == "commit" and any(a in _NO_VERIFY for a in args):
        return _COMMIT_DENIAL''',
        '''def _denial(subcommand: str, args: list[str]) -> str | None:
    """The message to block this git call with, or None to allow it."""
    if subcommand == "commit" and any(a in _NO_VERIFY for a in args):
        return _COMMIT_DENIAL
    if subcommand == "add":
        staged_all = [a for a in args if a in _ADD_ALL]
        if staged_all:
            return _ADD_DENIAL.format(arg=staged_all[0])''',
    ),
]

TEST_EDITS: list[tuple[str, str, str]] = [
    (
        "tests: staging the whole tree is denied, targeted staging is not",
        """    mod = _load("deny-unsafe-git-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 2
    assert "--no-verify" in capsys.readouterr().err""",
        '''    mod = _load("deny-unsafe-git-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 2
    assert "--no-verify" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "git add -A",
        "git add --all",
        "git add .",
        "git add :/",
        "git add -A -- .",
        "git -C . add -A",  # past a value-taking global option
        "echo staged && git add --all",  # not the first stage
        "FOO=1 git add .",  # env prefix before git
    ],
)
def test_git_guard_denies_staging_the_whole_tree(command, monkeypatch, capsys):
    """`git add -A` is a recurring source of commits carrying files the change
    never touched — scratch output, local config, editor artifacts. Blocking the
    flag alone would move the hazard to `git add .`, which stages the same set
    from the repo root, so the whole stage-everything class is denied."""
    mod = _load("deny-unsafe-git-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 2
    assert "stages the whole tree" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "git add README.md",
        "git add tests/test_hooks.py docs/audit/findings/INDEX.md",
        "git add -u",  # tracked files only — stages no new file
        "git add -p",  # interactive, per hunk
        "git add --update docs/",
        'git commit -m "git add -A is banned"',  # the token as message content
        "grep -rn 'git add -A' docs/",  # the token as search content
    ],
)
def test_git_guard_allows_targeted_staging(command, monkeypatch, capsys):
    """The guard must not push the agent off `git add` entirely: explicit
    pathspecs and `-u` are the intended replacements, and the token appearing as
    quoted content is not an invocation."""
    mod = _load("deny-unsafe-git-hook")
    _run(mod, _bash(command), monkeypatch)
    assert capsys.readouterr().err == ""''',
    ),
]

TARGETS: list[tuple[Path, list[tuple[str, str, str]]]] = [
    (GUARD, GUARD_EDITS),
    (TESTS, TEST_EDITS),
]


def apply_to(path: Path, edits: list[tuple[str, str, str]], write: bool) -> bool:
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
    ap = argparse.ArgumentParser(description="Block `git add -A` in the Bash guard.")
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
