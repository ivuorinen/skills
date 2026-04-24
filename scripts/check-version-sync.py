#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Verify that version is consistent across all manifests.

Exits 1 if any file disagrees with package.json.
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

CHECKS = [
    (".claude-plugin/plugin.json", lambda o: o["version"]),
    (".claude-plugin/marketplace.json", lambda o: o["plugins"][0]["version"]),
    (".release-please-manifest.json", lambda o: o["."]),
]


def read_json(rel_path: str) -> dict:
    return json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))


def read_toml_version(rel_path: str) -> str:
    content = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not m:
        raise KeyError("version field not found")
    return m.group(1)


base = read_json("package.json")["version"]
print(f"Reference version (package.json): {base}")

fail = False

try:
    toml_ver = read_toml_version("pyproject.toml")
    if toml_ver != base:
        print(f"  MISMATCH  pyproject.toml: {toml_ver} (expected {base})")
        fail = True
    else:
        print(f"  OK        pyproject.toml: {toml_ver}")
except KeyError as e:
    print(f"  ERROR     pyproject.toml: {e}")
    fail = True

for rel_path, extract in CHECKS:
    try:
        val = extract(read_json(rel_path))
    except (KeyError, IndexError) as e:
        print(f"  ERROR     {rel_path}: cannot read version — {e}")
        fail = True
        continue

    if val != base:
        print(f"  MISMATCH  {rel_path}: {val} (expected {base})")
        fail = True
    else:
        print(f"  OK        {rel_path}: {val}")

if fail:
    print("\nVersion mismatch detected. Run ./scripts/bump-version.py to resync.")
    sys.exit(1)

print("\nAll versions in sync.")
