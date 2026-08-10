#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate .claude/rules/ files after Write or Edit.

Rule files constrain the agent itself but had no in-session validation: the
skill hook returns early on anything outside skills/, so a broken rule surfaced
only at commit time. Runs the same two gates pre-commit and CI run.
"""

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


def main() -> None:
    """Validate an edited rule file, and the anatomy of the whole rules tree.

    Two checks rather than one: validate-rules.py judges the edited file,
    while check-rules-anatomy.py judges the tree — catching a rule that is
    well-formed on its own but stale against the paths it names.
    """
    path = event_path()
    if path is None:
        return

    root = REPO_ROOT.resolve()
    if path.suffix != ".md" or not path.is_relative_to(root / ".claude" / "rules"):
        return

    validator = REPO_ROOT / "scripts" / "validate-rules.py"
    anatomy = REPO_ROOT / "skills" / "nitpicker" / "scripts" / "check-rules-anatomy.py"
    if not validator.exists() or not anatomy.exists():
        return

    output = []
    failed = False
    for cmd in (
        ["uv", "run", "--quiet", str(validator), str(path)],
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
