#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — warn on version mismatch after editing a version-bearing manifest.

Covers JSON manifests (package.json, plugin.json, marketplace.json,
.release-please-manifest.json) and pyproject.toml.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import event_path, repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()

VERSION_FILES = {
    Path("package.json"),
    Path(".claude-plugin/plugin.json"),
    Path(".claude-plugin/marketplace.json"),
    Path(".release-please-manifest.json"),
    Path("pyproject.toml"),
}


def main() -> None:
    path = event_path()
    if path is None:
        return

    if not path.is_relative_to(REPO_ROOT.resolve()):
        return
    if path.relative_to(REPO_ROOT.resolve()) not in VERSION_FILES:
        return

    checker = REPO_ROOT / "scripts" / "check-version-sync.py"
    if not checker.exists():
        return

    result = subprocess.run(
        ["uv", "run", "--quiet", str(checker)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    problems = [
        line for line in result.stdout.splitlines() if "MISMATCH" in line or "ERROR" in line
    ]
    if problems or result.returncode != 0:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        for line in problems:
            print(line, file=sys.stderr)
        if result.returncode != 0 and not problems:
            print((result.stdout.strip() or result.stderr.strip()), file=sys.stderr)
        print(
            "Run ./scripts/bump-version.py to resync all version files.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
