#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Bump version across all JSON manifests and pyproject.toml.

Usage: ./scripts/bump-version.py [major|minor|patch]
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

# Seconds. `uv lock` resolves from the network on a cold cache; bounded so a
# hung resolve fails the bump rather than hanging it with no output.
LOCK_TIMEOUT = 120

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
    """Bump one component of a MAJOR.MINOR.PATCH string, resetting the lower ones.

    Refuses anything that is not three plain integers rather than bumping what
    it can parse: this value is written into several manifests at once, and a
    version that only half-matches produces a set that disagrees with itself —
    which the sync check then reports as drift rather than as a bad input here.
    """
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version.strip())
    if not m:
        sys.exit(f"error: version {version!r} is not in MAJOR.MINOR.PATCH form")
    major, minor, patch = (int(x) for x in m.groups())
    # A plain if-chain rather than `match`. Every branch returns and the final
    # `raise` terminates, so no path falls off the end returning None — which
    # `match` also achieved through its `case _`, but only for a reader that
    # models the statement as exhaustive. CodeQL does not, and reported the
    # function as mixing explicit returns with an implicit one.
    #
    # Removing the `match` has a second effect worth having: semgrep cannot
    # parse `match` and drops the whole file when it meets one, so this form
    # keeps the file under that scanner too.
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"error: unknown part {part!r} (expected major|minor|patch)")


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


def relock() -> bool:
    """Rewrite uv.lock's copy of the project version. True if it is now in sync.

    uv.lock records the root package's version in its own `[[package]]` entry,
    and release-please has no updater for it — 3.0.0 shipped with the lockfile
    still declaring 2.0.0. `make lock-check` now fails on that drift, so a bump
    that skipped this step would leave the tree failing its own gate.

    Returns False (never raises) when uv is absent or the lock cannot be
    regenerated: the manifests are already written by then, so aborting would
    leave the bump half-applied. The caller reports it as a manual follow-up.
    """
    if (uv := shutil.which("uv")) is None:
        print("  SKIPPED uv.lock: uv not on PATH")
        return False
    if not (REPO_ROOT / "uv.lock").exists():
        print("  SKIPPED uv.lock: no lockfile in this tree")
        return False
    try:
        # argv is a literal plus a resolved absolute path, never user input.
        result = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit
            [uv, "lock"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=LOCK_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        print(f"  ERROR   uv.lock: `uv lock` timed out after {LOCK_TIMEOUT}s")
        return False
    except OSError as exc:
        print(f"  ERROR   uv.lock: `uv lock` could not run: {exc}")
        return False
    if result.returncode != 0:
        detail = (result.stderr + result.stdout).strip().splitlines()
        print(f"  ERROR   uv.lock: `uv lock` failed — {detail[-1] if detail else 'no output'}")
        return False
    print("  updated uv.lock")
    return True


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

    # After pyproject is on disk, so `uv lock` reads the new version.
    locked = relock()

    print()
    print("Next steps:")
    if not locked:
        print("  0. Run `uv lock` — uv.lock still names the old version, and")
        print("     `make lock-check` fails until it does not")
    print(f"  1. Add an entry to CHANGELOG.md for v{new_version}")
    print(f"  2. git add -A && git commit -m 'chore: release v{new_version}'")
    print(f"  3. git tag v{new_version}")
    print("  4. git push && git push --tags")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
