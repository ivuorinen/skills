#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — revalidate the governed trees after a Bash tool call.

The five Write|Edit validators never see a Bash-mediated mutation (`sed -i`,
`>` redirection, `git mv`, `cp`, `patch`), so those edits bypassed the whole
enforcement surface. A Bash event carries no file_path, so this hook asks git
what is dirty instead, and runs the whole-tree gates only when something under
a governed path changed — a read-only Bash call costs one `git status`.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import repo_root  # type: ignore[import-not-found]

REPO_ROOT = repo_root()

# Substring markers — a porcelain line mentioning any of these is governed.
# ponytail: substring match, not per-entry parsing; a false positive only costs
# one validator run, and rename entries stay covered either way.
GOVERNED = (
    "skills/",
    ".claude/rules/",
    ".claude/agents/",
    "docs/audit/findings/",
    "package.json",
    "pyproject.toml",
    ".release-please-manifest.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
)

FINDINGS = "skills/nitpicker/scripts/findings.py"
# (script it needs on disk, argv) — a missing script is skipped, not a traceback.
GATES = (
    ("scripts/validate-skill.py", ["uv", "run", "--quiet", "scripts/validate-skill.py"]),
    ("scripts/validate-rules.py", ["uv", "run", "--quiet", "scripts/validate-rules.py"]),
    ("scripts/check-version-sync.py", ["uv", "run", "--quiet", "scripts/check-version-sync.py"]),
    ("scripts/check-stdlib-only.py", ["uv", "run", "--quiet", "scripts/check-stdlib-only.py"]),
    (FINDINGS, ["python3", FINDINGS, "validate"]),
    (FINDINGS, ["python3", FINDINGS, "index"]),
)


def main() -> None:
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return  # not a git tree — nothing to scope against
    if not any(marker in status.stdout for marker in GOVERNED):
        return

    failures = []
    for script, cmd in GATES:
        if not (REPO_ROOT / script).exists():
            # gate script absent (partial checkout) — CI remains the gate, but a
            # silently skipped gate is indistinguishable from a passing one.
            print(f"  post-bash-revalidate: gate skipped, {script} not found", file=sys.stderr)
            continue
        result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if result.returncode != 0:
            failures.append((result.stdout + result.stderr).rstrip())

    if failures:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print("\n".join(f for f in failures if f), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
