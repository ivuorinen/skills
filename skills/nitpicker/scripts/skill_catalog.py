#!/usr/bin/env python3
"""List and read the plugin's bundled skills and the nitpicker commands.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required.

The plugin root is derived from this file's location
(`<root>/skills/nitpicker/scripts/skill_catalog.py`), so listing works no
matter the process cwd — which matters when the MCP server runs as an
installed plugin whose cwd is unspecified. Names are resolved only against the
enumerated skill/command set, never by building a path from raw input.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from findings import parse_frontmatter

_CMD_ROW = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|\s*(.+?)\s*\|$")
_ALIAS = re.compile(r"alias(?:es)?:\s*([^)]+)")
_CODE = re.compile(r"`([a-z0-9][a-z0-9-]*)`")


def plugin_root() -> Path:
    """Repo/plugin root = the parent of skills/nitpicker/scripts/."""
    return Path(__file__).resolve().parents[3]


def _skill_files(root: Path) -> list[Path]:
    # Only `skills/*` — the tier this plugin ships. `.claude/skills/` is the
    # internal dev tier here and the user's own private skill directory on a
    # consumer machine, so reading it would hand back skills this tool's
    # contract never promised.
    return sorted(root.glob("skills/*/SKILL.md"))


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
    fence = ""
    for line in body.splitlines():
        opener = re.match(r"(`{3,}|~{3,})", line.lstrip())
        if fence:
            if opener and opener.group(1)[0] == fence[0] and len(opener.group(1)) >= len(fence):
                fence = ""
            continue
        if opener:
            fence = opener.group(1)
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
