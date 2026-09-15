#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — refuse a findings-store MCP write while the shipped scripts are edited.

The MCP server imports the shipped modules once at startup and keeps executing
them, so after an edit under `skills/nitpicker/scripts` a store write runs code
that is no longer on disk. CLAUDE.md tells the agent to switch to the CLI, and
only a non-blocking `[warn]` prefix backed that — `np_process_sarif` carries
none. A stale `redact()` wrote an unredacted credential into the append-only
ledger that way (audit-9bc6eb39); this hook turns the mandate into a denial
(agent-hooks-eaa13a08).

Fails closed: when git cannot say whether the scripts are edited, the write is
refused, because a ledger record is permanent and the CLI is always available.

Ceiling: a clean tree does not prove the server is current. A commit made after
the server started, or the plugin-scoped server serving the installed copy at
another version, both pass here; the server's own mtime `[warn]` is what sees
the first of those.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event, repo_root

REPO_ROOT = repo_root()
SCRIPTS = "skills/nitpicker/scripts"

# The CLI spelling of each store-writing tool, which loads fresh on every call.
_CLI = {
    "np_new_finding": f"python3 {SCRIPTS}/findings.py new",
    "np_resolve_finding": f"python3 {SCRIPTS}/findings.py resolve",
    "np_write_index": f"python3 {SCRIPTS}/findings.py index",
    "np_process_sarif": f"python3 {SCRIPTS}/process-sarif.py",
}


def _edited() -> list[str] | None:
    """Porcelain entries under the shipped scripts, or None if git could not answer."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--", SCRIPTS],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.splitlines() if result.returncode == 0 else None


def main() -> None:
    """Deny a store write through the MCP server unless the shipped scripts are clean."""
    data = load_event()
    if data is None:
        return
    tool = str(data.get("tool_name") or "")
    cli = _CLI.get(tool.rsplit("__", 1)[-1])
    if cli is None:
        return
    edited = _edited()
    if edited == []:
        return
    state = (
        "in an unknown state: git could not report it"
        if edited is None
        else "edited: " + ", ".join(entry[3:] for entry in edited[:5])
    )
    print(
        f"  DENIED  {tool} writes the findings store through the MCP server, but\n"
        f"          {SCRIPTS} is {state}.\n"
        "          The server runs the modules it imported at startup, so this write\n"
        "          would run code that is not on disk. Use the CLI, which loads fresh:\n"
        f"          {cli}",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed — exit 1 would let the write through
        print(f"  DENIED  stale-write guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
