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
    (
        ".claude-plugin/marketplace.json",
        lambda o, v: [p.__setitem__("version", v) for p in o["plugins"]],
    ),
    (".release-please-manifest.json", lambda o, v: o.__setitem__(".", v)),
]


def bump_version(version: str, part: str) -> str:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version.strip())
    if not m:
        sys.exit(f"error: version {version!r} is not in MAJOR.MINOR.PATCH form")
    major, minor, patch = (int(x) for x in m.groups())
    match part:
        case "major":
            return f"{major + 1}.0.0"
        case "minor":
            return f"{major}.{minor + 1}.0"
        case "patch":
            return f"{major}.{minor}.{patch + 1}"
        case _:
            sys.exit(f"error: unknown part {part!r} (expected major|minor|patch)")


def render_json(rel_path: str, mutate, version: str) -> str:
    """Return the updated JSON manifest content without writing it."""
    obj = json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
    mutate(obj, version)
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def update_toml(rel_path: str, version: str) -> str:
    """Return the updated pyproject content without writing it."""
    content = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    # Only replace version inside the [project] section, not in [tool.*] sections.
    in_project = False
    replaced = False
    result: list[str] = []
    for line in content.splitlines(keepends=True):
        if re.match(r"^\[project\]\s*$", line):
            in_project = True
        elif re.match(r"^\[", line):
            in_project = False
        if in_project and not replaced and re.match(r"""^version\s*=\s*["']""", line):
            line = re.sub(r"""^(version\s*=\s*)["'][^"']+["']""", rf'\g<1>"{version}"', line)
            replaced = True
        result.append(line)
    if not replaced:
        print(f"  ERROR  {rel_path}: [project] version not found — file unchanged", file=sys.stderr)
        sys.exit(1)
    return "".join(result)


def main() -> int:
    part = sys.argv[1] if len(sys.argv) > 1 else "patch"
    if part not in {"major", "minor", "patch"}:
        print(f"Usage: {sys.argv[0]} [major|minor|patch]")
        return 1

    current = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    new_version = bump_version(current, part)

    print(f"Bumping {current} → {new_version}")
    # Parse and render every manifest before writing any, so a malformed
    # file aborts the run without leaving the manifests half-updated.
    pending: list[tuple[str, str]] = [
        ("pyproject.toml", update_toml("pyproject.toml", new_version))
    ]
    pending += [
        (rel_path, render_json(rel_path, mutate, new_version)) for rel_path, mutate in FILES
    ]
    for rel_path, content in pending:
        (REPO_ROOT / rel_path).write_text(content, encoding="utf-8")
        print(f"  updated {rel_path}")

    print()
    print("Next steps:")
    print(f"  1. Add an entry to CHANGELOG.md for v{new_version}")
    print(f"  2. git add -A && git commit -m 'chore: release v{new_version}'")
    print(f"  3. git tag v{new_version}")
    print("  4. git push && git push --tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
