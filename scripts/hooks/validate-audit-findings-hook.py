#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate edited files in the docs/audit/findings/ store.

Runs `findings.py validate` on an edited open finding file (or a store-mode
validate when the resolved.jsonl ledger is edited) and, on success, regenerates
INDEX.md so it never drifts from the store. Never autofixes — the store is
written through findings.py, which only produces canonical files.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import event_path, repo_root  # noqa: E402  # type: ignore[import-not-found]

REPO_ROOT = repo_root()
FINDINGS = REPO_ROOT / "skills" / "nitpicker" / "scripts" / "findings.py"


def store_root(repo_root: Path) -> Path:
    return repo_root / "docs" / "audit" / "findings"


def should_check(path: Path, repo_root: Path) -> bool:
    # `path` is resolved (symlinks followed) by the caller, so resolve the root
    # too — otherwise a symlinked checkout makes is_relative_to falsely fail.
    root = store_root(repo_root).resolve()
    return (
        path.suffix == ".md"
        and path.name != "INDEX.md"
        and path.is_relative_to(root)
        and path.exists()
    )


def main() -> None:
    path = event_path()
    if path is None:
        return

    # An edit to INDEX.md itself still warrants regeneration so it never drifts.
    store = store_root(REPO_ROOT).resolve()
    in_store = path.is_relative_to(store)
    is_index = path.name == "INDEX.md" and in_store
    is_ledger = path.name == "resolved.jsonl" and in_store and path.exists()
    is_finding = should_check(path, REPO_ROOT)
    if not (is_index or is_ledger or is_finding):
        return

    # findings.py is a shipped skill tool: stdlib-only, run with plain python
    py = [sys.executable, str(FINDINGS)]
    if is_finding:
        result = subprocess.run(
            [*py, "validate", str(path)], capture_output=True, text=True, cwd=REPO_ROOT
        )
        if result.returncode != 0:
            # PostToolUse surfaces only exit 2 + stderr back to the agent.
            print(
                f"  audit-findings hook: {path.name} is not a valid finding file", file=sys.stderr
            )
            print((result.stdout or result.stderr).rstrip(), file=sys.stderr, flush=True)
            sys.exit(2)
    elif is_ledger:
        # The resolved ledger has no per-line file, so validate the store as a whole.
        result = subprocess.run([*py, "validate"], capture_output=True, text=True, cwd=REPO_ROOT)
        if result.returncode != 0:
            print("  audit-findings hook: resolved.jsonl failed store validation", file=sys.stderr)
            print((result.stdout or result.stderr).rstrip(), file=sys.stderr, flush=True)
            sys.exit(2)

    # No --root: cwd=REPO_ROOT lets findings.py resolve its DEFAULT_ROOT
    # (docs/audit/findings) and emit repo-relative paths, matching the canonical
    # `findings.py index` used by make check and CI. An absolute --root would
    # write absolute paths into INDEX.md and fail index-check.
    index = subprocess.run(
        [*py, "index"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if index.returncode != 0:
        print("  audit-findings hook: INDEX.md regeneration failed", file=sys.stderr)
        print((index.stderr or index.stdout).rstrip(), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
