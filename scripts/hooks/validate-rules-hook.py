#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate .claude/rules/ files after Write or Edit.

Rule files constrain the agent itself but had no in-session validation: the
skill hook returns early on anything outside skills/, so a broken rule surfaced
only at commit time. Runs the same two gates pre-commit and CI run.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (
    HOOK_TIMEOUT,
    SHIPPED_ROOT,
    event_path,
    repo_root,
    report_skip,
)

REPO_ROOT = repo_root()
_HOOK = "validate-rules-hook"
_BY_HAND = (
    "uv run --quiet scripts/validate-rules.py"
    " && python3 skills/nitpicker/scripts/check-rules-anatomy.py ."
)


def main() -> None:
    """Validate an edited rule file, and the anatomy of the whole rules tree.

    Two checks rather than one: validate-rules.py judges the edited file,
    while check-rules-anatomy.py judges the tree — catching a rule that is
    well-formed on its own but stale against the paths it names.
    """
    path = event_path()
    if path is None:
        return

    # Containment spelled with `os.path.realpath` and `str.startswith` rather
    # than `Path.resolve()` and `Path.is_relative_to`. Equivalent for these
    # absolute paths, but only this form is one CodeQL recognises as a guard, so
    # the pathlib spelling left `path` tainted all the way into the argv below.
    # The `+ os.sep` matters: without it `.claude/rules-evil` counts as inside
    # `.claude/rules`.
    rules_dir = os.path.realpath(REPO_ROOT / ".claude" / "rules")
    candidate = os.path.realpath(path)
    if path.suffix != ".md" or not candidate.startswith(rules_dir + os.sep):
        return

    # Both scripts come from the checkout this hook ships in (`SHIPPED_ROOT`);
    # REPO_ROOT only supplies the subprocess `cwd`, the tree being validated.
    validator = SHIPPED_ROOT / "scripts" / "validate-rules.py"
    anatomy = SHIPPED_ROOT / "skills" / "nitpicker" / "scripts" / "check-rules-anatomy.py"
    if not validator.exists() or not anatomy.exists():
        report_skip(_HOOK, "validate-rules.py or check-rules-anatomy.py not found", _BY_HAND)

    output = []
    failed = False
    for cmd in (
        # `candidate`, not `path`: the argv carries the value that was checked,
        # not the one it was derived from. Passing `path` here validated one
        # string and used another — correct only by coincidence, and the reason
        # the guard above did not count as a barrier.
        # `--` terminates option parsing. Without it a rule file named
        # `-x.md` — legal on disk and inside .claude/rules/ — reaches `uv` and
        # the validator as a flag rather than an operand. A containment check
        # cannot prevent that, which is why it is not a barrier for
        # py/command-line-injection: the path is *inside* the tree and still
        # argument-injects.
        ["uv", "run", "--quiet", str(validator), "--", candidate],
        ["python3", str(anatomy), "."],
    ):
        try:
            # argv is one of the two literal command lists in the loop above.
            result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
                cmd,
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=HOOK_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            # Stop running validators, but fall through to the report below: a
            # failure already collected from an earlier one is a real result,
            # and returning here would discard it. With nothing collected, the
            # skip itself is the result and has to be said.
            if not failed:
                report_skip(_HOOK, f"{type(exc).__name__}: {exc}", _BY_HAND)
            break
        if result.returncode != 0:
            failed = True
            output.append((result.stdout + result.stderr).rstrip())

    if failed:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print("\n".join(o for o in output if o), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
