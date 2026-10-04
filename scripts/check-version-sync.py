#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Verify that version is consistent across all manifests.

Usage:
    check-version-sync.py [--help]

Takes no arguments; checks the checkout it lives in against package.json.

Exit codes: 0 = all versions in sync, 1 = a manifest disagrees or cannot be
read, 2 = usage error (any argument other than --help).
"""

import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Each extractor returns a list of versions so a manifest with several
# version-bearing entries (marketplace.json's plugins array) is fully checked.
CHECKS = [
    (".claude-plugin/plugin.json", lambda o: [o["version"]]),
    (".claude-plugin/marketplace.json", lambda o: [p["version"] for p in o["plugins"]]),
    (".release-please-manifest.json", lambda o: [o["."]]),
]


def read_json(rel_path: str) -> dict:
    return json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))


def read_toml_version(rel_path: str) -> str:
    # tomllib (stdlib, 3.11+) parses [project].version correctly, ignoring
    # [tool.*] version keys. Malformed TOML is surfaced as KeyError so the
    # caller's (KeyError, OSError) handler reports it as a mismatch, not a crash.
    try:
        data = tomllib.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise KeyError(f"{rel_path} is not valid TOML: {e}") from e
    try:
        return data["project"]["version"]
    except (KeyError, TypeError) as e:
        raise KeyError("[project] version field not found") from e


def _answer_args(args: list[str]) -> int | None:
    """Exit code for `--help` (0) or any other argument (2); None to run the check.

    `--help` ran the whole check and printed its verdict at exit 0.
    """
    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0
    if args:
        print(
            f"Error: unexpected argument {args[0]!r}; check-version-sync.py takes only --help.",
            file=sys.stderr,
        )
        return 2
    return None


def main() -> int:
    early = _answer_args(sys.argv[1:])
    if early is not None:
        return early
    try:
        base = read_json("package.json")["version"]
    except (KeyError, OSError, json.JSONDecodeError) as e:
        print(f"  ERROR     package.json: cannot read version — {e}")
        return 1
    print(f"Reference version (package.json): {base}")

    fail = False

    try:
        toml_ver = read_toml_version("pyproject.toml")
        if toml_ver != base:
            print(f"  MISMATCH  pyproject.toml: {toml_ver} (expected {base})")
            fail = True
        else:
            print(f"  OK        pyproject.toml: {toml_ver}")
    except (KeyError, OSError) as e:
        print(f"  ERROR     pyproject.toml: {e}")
        fail = True

    for rel_path, extract in CHECKS:
        try:
            vals = extract(read_json(rel_path))
        # TypeError: a null/wrong-typed value (e.g. "plugins": null) breaks the
        # extractor's iteration — without it the loop aborts and the remaining
        # manifests go unchecked, masking a real mismatch.
        except (KeyError, IndexError, TypeError, OSError, json.JSONDecodeError) as e:
            print(f"  ERROR     {rel_path}: cannot read version — {e}")
            fail = True
            continue

        mismatched = [v for v in vals if v != base]
        if not vals:
            print(f"  ERROR     {rel_path}: no version entries found")
            fail = True
        elif mismatched:
            print(f"  MISMATCH  {rel_path}: {mismatched} (expected {base})")
            fail = True
        else:
            print(f"  OK        {rel_path}: {vals[0]}")

    if fail:
        print("\nVersion mismatch detected. Run ./scripts/bump-version.py to resync.")
        return 1

    print("\nAll versions in sync.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
