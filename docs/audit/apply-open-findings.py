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

After applying, add the matching cases to tests/test_hooks.py (which already has
the hook-loading harness) and run `make check` before committing.
"""

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TARGET = REPO / "scripts" / "hooks" / "post-bash-revalidate.py"

# (description, anchor that must appear exactly once, replacement)
EDITS: list[tuple[str, str, str]] = [
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
        # git absent, or the tree so slow the status timed out. A PostToolUse
        # hook that blocks has no user-visible recovery, so bound it and skip.
        return
    if status.returncode != 0:
        return  # not a git tree — nothing to scope against""",
    ),
    (
        "gates: preflight the binary and bound the call",
        """        if not (REPO_ROOT / script).exists():
            # gate script absent (partial checkout) — CI remains the gate, but a
            # silently skipped gate is indistinguishable from a passing one.
            print(f"  post-bash-revalidate: gate skipped, {script} not found", file=sys.stderr)
            continue
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)""",
        """        if not (REPO_ROOT / script).exists():
            # gate script absent (partial checkout) — CI remains the gate, but a
            # silently skipped gate is indistinguishable from a passing one.
            print(f"  post-bash-revalidate: gate skipped, {script} not found", file=sys.stderr)
            continue
        if shutil.which(cmd[0]) is None:
            # Same reasoning as the missing-script arm above: the existence check
            # covered the gate script but never the interpreter, so an absent
            # `uv` raised an uncaught FileNotFoundError instead of this message.
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
    (
        "GATE_TIMEOUT constant",
        '''FINDINGS = "skills/nitpicker/scripts/findings.py"''',
        """FINDINGS = "skills/nitpicker/scripts/findings.py"

# Seconds. Generous enough for a cold `uv run` that resolves an environment,
# short enough that a hung gate surfaces as a failure rather than a frozen
# session. deny-unsafe-git-hook.py uses 10 for a bare `git rev-parse`.
GATE_TIMEOUT = 120""",
    ),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="verify anchors, write nothing")
    args = ap.parse_args()

    if not TARGET.exists():
        print(f"ERROR  {TARGET} not found", file=sys.stderr)
        return 1

    text = TARGET.read_text(encoding="utf-8")
    original = text

    for desc, anchor, replacement in EDITS:
        found = text.count(anchor)
        if found != 1:
            print(
                f"ERROR  {desc}: anchor matched {found} times, want exactly 1.\n"
                f"       The file drifted from the audited revision — re-read it "
                f"and update this script rather than forcing the edit.",
                file=sys.stderr,
            )
            return 1
        text = text.replace(anchor, replacement, 1)
        print(f"OK     {desc}")

    if args.check:
        print("\nAll anchors matched. Re-run without --check to apply.")
        return 0

    if text == original:
        print("\nNothing to do — already applied.")
        return 0

    TARGET.write_text(text, encoding="utf-8")
    print(f"\nApplied to {TARGET.relative_to(REPO)}")
    print("Next: add cases to tests/test_hooks.py, then run `make check`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
