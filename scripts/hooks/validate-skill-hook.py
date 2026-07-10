#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate SKILL.md after Write or Edit."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import event_path, repo_root  # noqa: E402  # type: ignore[import-not-found]

REPO_ROOT = repo_root()


def main() -> None:
    path = event_path()
    if path is None:
        return

    # Only skill files under the repo's skills/ or .claude/skills/ trees count.
    if not path.is_relative_to(REPO_ROOT.resolve()):
        return
    rel = path.relative_to(REPO_ROOT.resolve())
    in_skills_tree = rel.parts[:1] == ("skills",) or rel.parts[:2] == (".claude", "skills")
    is_skill = path.name == "SKILL.md" and in_skills_tree
    is_command = path.suffix == ".md" and path.parent.name == "commands" and in_skills_tree
    if not (is_skill or is_command):
        return

    # A command-file edit is validated through its parent SKILL.md (table sync, format).
    target = path if is_skill else path.parent.parent / "SKILL.md"

    validator = REPO_ROOT / "scripts" / "validate-skill.py"
    if not validator.exists():
        return

    result = subprocess.run(
        ["uv", "run", "--quiet", str(validator), str(target)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print((result.stdout + result.stderr).rstrip(), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
