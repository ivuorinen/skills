#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruff"]
# ///
"""PostToolUse hook — run ruff check --fix and ruff format on edited Python files."""

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

    # Only act on files inside the project; ignore anything resolving outside it.
    if path.suffix != ".py" or not path.is_relative_to(REPO_ROOT.resolve()) or not path.exists():
        return

    # auto-fix what ruff can, then format
    subprocess.run(["ruff", "check", "--fix", "--quiet", str(path)], check=False)
    subprocess.run(["ruff", "format", "--quiet", str(path)], check=False)

    # report any remaining lint errors
    result = subprocess.run(
        ["ruff", "check", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print((result.stdout + result.stderr).rstrip(), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
