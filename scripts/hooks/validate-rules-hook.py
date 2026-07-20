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
from _hooklib import event_path, repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()


def main() -> None:
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
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if result.returncode != 0:
            failed = True
            output.append((result.stdout + result.stderr).rstrip())

    if failed:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print("\n".join(o for o in output if o), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
