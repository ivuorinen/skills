#!/usr/bin/env python3
"""List and read the plugin's bundled skills and the nitpicker commands.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required.

The plugin root is derived from this file's location
(`<root>/skills/nitpicker/scripts/skill_catalog.py`), so listing works no
matter the process cwd — which matters when the MCP server runs as an
installed plugin whose cwd is unspecified. Names are resolved only against the
enumerated skill/command set, never by building a path from raw input.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from findings import parse_frontmatter  # noqa: E402  (sibling shipped module)

_CMD_ROW = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|\s*(.+?)\s*\|$")
_ALIAS = re.compile(r"alias(?:es)?:\s*([^)]+)")
_CODE = re.compile(r"`([a-z0-9][a-z0-9-]*)`")


def plugin_root() -> Path:
    """Repo/plugin root = the parent of skills/nitpicker/scripts/."""
    return Path(__file__).resolve().parents[3]


def _skill_files(root: Path) -> list[Path]:
    # `.claude/skills/nitpicker` is a symlink to `skills/nitpicker`, so both
    # globs can resolve to the same real SKILL.md — dedupe by real path,
    # keeping the first (skills/* before .claude/skills/*).
    seen: set[Path] = set()
    files: list[Path] = []
    for path in sorted(root.glob("skills/*/SKILL.md")) + sorted(
        root.glob(".claude/skills/*/SKILL.md")
    ):
        real = path.resolve()
        if real not in seen:
            seen.add(real)
            files.append(path)
    return files


def _nitpicker_dir(root: Path) -> Path:
    return root / "skills" / "nitpicker"


def list_skills(root: Path | None = None) -> list[dict]:
    root = root or plugin_root()
    out: list[dict] = []
    for path in _skill_files(root):
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        name = fm.get("name", path.parent.name)
        entry: dict = {
            "name": name,
            "description": fm.get("description", ""),
            "path": path.relative_to(root).as_posix(),
        }
        if name == "nitpicker":
            entry["commands"] = [c["name"] for c in list_commands(root=root)]
        out.append(entry)
    return out


def read_skill(name: str, root: Path | None = None) -> str:
    root = root or plugin_root()
    for path in _skill_files(root):
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if fm.get("name", path.parent.name) == name:
            return path.read_text(encoding="utf-8")
    raise KeyError(name)


def list_commands(root: Path | None = None) -> list[dict]:
    """Parse the nitpicker SKILL.md Commands tables → name, aliases, purpose."""
    root = root or plugin_root()
    body = (_nitpicker_dir(root) / "SKILL.md").read_text(encoding="utf-8")
    out: list[dict] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _CMD_ROW.match(line.strip())
        if not m or m.group(1) == "command":
            continue
        name, purpose = m.group(1), m.group(2)
        am = _ALIAS.search(purpose)
        aliases = _CODE.findall(am.group(1)) if am else []
        out.append({"name": name, "aliases": aliases, "purpose": purpose})
    return out


def read_command(command: str, root: Path | None = None) -> str:
    root = root or plugin_root()
    cmd_dir = _nitpicker_dir(root) / "commands"
    valid = {p.stem for p in cmd_dir.glob("*.md") if not p.name.startswith("_")}
    if command not in valid:
        raise KeyError(command)
    return (cmd_dir / f"{command}.md").read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list skills")
    p_rs = sub.add_parser("read", help="print a skill's SKILL.md")
    p_rs.add_argument("name")
    sub.add_parser("commands", help="list nitpicker commands")
    p_rc = sub.add_parser("read-command", help="print a command file")
    p_rc.add_argument("command")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for s in list_skills():
            print(f"{s['name']:20} {s['description'][:70]}")
    elif args.cmd == "read":
        print(read_skill(args.name), end="")
    elif args.cmd == "commands":
        for c in list_commands():
            extra = f"  (aliases: {', '.join(c['aliases'])})" if c["aliases"] else ""
            print(f"{c['name']:20}{extra}")
    elif args.cmd == "read-command":
        print(read_command(args.command), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
