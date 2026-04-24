#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Bump version across all JSON manifests and pyproject.toml.

Usage: ./scripts/bump-version.py [major|minor|patch]
"""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

FILES = [
    ("package.json", lambda o, v: o.__setitem__("version", v)),
    (".claude-plugin/plugin.json", lambda o, v: o.__setitem__("version", v)),
    (".claude-plugin/marketplace.json", lambda o, v: o["plugins"][0].__setitem__("version", v)),
    (".release-please-manifest.json", lambda o, v: o.__setitem__(".", v)),
]


def bump_version(version: str, part: str) -> str:
    major, minor, patch = (int(x) for x in version.split("."))
    match part:
        case "major":
            return f"{major + 1}.0.0"
        case "minor":
            return f"{major}.{minor + 1}.0"
        case _:
            return f"{major}.{minor}.{patch + 1}"


def update_file(rel_path: str, mutate, version: str) -> None:
    path = REPO_ROOT / rel_path
    obj = json.loads(path.read_text(encoding="utf-8"))
    mutate(obj, version)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    print(f"  updated {rel_path}")


def update_toml(rel_path: str, version: str) -> None:
    path = REPO_ROOT / rel_path
    content = path.read_text(encoding="utf-8")
    new_content = re.sub(
        r'^(version\s*=\s*")[^"]+(")',
        rf"\g<1>{version}\2",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if new_content == content:
        print(f"  ERROR  {rel_path}: version line not found — file unchanged", file=sys.stderr)
        sys.exit(1)
    path.write_text(new_content, encoding="utf-8")
    print(f"  updated {rel_path}")


part = sys.argv[1] if len(sys.argv) > 1 else "patch"
if part not in {"major", "minor", "patch"}:
    print(f"Usage: {sys.argv[0]} [major|minor|patch]")
    sys.exit(1)

current = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["version"]
new_version = bump_version(current, part)

print(f"Bumping {current} → {new_version}")
update_toml("pyproject.toml", new_version)
for rel_path, mutate in FILES:
    update_file(rel_path, mutate, new_version)

print()
print("Next steps:")
print(f"  1. Add an entry to CHANGELOG.md for v{new_version}")
print(f"  2. git add -A && git commit -m 'chore: release v{new_version}'")
print(f"  3. git tag v{new_version}")
print("  4. git push && git push --tags")
