#!/usr/bin/env python3
"""Apply the audit findings an agent cannot: they live under permissions.deny.

Every fix here touches `scripts/hooks/`, which `.claude/settings.json` denies to
the Edit/Write tools, so the release-prep audit filed them open instead of
applying them. This script is the patch, written as anchored string
replacements rather than a unified diff so it fails loudly on drift instead of
applying with fuzz. Already-applied edits are detected and skipped, so it is
safe to re-run.

    python3 docs/audit/apply-open-findings.py --check   # verify anchors only
    python3 docs/audit/apply-open-findings.py           # apply

Covers, in full:

  agent-loopholes-338dfd70 (high)
    1. GOVERNED gains scripts/ and .claude/settings.json, so a Bash edit to the
       enforcement surface re-runs the gates instead of returning early.
    2. deny-agents-path-hook.py becomes a protected-paths guard: it now also
       blocks a Bash command that WRITES to scripts/hooks/ or
       .claude/settings.json. Writes only — unlike .claude/agents, Read is not
       denied for those paths, so blocking `cat scripts/hooks/ruff-hook.py`
       would contradict the permission model and break ordinary work.

  reliability-397b7fec (medium)
    Every subprocess.run in scripts/hooks/ is bounded by HOOK_TIMEOUT and
    wrapped so the call degrades to a skipped gate instead of hanging the
    session or raising an uncaught FileNotFoundError. The except clause covers
    the missing-binary case, which is why no separate shutil.which preflight is
    added at these sites.

The matching tests/test_hooks.py cases are applied too, so the patch lands
green against coverage's fail_under=100. Run `make check` before committing.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
H = REPO / "scripts" / "hooks"
TESTS = REPO / "tests" / "test_hooks.py"

# ── reliability-397b7fec ──────────────────────────────────────────────────────

HOOKLIB_EDITS: list[tuple[str, str, str]] = [
    (
        "_hooklib: one definition of the hook subprocess timeout",
        # Anchored on the function below rather than the _VALUE_OPTS line above,
        # which is itself past ruff's 100-col limit when quoted here.
        """def repo_root() -> Path:""",
        """# Seconds, shared by every hook that shells out. An unbounded call is
# unrecoverable from the user's side: a PostToolUse hook that blocks freezes the
# session with no output and no signal, and `uv run` resolves an environment
# from the network on a cold cache. Generous enough for that resolve, short
# enough that a hung gate surfaces as a failure instead of a frozen session.
# deny-unsafe-git-hook.py uses 10 for a bare `git rev-parse`.
HOOK_TIMEOUT = 120


def repo_root() -> Path:""",
    ),
]

REVALIDATE_EDITS: list[tuple[str, str, str]] = [
    (
        "GOVERNED: cover the enforcement surface itself",
        """GOVERNED = (
    "skills/",
    ".claude/rules/",""",
        # Replacement text must stay byte-identical to what already landed, or
        # the already-applied check below misses and the anchor is long gone.
        """GOVERNED = (
    "skills/",
    # The enforcement surface itself. permissions.deny stops Edit/Write on
    # scripts/hooks/ and .claude/settings.json but never reaches Bash, and no
    # PreToolUse guard matches them either — deny-agents-path-hook.py covers
    # .claude/agents/ only. Without these two entries a `sed -i` disabling a
    # guard, or unregistering every hook at once, ran the gates zero times.
    # "scripts/" also covers the validators the gates below invoke.
    "scripts/",
    ".claude/settings.json",
    ".claude/rules/",""",
    ),
    (
        "import shutil for the binary preflight",
        """import subprocess
import sys
from pathlib import Path""",
        """import shutil
import subprocess
import sys
from pathlib import Path""",
    ),
    (
        "GATE_TIMEOUT constant",
        '''FINDINGS = "skills/nitpicker/scripts/findings.py"''',
        """FINDINGS = "skills/nitpicker/scripts/findings.py"

# Seconds. Generous enough for a cold `uv run` that resolves an environment,
# short enough that a hung gate surfaces as a failure rather than a frozen
# session. deny-unsafe-git-hook.py uses 10 for a bare `git rev-parse`.
GATE_TIMEOUT = 120""",
    ),
    (
        "git status: bound the call",
        """    status = subprocess.run(
        ["git", "status", "--porcelain", "--ignored"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return  # not a git tree — nothing to scope against""",
        """    try:
        status = subprocess.run(
            ["git", "status", "--porcelain", "--ignored"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=GATE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        # git absent, or a tree slow enough that status timed out. A PostToolUse
        # hook that blocks has no user-visible recovery, so bound it and skip.
        return
    if status.returncode != 0:
        return  # not a git tree — nothing to scope against""",
    ),
    (
        "gates: preflight the binary and bound the call",
        # Split literal, same string: the line itself exceeds ruff's 100-col limit.
        "        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)",
        """        if shutil.which(cmd[0]) is None:
            # Same reasoning as the missing-script arm above: that check covered
            # the gate script but never the interpreter, so an absent `uv` raised
            # an uncaught FileNotFoundError instead of this message.
            print(
                f"  post-bash-revalidate: gate skipped, {cmd[0]} not on PATH",
                file=sys.stderr,
            )
            continue
        try:
            result = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=GATE_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            # `uv run` resolves and downloads an environment on a cold cache; an
            # unreachable index made that block forever with no output.
            failures.append(f"{' '.join(cmd)} timed out after {GATE_TIMEOUT}s")
            continue
        except OSError as exc:
            failures.append(f"{' '.join(cmd)} could not run: {exc}")
            continue""",
    ),
]

RUFF_EDITS: list[tuple[str, str, str]] = [
    (
        "ruff-hook: import the shared timeout",
        "from _hooklib import event_path, repo_root  # type: ignore[import-not-found]",
        "from _hooklib import (  # type: ignore[import-not-found]\n"
        "    HOOK_TIMEOUT,\n"
        "    event_path,\n"
        "    repo_root,\n"
        ")",
    ),
    (
        "ruff-hook: bound all three ruff calls",
        """    fix = subprocess.run(
        ["ruff", "check", "--fix", "--quiet", str(path)], capture_output=True, text=True
    )
    fmt = subprocess.run(["ruff", "format", "--quiet", str(path)], capture_output=True, text=True)

    # report any remaining lint errors
    result = subprocess.run(
        ["ruff", "check", str(path)],
        capture_output=True,
        text=True,
    )""",
        """    try:
        fix = subprocess.run(
            ["ruff", "check", "--fix", "--quiet", str(path)],
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
        fmt = subprocess.run(
            ["ruff", "format", "--quiet", str(path)],
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
        # report any remaining lint errors
        result = subprocess.run(
            ["ruff", "check", str(path)],
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        # ruff vanished between the which() above and here, or hung mid-run.
        # This hook fires on every .py edit and shells out three times, so an
        # unbounded call here is the likeliest place to freeze a session.
        return  # CI's ruff steps remain the gate""",
    ),
]

VSKILL_EDITS: list[tuple[str, str, str]] = [
    (
        "validate-skill-hook: import the shared timeout",
        "from _hooklib import event_path, repo_root  # type: ignore[import-not-found]",
        "from _hooklib import (  # type: ignore[import-not-found]\n"
        "    HOOK_TIMEOUT,\n"
        "    event_path,\n"
        "    repo_root,\n"
        ")",
    ),
    (
        "validate-skill-hook: bound the validator call",
        """    result = subprocess.run(
        ["uv", "run", "--quiet", str(validator), str(target)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )""",
        """    try:
        result = subprocess.run(
            ["uv", "run", "--quiet", str(validator), str(target)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return  # uv absent or the validator hung — CI remains the gate""",
    ),
]

VRULES_EDITS: list[tuple[str, str, str]] = [
    (
        "validate-rules-hook: import the shared timeout",
        "from _hooklib import event_path, repo_root  # type: ignore[import-not-found]",
        "from _hooklib import (  # type: ignore[import-not-found]\n"
        "    HOOK_TIMEOUT,\n"
        "    event_path,\n"
        "    repo_root,\n"
        ")",
    ),
    (
        "validate-rules-hook: bound both validator calls",
        """        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if result.returncode != 0:""",
        """        try:
            result = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=HOOK_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return  # uv/python3 absent or the validator hung — CI remains the gate
        if result.returncode != 0:""",
    ),
]

VSYNC_EDITS: list[tuple[str, str, str]] = [
    (
        "check-version-sync-hook: import the shared timeout",
        "from _hooklib import event_path, repo_root  # type: ignore[import-not-found]",
        "from _hooklib import (  # type: ignore[import-not-found]\n"
        "    HOOK_TIMEOUT,\n"
        "    event_path,\n"
        "    repo_root,\n"
        ")",
    ),
    (
        "check-version-sync-hook: bound the checker call",
        """    result = subprocess.run(
        ["uv", "run", "--quiet", str(checker)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )""",
        """    try:
        result = subprocess.run(
            ["uv", "run", "--quiet", str(checker)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return  # uv absent or the checker hung — CI remains the gate""",
    ),
]

VAUDIT_EDITS: list[tuple[str, str, str]] = [
    (
        "validate-audit-findings-hook: import the shared timeout",
        "from _hooklib import event_path, repo_root  # type: ignore[import-not-found]",
        "from _hooklib import (  # type: ignore[import-not-found]\n"
        "    HOOK_TIMEOUT,\n"
        "    event_path,\n"
        "    repo_root,\n"
        ")",
    ),
    (
        "validate-audit-findings-hook: bound the per-file validate",
        """        result = subprocess.run(
            [*py, "validate", str(path)], capture_output=True, text=True, cwd=REPO_ROOT
        )""",
        """        try:
            result = subprocess.run(
                [*py, "validate", str(path)],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=HOOK_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return  # findings.py unrunnable — `make check` remains the gate""",
    ),
    (
        "validate-audit-findings-hook: bound the store validate",
        # Split literal, same string: the line itself exceeds ruff's 100-col limit.
        '        result = subprocess.run([*py, "validate"], '
        "capture_output=True, text=True, cwd=REPO_ROOT)",
        """        try:
            result = subprocess.run(
                [*py, "validate"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                timeout=HOOK_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return  # findings.py unrunnable — `make check` remains the gate""",
    ),
    (
        "validate-audit-findings-hook: bound the index regeneration",
        """    index = subprocess.run(
        [*py, "index"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )""",
        """    try:
        index = subprocess.run(
            [*py, "index"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=HOOK_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return  # findings.py unrunnable — `make check` remains the gate""",
    ),
]

STOP_EDITS: list[tuple[str, str, str]] = [
    (
        "stop-reminder: import the shared timeout",
        "from _hooklib import load_event, repo_root  # type: ignore[import-not-found]",
        "from _hooklib import (  # type: ignore[import-not-found]\n"
        "    HOOK_TIMEOUT,\n"
        "    load_event,\n"
        "    repo_root,\n"
        ")",
    ),
    (
        "stop-reminder: bound the three git reads",
        """        result = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return""",
        """        try:
            result = subprocess.run(
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=HOOK_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return  # git absent or hung — no reminder is better than a frozen stop
        if result.returncode != 0:
            return""",
    ),
]

# ── agent-loopholes-338dfd70 change 2 ─────────────────────────────────────────

GUARD_EDITS: list[tuple[str, str, str]] = [
    (
        "guard: docstring now covers the whole enforcement surface",
        '''"""PreToolUse hook — block Bash commands that reach into .claude/agents/.

The `permissions.deny` list in .claude/settings.json covers Read/Edit/Write on
`./.claude/agents/**`, but not Bash — `head`, `sed -i`, or a redirection walks
straight past it. This hook closes that surface for the Bash tool.
"""''',
        '''"""PreToolUse hook — block Bash commands that reach the protected trees.

The `permissions.deny` list in .claude/settings.json covers Read/Edit/Write but
never Bash — `head`, `sed -i`, or a redirection walks straight past it. This
hook closes that surface for the Bash tool, in two different shapes because the
deny list itself has two shapes:

- `.claude/agents/**` denies Read as well as Edit/Write, so ANY reference is
  blocked (see `_references_agents`).
- `scripts/hooks/**` and `.claude/settings.json` deny only Edit/Write/
  NotebookEdit — Read stays allowed — so only a WRITE is blocked (see
  `_writes_protected`). Denying `cat scripts/hooks/ruff-hook.py` would
  contradict the permission model and break ordinary work.
"""''',
    ),
    (
        "guard: import the shared tokenizer",
        "from _hooklib import load_event, repo_root  # type: ignore[import-not-found]",
        "from _hooklib import (  # type: ignore[import-not-found]\n"
        "    load_event,\n"
        "    repo_root,\n"
        "    shell_stages,\n"
        "    skip_git_global_opts,\n"
        ")",
    ),
    (
        "guard: protected-write matcher",
        """def _canonicalize(command: str) -> str:""",
        '''# ── protected-write paths ─────────────────────────────────────────────────────
#
# permissions.deny also covers Edit/Write/NotebookEdit on `scripts/hooks/**` and
# `.claude/settings.json` — the enforcement surface itself — and Bash walks past
# those exactly as it does for the agents tree. Unlike `.claude/agents`, Read is
# NOT denied for them, so this half matches a MUTATION only.
#
# Ceiling, stated rather than implied: this matches redirection targets, a fixed
# set of mutating verbs, in-place stream editors, and the `git` subcommands that
# write the working tree. A write performed *inside* an interpreter
# (`python -c "open(p, 'w')"`), by a script that takes the path as data, or
# through a symlink is not matched. As with the agents half, CODEOWNERS plus
# branch protection remains the binding control; this raises the cost of the
# bypass, it does not close it.
PROTECTED_WRITE = ("scripts/hooks", ".claude/settings.json")

_REDIR_RE = re.compile(r">{1,2}\\s*([^\\s;&|<>()]+)")
_WRITE_VERBS = frozenset(
    {
        "cp",
        "mv",
        "rm",
        "rmdir",
        "install",
        "truncate",
        "dd",
        "tee",
        "patch",
        "chmod",
        "chown",
        "chgrp",
        "ln",
        "shred",
        "touch",
        "ed",
        "ex",
        "sponge",
    }
)
# Only in-place invocations write; a bare `sed`/`perl` reads and prints.
_STREAM_EDITORS = frozenset({"sed", "perl", "ruby"})
_INPLACE_RE = re.compile(r"^-[a-zA-Z]*i|^--in-place")
_GIT_WRITE_SUBCMDS = frozenset(
    {"checkout", "restore", "apply", "mv", "rm", "clean", "stash", "reset"}
)


def _under_protected(rel: str) -> bool:
    """True if a repo-relative POSIX path sits at or under a protected-write root."""
    rel = rel.strip()
    while rel.startswith("./"):
        rel = rel[2:]
    return any(rel == root or rel.startswith(root + "/") for root in PROTECTED_WRITE)


def _protected_path(path: Path) -> bool:
    """True if a filesystem path resolves inside a protected-write root."""
    try:
        rel = path.resolve().relative_to(_REPO_ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    return _under_protected(rel)


def _token_writes_protected(token: str, command: str) -> bool:
    """True if `token`, read as a path, lands under a protected-write root.

    `--file=path` and `dd of=path` carry the path after an `=`, so the tail is
    taken. Glob tokens are expanded through the same machinery the agents half
    uses, so `scripts/ho*ks/*.py` resolves rather than being read literally.
    """
    token = token.split("=", 1)[-1]
    if not token:
        return False
    pure = PurePosixPath(token)
    if pure.is_absolute():
        try:
            token = str(pure.relative_to(_REPO_ROOT))
        except ValueError:
            return False  # absolute but outside the repo — nothing to protect
    if _under_protected(token):
        return True
    if _GLOB_META_RE.search(token):
        for base in _cd_bases(command):
            for hit in _shell_glob(base, token):
                if _protected_path(hit):
                    return True
    return False


def _stage_is_mutating(tokens: list[str]) -> bool:
    """True if this pipeline stage's verb writes files."""
    verb = PurePosixPath(tokens[0]).name
    if verb in _WRITE_VERBS:
        return True
    if verb in _STREAM_EDITORS:
        return any(_INPLACE_RE.match(a) for a in tokens[1:])
    if verb == "git":
        i = skip_git_global_opts(tokens, 1)
        return i < len(tokens) and tokens[i] in _GIT_WRITE_SUBCMDS
    return False


def _writes_protected(command: str) -> bool:
    """True if the command writes to scripts/hooks/ or .claude/settings.json."""
    c = _canonicalize(command)
    for match in _REDIR_RE.finditer(c):
        if _token_writes_protected(match.group(1), c):
            return True
    stages = [t for t in shell_stages(c) if _stage_is_mutating(t)]
    if not stages:
        return False
    for tokens in stages:
        if any(_token_writes_protected(a, c) for a in tokens[1:]):
            return True
    # `cd scripts/hooks && sed -i s/a/b/ ruff-hook.py` — the operand carries no
    # directory, so the protected root appears only in the `cd` target.
    return any(_protected_path(base) for base in _cd_bases(c))


def _canonicalize(command: str) -> str:''',
    ),
    (
        "guard: deny a protected write",
        """    command = (data.get("tool_input") or {}).get("command") or ""
    if _references_agents(command):
        # PreToolUse: exit 2 blocks the call and surfaces stderr to the agent.
        print(f"  DENIED  Bash command references {DENIED}", file=sys.stderr, flush=True)
        sys.exit(2)""",
        """    command = (data.get("tool_input") or {}).get("command") or ""
    if _references_agents(command):
        # PreToolUse: exit 2 blocks the call and surfaces stderr to the agent.
        print(f"  DENIED  Bash command references {DENIED}", file=sys.stderr, flush=True)
        sys.exit(2)
    if _writes_protected(command):
        print(
            "  DENIED  Bash command writes to the enforcement surface "
            f"({', '.join(PROTECTED_WRITE)}).\\n"
            "          permissions.deny covers the edit tools, not Bash. Reading\\n"
            "          these paths is allowed; changing them is the owner's call.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)""",
    ),
]

# ── tests ─────────────────────────────────────────────────────────────────────

TEST_EDITS: list[tuple[str, str, str]] = [
    (
        "tests: import subprocess for the timeout case",
        """import runpy
import shutil
import sys
from pathlib import Path""",
        """import runpy
import shutil
import subprocess
import sys
from pathlib import Path""",
    ),
    (
        "tests: let the fake runner raise, and keep shutil.which hermetic",
        # Content starts at column 0 so the 98-char def line stays under ruff's
        # 100-col limit here as well as in the file it is written into.
        '''\
def _revalidate(monkeypatch, tmp_path, *, status, gate=None, gates_on_disk=True):
    """Load the hook against a tmp REPO_ROOT with subprocess.run faked.

    `status` is the _Result for `git status`; `gate` is called with each gate's
    argv and returns that gate's _Result (default: success).
    """''',
        '''\
def _revalidate(monkeypatch, tmp_path, *, status, gate=None, gates_on_disk=True, missing_bins=()):
    """Load the hook against a tmp REPO_ROOT with subprocess.run faked.

    `status` is the _Result for `git status`; `gate` is called with each gate's
    argv and returns that gate's _Result (default: success). Either may be an
    exception instance instead, which the fake runner raises — that is how the
    timeout and OSError arms are driven.

    `missing_bins` names binaries `shutil.which` should report absent. The
    default keeps every other test hermetic: without it the preflight would
    depend on `uv` actually being installed on the machine running the suite.
    """''',
    ),
    (
        "tests: raise-capable fake runner + which patch",
        """    def _fake_run(cmd, *a, **k):
        calls.append(list(cmd))
        if cmd[:2] == ["git", "status"]:
            return status
        return gate(cmd) if gate else _Result()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    return mod, calls""",
        """    def _fake_run(cmd, *a, **k):
        calls.append(list(cmd))
        if cmd[:2] == ["git", "status"]:
            if isinstance(status, BaseException):
                raise status
            return status
        result = gate(cmd) if gate else _Result()
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        mod.shutil, "which", lambda name: None if name in missing_bins else f"/usr/bin/{name}"
    )
    return mod, calls""",
    ),
    (
        "tests: the post-bash-revalidate cases",
        """def _gate_calls(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if c[:2] != ["git", "status"]]""",
        '''def _gate_calls(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if c[:2] != ["git", "status"]]


def test_governed_covers_the_enforcement_surface(monkeypatch, tmp_path):
    """permissions.deny stops Edit/Write on scripts/hooks/ and settings.json but
    never reaches Bash, and no PreToolUse guard matches them. Without these
    entries a `sed -i` disabling a guard ran the gates zero times."""
    governed = _load("post-bash-revalidate").GOVERNED
    assert "scripts/" in governed
    assert ".claude/settings.json" in governed


def test_revalidate_skips_a_gate_whose_binary_is_absent(monkeypatch, tmp_path, capsys):
    """The existence check covered the gate script but never the interpreter, so
    an absent `uv` raised an uncaught FileNotFoundError instead of a skip line."""
    mod, calls = _revalidate(
        monkeypatch,
        tmp_path,
        status=_Result(stdout=" M skills/nitpicker/SKILL.md\\n"),
        missing_bins={"uv"},
    )
    mod.main()
    assert [c for c in _gate_calls(calls) if c[0] == "uv"] == []
    assert "gate skipped, uv not on PATH" in capsys.readouterr().err


def test_revalidate_records_a_timed_out_gate_as_a_failure(monkeypatch, tmp_path, capsys):
    """`uv run` resolves an environment on a cold cache; unbounded, an unreachable
    index blocked the session forever with no output. Bounded, it must surface."""
    mod, _ = _revalidate(
        monkeypatch,
        tmp_path,
        status=_Result(stdout=" M skills/nitpicker/SKILL.md\\n"),
        gate=lambda cmd: subprocess.TimeoutExpired(cmd, 120),
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "timed out after" in capsys.readouterr().err


def test_revalidate_records_a_gate_that_cannot_run_as_a_failure(monkeypatch, tmp_path, capsys):
    """An OSError from exec (permissions, ENOEXEC) must name the gate, not raise."""
    mod, _ = _revalidate(
        monkeypatch,
        tmp_path,
        status=_Result(stdout=" M skills/nitpicker/SKILL.md\\n"),
        gate=lambda cmd: OSError("exec format error"),
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "could not run" in capsys.readouterr().err


def test_revalidate_returns_when_git_status_cannot_run(monkeypatch, tmp_path, capsys):
    """git absent or the status call timing out means nothing to scope against —
    return rather than block or raise."""
    mod, calls = _revalidate(
        monkeypatch, tmp_path, status=subprocess.TimeoutExpired(["git", "status"], 120)
    )
    mod.main()
    assert _gate_calls(calls) == []
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""''',
    ),
    (
        # Anchored on the TAIL of the block the previous edit inserted, so these
        # append after it. Re-using that edit's anchor would re-insert the whole
        # v1 block and duplicate every function in it.
        "tests: the reliability and guard cases",
        '''def test_revalidate_returns_when_git_status_cannot_run(monkeypatch, tmp_path, capsys):
    """git absent or the status call timing out means nothing to scope against —
    return rather than block or raise."""
    mod, calls = _revalidate(
        monkeypatch, tmp_path, status=subprocess.TimeoutExpired(["git", "status"], 120)
    )
    mod.main()
    assert _gate_calls(calls) == []
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""''',
        '''def test_revalidate_returns_when_git_status_cannot_run(monkeypatch, tmp_path, capsys):
    """git absent or the status call timing out means nothing to scope against —
    return rather than block or raise."""
    mod, calls = _revalidate(
        monkeypatch, tmp_path, status=subprocess.TimeoutExpired(["git", "status"], 120)
    )
    mod.main()
    assert _gate_calls(calls) == []
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── reliability-397b7fec: every hook subprocess call is bounded ───────────────


def test_every_hook_subprocess_call_passes_a_timeout():
    """An unbounded shell-out in a hook freezes the session with no output and no
    recovery short of interrupting it. This is a source-level assertion rather
    than a behavioural one so a NEW call site cannot land unbounded."""
    import ast

    unbounded = []
    for path in sorted(HOOKS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and getattr(node.func.value, "id", "") == "subprocess"
                and not any(k.arg == "timeout" for k in node.keywords)
            ):
                unbounded.append(f"{path.name}:{node.lineno}")
    assert unbounded == [], f"unbounded subprocess.run call sites: {unbounded}"


@pytest.mark.parametrize(
    "name,event",
    [
        ("validate-skill-hook", {"tool_input": {"file_path": "skills/x/SKILL.md"}}),
        ("check-version-sync-hook", {"tool_input": {"file_path": "package.json"}}),
        ("validate-rules-hook", {"tool_input": {"file_path": ".claude/rules/x.md"}}),
    ],
)
def test_hook_is_silent_when_its_gate_cannot_run(name, event, monkeypatch, capsys, tmp_path):
    """uv absent (FileNotFoundError) or the gate hung (TimeoutExpired): the hook
    must return, not raise a traceback and not block the edit."""
    mod = _load(name)

    def _boom(*a, **k):
        raise FileNotFoundError("uv")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps(event), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_ruff_hook_is_silent_when_ruff_hangs(monkeypatch, tmp_path, capsys):
    """ruff-hook fires on every .py edit and shells out three times, so it is the
    likeliest place for an unbounded call to freeze a session."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ruff")

    def _hang(*a, **k):
        raise subprocess.TimeoutExpired(["ruff"], 120)

    monkeypatch.setattr(mod.subprocess, "run", _hang)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_stop_reminder_is_silent_when_git_cannot_run(monkeypatch, tmp_path, capsys):
    """A Stop hook that raises replaces the reminder with a traceback."""
    mod = _load("stop-reminder")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    def _boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── agent-loopholes-338dfd70: the protected-write half of the guard ──────────


def _guard_blocks(command: str) -> bool:
    """True if deny-agents-path-hook would block this Bash command."""
    mod = _load("deny-agents-path-hook")
    return mod._references_agents(command) or mod._writes_protected(command)


@pytest.mark.parametrize(
    "command",
    [
        "sed -i 's/PROTECTED/x/' scripts/hooks/deny-unsafe-git-hook.py",
        "sed --in-place s/a/b/ scripts/hooks/ruff-hook.py",
        "echo '{}' > .claude/settings.json",
        "echo x >> scripts/hooks/ruff-hook.py",
        "cp /tmp/evil.py scripts/hooks/ruff-hook.py",
        "mv /tmp/evil.py scripts/hooks/_hooklib.py",
        "rm scripts/hooks/deny-unsafe-git-hook.py",
        "truncate -s 0 .claude/settings.json",
        "cd scripts/hooks && sed -i s/a/b/ ruff-hook.py",
        "git checkout -- scripts/hooks/ruff-hook.py",
        "git restore .claude/settings.json",
        "perl -i -pe s/a/b/ scripts/hooks/stop-reminder.py",
        "tee scripts/hooks/ruff-hook.py < /tmp/evil.py",
        "dd of=scripts/hooks/ruff-hook.py if=/tmp/evil.py",
        "chmod 000 scripts/hooks/deny-agents-path-hook.py",
        # `./` prefix is stripped before the prefix comparison.
        "rm ./scripts/hooks/ruff-hook.py",
    ],
)
def test_guard_blocks_a_write_to_the_enforcement_surface(command):
    """permissions.deny covers Edit/Write on these paths but never Bash, so a
    one-liner could disable every in-session guard unobserved."""
    assert _guard_blocks(command), command


@pytest.mark.parametrize(
    "command",
    [
        # Read is NOT denied for these paths — blocking reads would contradict
        # the permission model and break ordinary work.
        "cat scripts/hooks/ruff-hook.py",
        "grep -rn timeout scripts/hooks/",
        "head -20 .claude/settings.json",
        "python3 -m pytest tests/test_hooks.py",
        "ruff check scripts/hooks/ruff-hook.py",
        "sed -n '1,5p' scripts/hooks/ruff-hook.py",
        # Mutations that land somewhere else entirely.
        "rm -rf /tmp/scratch",
        "git commit -m 'fix: something'",
        "cp README.md /tmp/README.md",
        "echo hi > /tmp/out.txt",
        "sed -i s/a/b/ README.md",
        # A `cd` to an absolute directory outside the repo: relative_to raises,
        # which must read as "not protected" rather than crashing the guard.
        "cd /tmp && rm scratch.txt",
        # `of=` with an empty tail — the split leaves nothing to resolve.
        "dd of= if=/tmp/x",
        # A glob that expands, but to nothing under a protected root.
        "rm scripts/*.py",
    ],
)
def test_guard_allows_reads_and_unrelated_writes(command):
    assert not _guard_blocks(command), command


def test_guard_blocks_a_glob_spelled_write(tmp_path):
    """A metacharacter that obscures the literal path is expanded through the same
    machinery the agents half uses, so it resolves rather than reading literally."""
    assert _guard_blocks("rm scripts/ho*ks/ruff-hook.py")


def test_guard_denial_message_names_the_surface(monkeypatch, capsys):
    mod = _load("deny-agents-path-hook")
    event = {"tool_input": {"command": "sed -i s/a/b/ scripts/hooks/ruff-hook.py"}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(event), monkeypatch)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "enforcement surface" in err
    assert "Reading" in err''',
    ),
]

AUDIT_TEST_EDITS: list[tuple[str, str, str]] = [
    (
        "audit-hook tests: findings.py unrunnable on all three branches",
        '''def test_main_ignores_invalid_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    hook.main()
    assert capsys.readouterr().out == ""''',
        '''def test_main_ignores_invalid_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    hook.main()
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "rel,text",
    [
        ("docs/audit/findings/security/open/security-1a2b3c4d.md", "x"),
        ("docs/audit/findings/resolved.jsonl", "{}\\n"),
        ("docs/audit/findings/INDEX.md", "x"),
    ],
)
def test_main_is_silent_when_findings_py_cannot_run(rel, text, tmp_path, monkeypatch, capsys):
    """python3/findings.py absent, or the call hung past its timeout: the hook
    must return rather than raise a traceback or block the edit. Each of the
    three shell-outs (per-file validate, store validate, index) is covered.
    `make check` and CI remain the gate."""
    path = _store_file(tmp_path, rel, text)
    monkeypatch.setattr(hook, "REPO_ROOT", tmp_path)

    def _boom(*a, **k):
        raise FileNotFoundError("python3")

    monkeypatch.setattr(hook.subprocess, "run", _boom)
    event = json.dumps({"tool_input": {"file_path": str(path)}})
    monkeypatch.setattr(sys, "stdin", io.StringIO(event))
    hook.main()
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""''',
    ),
]

TARGETS: list[tuple[Path, list[tuple[str, str, str]]]] = [
    (H / "_hooklib.py", HOOKLIB_EDITS),
    (H / "post-bash-revalidate.py", REVALIDATE_EDITS),
    (H / "ruff-hook.py", RUFF_EDITS),
    (H / "validate-skill-hook.py", VSKILL_EDITS),
    (H / "validate-rules-hook.py", VRULES_EDITS),
    (H / "check-version-sync-hook.py", VSYNC_EDITS),
    (H / "validate-audit-findings-hook.py", VAUDIT_EDITS),
    (H / "stop-reminder.py", STOP_EDITS),
    (H / "deny-agents-path-hook.py", GUARD_EDITS),
    (TESTS, TEST_EDITS),
    (REPO / "tests" / "test_validate_audit_findings_hook.py", AUDIT_TEST_EDITS),
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
                f"       {rel} drifted from the audited revision — re-read it and\n"
                f"       update this script rather than forcing the edit.",
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
    ap = argparse.ArgumentParser(description="Apply the owner-only audit findings.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    # Two passes: verify every anchor across every file before writing any of
    # them, so a drifted file cannot leave the enforcement surface half-patched.
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
