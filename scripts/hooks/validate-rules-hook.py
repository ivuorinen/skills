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
from _hooklib import (  # type: ignore[import-not-found]
    HOOK_TIMEOUT,
    event_path,
    repo_root,
)

REPO_ROOT = repo_root()

# The two scripts this hook runs ship beside it, so their paths are derived from
# `__file__` rather than from REPO_ROOT. REPO_ROOT comes from CLAUDE_PROJECT_DIR
# or REPO_ROOT, and while `repo_root()` refuses a value that does not point at
# this checkout, that is an existence test rather than a containment one — it
# left an environment-derived string interpolated into the argv below, reported
# as py/command-line-injection. A path built from `__file__` cannot be
# influenced by the environment at all, which is both the stronger guarantee and
# the simpler one to read. REPO_ROOT still supplies the subprocess `cwd`, which
# is the tree being validated rather than the code doing the validating.
_SHIPPED_ROOT = Path(__file__).resolve().parent.parent.parent


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

    validator = _SHIPPED_ROOT / "scripts" / "validate-rules.py"
    anatomy = _SHIPPED_ROOT / "skills" / "nitpicker" / "scripts" / "check-rules-anatomy.py"
    if not validator.exists() or not anatomy.exists():
        return

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
        except (OSError, subprocess.SubprocessError):
            # Stop running validators, but fall through to the report below: a
            # failure already collected from an earlier one is a real result,
            # and returning here would discard it.
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
