#!/usr/bin/env python3
"""Apply the two audit findings an agent cannot: they live under permissions.deny.

Both fixes touch `scripts/hooks/`, which `.claude/settings.json` denies to the
Edit/Write tools, so the release-prep audit filed them open instead of applying
them. This script is the patch, written as anchored string replacements rather
than a unified diff so it fails loudly on drift instead of applying with fuzz.

    python3 docs/audit/apply-open-findings.py --check   # verify anchors only
    python3 docs/audit/apply-open-findings.py           # apply

Covers:
  agent-loopholes-338dfd70 (high, part 1) — put scripts/ and .claude/settings.json
      under post-bash-revalidate's GOVERNED list, so a Bash edit to the
      enforcement surface re-runs the gates instead of passing unobserved.
  reliability-397b7fec (medium, in post-bash-revalidate.py) — bound both
      subprocess calls with a timeout and preflight the gate binary, so a slow
      uv cannot hang the session and an absent uv cannot raise an uncaught
      FileNotFoundError.

The matching tests/test_hooks.py cases are applied too, so the patch lands
green: coverage runs at fail_under=100, and the three new branches would
otherwise drop it below the gate. Run `make check` before committing.

NOT covered — deliberately left for a human, because writing them blind risks
shipping a wrong guard:
  agent-loopholes-338dfd70 part 2 — generalising deny-agents-path-hook.py from
      an agents-only matcher to a protected-paths matcher. Its token coverage
      (literal, quoted, escaped, variable-built, glob-spelled) is intricate and
      needs its own test pass.
  reliability-397b7fec, the other 9 call sites — a shared runner in
      scripts/hooks/_hooklib.py routed through check-version-sync-hook,
      ruff-hook, stop-reminder, validate-audit-findings-hook, validate-rules-hook
      and validate-skill-hook.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "scripts" / "hooks" / "post-bash-revalidate.py"
TESTS = REPO / "tests" / "test_hooks.py"

# (description, anchor that must appear exactly once, replacement)
HOOK_EDITS: list[tuple[str, str, str]] = [
    (
        "GOVERNED: cover the enforcement surface itself",
        """GOVERNED = (
    "skills/",
    ".claude/rules/",""",
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
        '''def _revalidate(monkeypatch, tmp_path, *, status, gate=None, gates_on_disk=True):
    """Load the hook against a tmp REPO_ROOT with subprocess.run faked.

    `status` is the _Result for `git status`; `gate` is called with each gate's
    argv and returns that gate's _Result (default: success).
    """''',
        # Content starts at column 0 so the 98-char def line stays under ruff's
        # 100-col limit here as well as in the file it is written into.
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
        "tests: the new cases",
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
]

TARGETS: list[tuple[Path, list[tuple[str, str, str]]]] = [
    (HOOK, HOOK_EDITS),
    (TESTS, TEST_EDITS),
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
    ap = argparse.ArgumentParser(description="Apply the two owner-only audit findings.")
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    # Two passes: verify every anchor across both files before writing either, so
    # a drifted test file cannot leave the hook half-patched.
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
