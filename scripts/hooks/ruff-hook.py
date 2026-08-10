#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# dependencies = ["ruff==0.16.2"]  # keep in sync with the pyproject.toml dev pin
# ///
"""PostToolUse hook — run ruff check --fix and ruff format on edited Python files."""

import shutil
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
    """Auto-fix and format an edited Python file, then report what remains.

    Fix and format are captured and reported alongside the final check: a
    fix or format pass that itself fails (bad config, a syntax error) would
    otherwise leave the check reporting a lint failure whose real cause
    appears nowhere in the output.
    """
    path = event_path()
    if path is None:
        return

    # Only act on files inside the project; ignore anything resolving outside it.
    if path.suffix != ".py" or not path.is_relative_to(REPO_ROOT.resolve()) or not path.exists():
        return

    if shutil.which("ruff") is None:
        return  # ruff unavailable — CI's ruff steps remain the gate

    # auto-fix what ruff can, then format. Capture both: a fix/format pass that
    # itself fails (bad config, syntax error) otherwise leaves the check below
    # reporting a lint failure whose real cause appears nowhere in the output.
    fix = fmt = None
    try:
        fix = subprocess.run(
            ["ruff", "check", "--fix", "--quiet", str(path)],
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
        fmt = subprocess.run(
            ["ruff", "format", "--quiet", str(path)],
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
        # report any remaining lint errors
        result = subprocess.run(
            ["ruff", "check", str(path)],
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        # ruff vanished between the which() above and here, or hung mid-run.
        # This hook fires on every .py edit and shells out three times, so an
        # unbounded call here is the likeliest place to freeze a session.
        #
        # A completed failure is not discarded by a later tool error: if fix or
        # format already reported one, that result is real and has to surface,
        # or the tool error silently erases an enforcement outcome.
        prior = "".join(r.stdout + r.stderr for r in (fix, fmt) if r and r.returncode != 0)
        if prior.strip():
            print(prior.rstrip(), file=sys.stderr, flush=True)
            sys.exit(2)
        return  # nothing had failed yet — CI's ruff steps remain the gate
    # Every completed call counts, not just the last. A fix or format pass that
    # failed on its own (bad config, a syntax error) is reported even when the
    # final check comes back clean: its output is the only place that cause
    # appears, which is why both results are captured at all. Ordering is
    # fix, fmt, result, so the report reads as it always did.
    failed = [r for r in (fix, fmt, result) if r.returncode != 0]
    if failed:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        report = "".join(r.stdout + r.stderr for r in failed)
        print(report.rstrip(), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
