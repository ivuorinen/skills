#!/usr/bin/env python3
"""One-shot patch: three CodeRabbit findings on scripts/hooks/.

`scripts/hooks/` is under permissions.deny for the Edit/Write tools. Delete this
file once applied.

    python3 docs/audit/apply-cr-round2.py --check
    python3 docs/audit/apply-cr-round2.py

1. deny-agents-path-hook.py — an unscoped worktree-writing git command rewrites
   tracked files under scripts/hooks/ while carrying no protected path token, so
   `_writes_protected` allowed it. `git reset --hard` is the clearest case.

2. deny-unsafe-git-hook.py — `_ADD_ALL` compared raw tokens, so `git add ./`,
   `git add .//` and `git add :/.` staged the whole tree despite the module
   docstring declaring that blocked. The sibling guard already normalises `./`
   before comparing, so the two disagreed on identical input.

3. ruff-hook.py and validate-rules-hook.py — the `except` arms added earlier in
   this branch returned silently even when an *earlier* validator in the same
   run had already failed, discarding a completed enforcement result. A tool
   error must not erase a finding that was already produced.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
H = REPO / "scripts" / "hooks"

EDITS: dict[str, list[tuple[str, str, str]]] = {
    "deny-agents-path-hook.py": [
        (
            "guard: unscoped worktree writes",
            """_GIT_WRITE_SUBCMDS = frozenset(
    {"checkout", "restore", "apply", "mv", "rm", "clean", "stash", "reset"}
)""",
            '''_GIT_WRITE_SUBCMDS = frozenset(
    {"checkout", "restore", "apply", "mv", "rm", "clean", "stash", "reset"}
)

# Git subcommands that rewrite tracked files across the WHOLE worktree while
# naming no path — so they reach scripts/hooks/ carrying no protected token for
# `_token_writes_protected` to match. `git reset --hard` is the plain case.
#
# Deliberately narrow, because over-blocking git makes the guard something to
# route around:
#   * `reset` counts only with a mode flag that touches the worktree; plain
#     `reset` and `--soft` move refs and leave files alone.
#   * `checkout`/`restore` count only with a whole-tree pathspec. Switching
#     branches also rewrites files, but that is ordinary work, and
#     ask-destructive-restore-hook.py already prompts when it would discard
#     uncommitted content.
#   * `apply` counts always: the patch decides what it touches, so it is
#     unscoped by construction.
#   * `clean` is absent on purpose — it removes untracked files only, and every
#     file under scripts/hooks/ is tracked.
#   * `stash` is absent on purpose — it is recoverable by `stash pop`, unlike
#     the others here.
_RESET_WORKTREE_MODES = frozenset({"--hard", "--merge", "--keep"})
_WHOLE_TREE = frozenset({".", "./", ":/", ":/.", "*"})


def _git_rewrites_worktree(tokens: list[str]) -> bool:
    """True if this git stage rewrites tracked files without naming a path."""
    i = skip_git_global_opts(tokens, 1)
    if i >= len(tokens):
        return False
    sub, args = tokens[i], tokens[i + 1 :]
    if sub == "apply":
        return True
    if sub == "reset":
        return any(a in _RESET_WORKTREE_MODES for a in args)
    if sub in ("checkout", "restore"):
        return any(a in _WHOLE_TREE for a in args)
    return False''',
        ),
        (
            "guard: consult it from _writes_protected",
            """    stages = [t for t in shell_stages(c) if _stage_is_mutating(t)]
    if not stages:
        return False
    for tokens in stages:""",
            """    stages = [t for t in shell_stages(c) if _stage_is_mutating(t)]
    if not stages:
        return False
    for tokens in stages:
        # An unscoped worktree rewrite reaches the protected paths without ever
        # naming them, so no operand check below would catch it.
        if PurePosixPath(tokens[0]).name == "git" and _git_rewrites_worktree(tokens):
            return True""",
        ),
    ],
    "deny-unsafe-git-hook.py": [
        (
            "git guard: normalise the pathspec",
            """_ADD_ALL = frozenset({"-A", "--all", "--no-ignore-removal", ".", ":/"})""",
            '''_ADD_ALL = frozenset({"-A", "--all", "--no-ignore-removal", ".", ":/"})


def _norm_pathspec(arg: str) -> str:
    """Fold the whole-tree pathspec spellings onto one comparable form.

    `git add ./`, `git add .//` and `git add :/.` stage exactly what `git add .`
    stages, so comparing raw tokens let three spellings through a check the
    module docstring declares blocked. deny-agents-path-hook.py already strips a
    leading `./` before comparing paths; this keeps the two guards agreeing on
    identical input.
    """
    if arg.startswith(":/"):
        return ":/" if not arg[2:].strip("./") else arg
    s = arg
    while s.startswith("./"):
        s = s[2:]
    return s.rstrip("/") or "."

''',
        ),
        (
            "git guard: compare normalised",
            """    if subcommand == "add":
        staged_all = [a for a in args if a in _ADD_ALL]""",
            """    if subcommand == "add":
        staged_all = [a for a in args if _norm_pathspec(a) in _ADD_ALL]""",
        ),
    ],
    "ruff-hook.py": [
        (
            "ruff-hook: keep a completed failure when a later call errors",
            """    try:
        fix = subprocess.run(""",
            """    fix = fmt = None
    try:
        fix = subprocess.run(""",
        ),
        (
            "ruff-hook: report the prior failure instead of returning",
            """    except (OSError, subprocess.SubprocessError):
        # ruff vanished between the which() above and here, or hung mid-run.
        # This hook fires on every .py edit and shells out three times, so an
        # unbounded call here is the likeliest place to freeze a session.
        return  # CI's ruff steps remain the gate""",
            """    except (OSError, subprocess.SubprocessError):
        # ruff vanished between the which() above and here, or hung mid-run.
        # This hook fires on every .py edit and shells out three times, so an
        # unbounded call here is the likeliest place to freeze a session.
        #
        # A completed failure is not discarded by a later tool error: if fix or
        # format already reported one, that result is real and has to surface,
        # or the tool error silently erases an enforcement outcome.
        prior = "".join(r.stdout + r.stderr for r in (fix, fmt) if r and r.returncode != 0)
        if prior.strip():
            print(prior.rstrip(), file=sys.stderr, flush=True)
            sys.exit(2)
        return  # nothing had failed yet — CI's ruff steps remain the gate""",
        ),
    ],
    "validate-rules-hook.py": [
        (
            "validate-rules-hook: keep a completed failure",
            """        except (OSError, subprocess.SubprocessError):
            return  # uv/python3 absent or the validator hung — CI remains the gate""",
            """        except (OSError, subprocess.SubprocessError):
            # Stop running validators, but fall through to the report below: a
            # failure already collected from an earlier one is a real result,
            # and returning here would discard it.
            break""",
        ),
    ],
}


TEST_EDITS: list[tuple[str, str, str]] = [
    (
        "tests: the round-2 cases",
        """    err = capsys.readouterr().err
    assert "enforcement surface" in err
    assert "Reading" in err""",
        '''    err = capsys.readouterr().err
    assert "enforcement surface" in err
    assert "Reading" in err


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard",
        "git reset --hard HEAD~1",
        "git reset --merge",
        "git checkout .",
        "git checkout -- .",
        "git restore .",
        "git restore :/",
        "git apply /tmp/x.patch",
        "git -C . apply /tmp/x.patch",
    ],
)
def test_guard_blocks_an_unscoped_worktree_rewrite(command):
    """These rewrite tracked files under scripts/hooks/ while naming no path, so
    no operand check sees a protected token and the guard would otherwise pass
    them. `git reset --hard` is the plain case."""
    assert _guard_blocks(command), command


@pytest.mark.parametrize(
    "command",
    [
        "git reset --soft HEAD~1",
        "git reset HEAD~1",
        "git checkout -b feature/x",
        "git checkout main",
        "git restore --staged README.md",
        "git stash",
        "git clean -fd",
    ],
)
def test_guard_allows_scoped_and_recoverable_git(command):
    """Over-blocking git makes the guard something to route around. `--soft` and a
    bare reset move refs only; branch switching is ordinary work already covered
    by ask-destructive-restore-hook; clean touches untracked files only, and every
    file under scripts/hooks/ is tracked; stash is recoverable by `stash pop`."""
    assert not _guard_blocks(command), command


def test_git_rewrites_worktree_ignores_a_bare_git():
    """A `git` with no subcommand names nothing to rewrite."""
    assert _load("deny-agents-path-hook")._git_rewrites_worktree(["git"]) is False


@pytest.mark.parametrize("spelling", ["./", ".//", ":/.", ".", ":/", "././"])
def test_git_guard_normalises_whole_tree_pathspecs(spelling):
    """`git add ./` stages exactly what `git add .` stages, so comparing raw
    tokens let three spellings through a check the docstring declares blocked."""
    mod = _load("deny-unsafe-git-hook")
    assert mod._norm_pathspec(spelling) in mod._ADD_ALL, spelling


def test_ruff_hook_keeps_a_completed_failure_when_a_later_call_errors(
    monkeypatch, tmp_path, capsys
):
    """A tool error must not erase a finding an earlier validator already
    produced — that silently drops an enforcement result."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/ruff")
    calls = []

    def _run_ruff(cmd, *a, **k):
        """Fail the first ruff call, then time out."""
        calls.append(cmd)
        if len(calls) == 1:
            return _Result(returncode=2, stderr="ruff: bad configuration\\n")
        raise subprocess.TimeoutExpired(["ruff"], 120)

    monkeypatch.setattr(mod.subprocess, "run", _run_ruff)
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    assert exc.value.code == 2
    assert "bad configuration" in capsys.readouterr().err


def test_ruff_hook_returns_when_nothing_had_failed_yet(monkeypatch, tmp_path, capsys):
    """With no completed failure to preserve, a tool error stays silent."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/ruff")

    def _boom(*a, **k):
        """Fail before any validator completes."""
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_rules_hook_keeps_a_completed_failure(monkeypatch, tmp_path, capsys):
    """The rule validator runs first and the anatomy checker second. A failure
    already collected from the first has to survive an error in the second —
    the branch is reachable without this test, but nothing pinned the outcome."""
    mod = _load("validate-rules-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate-rules.py").write_text("", encoding="utf-8")
    anatomy = tmp_path / "skills" / "nitpicker" / "scripts"
    anatomy.mkdir(parents=True)
    (anatomy / "check-rules-anatomy.py").write_text("", encoding="utf-8")
    rule = tmp_path / ".claude" / "rules" / "x.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("# R\\n", encoding="utf-8")
    calls = []

    def _run_validator(cmd, *a, **k):
        """Fail the rule validator, then make the anatomy checker unrunnable."""
        calls.append(cmd)
        if len(calls) == 1:
            return _Result(returncode=1, stdout="RULE VIOLATION: hedged language\\n")
        raise FileNotFoundError("python3")

    monkeypatch.setattr(mod.subprocess, "run", _run_validator)
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(rule)}}), monkeypatch)
    assert exc.value.code == 2
    assert "RULE VIOLATION" in capsys.readouterr().err''',
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
    """Verify every anchor across every file, then write."""
    ap = argparse.ArgumentParser(description="Apply CodeRabbit round-2 findings.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    targets = [(H / name, edits) for name, edits in EDITS.items()]
    targets.append((REPO / "tests" / "test_hooks.py", TEST_EDITS))

    for path, edits in targets:
        if not apply_to(path, edits, write=False):
            return 1
    if args.check:
        print("\nAll anchors matched. Re-run without --check to apply.")
        return 0
    print()
    for path, edits in targets:
        if not apply_to(path, edits, write=True):
            return 1
    print("\nApplied. Next: run `make check`, then commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
