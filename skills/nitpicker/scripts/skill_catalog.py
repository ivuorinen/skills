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
_HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*$")


def _slug(text: str) -> str:
    """`Security and data` -> `security-and-data`, so a caller may spell either.

    Category names are prose headings in SKILL.md, and a filter argument arrives
    as whatever the user typed. Comparing slugs makes case, punctuation, and the
    space-vs-hyphen choice all irrelevant instead of turning them into failed
    calls.
    """
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


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


def _filter_category(rows: list[dict], category: str) -> list[dict]:
    """The rows in one category, or a ValueError naming every known category.

    Split out of `list_commands` so that function stays under the cyclomatic
    ceiling the repo's static analysis enforces; parsing the tables and selecting
    from the parsed rows are independent, and the split keeps each readable.

    Raises rather than returning `[]`, because an empty list reads as "this
    category has no commands" — indistinguishable from a typo, and the caller
    would carry on with nothing.
    """
    want = _slug(category)
    matched = [c for c in rows if _slug(c["category"]) == want]
    if matched:
        return matched
    known = sorted({c["category"] for c in rows})
    raise ValueError(f"unknown category {category!r}; known categories: {', '.join(known)}")


def list_commands(root: Path | None = None, category: str = "") -> list[dict]:
    """Parse the nitpicker SKILL.md Commands tables → name, category, aliases, purpose.

    `category` is the heading a row sits under: the `###` group inside
    `## Commands` (`Review and fixing`, `Planning`, `Security and data`, …), or
    the `##` heading itself for a table with no subheading — which is how the
    internal `## Internal commands` rows stay distinguishable from public ones.
    The vocabulary is derived, never hardcoded: add a `###` group to SKILL.md and
    it is filterable in the same commit.

    Passing `category` filters to that group. An unknown value raises rather than
    returning `[]`, because an empty list reads as "this category has no
    commands" — indistinguishable from a typo, and the caller would carry on with
    nothing.
    """
    root = root or plugin_root()
    body = (_nitpicker_dir(root) / "SKILL.md").read_text(encoding="utf-8")
    out: list[dict] = []
    fence = ""
    section = ""  # nearest `##`; the category for a table with no `###` group
    group = ""  # nearest `###` under the current `##`
    for line in body.splitlines():
        opener = re.match(r"(`{3,}|~{3,})", line.lstrip())
        if fence:
            if opener and opener.group(1)[0] == fence[0] and len(opener.group(1)) >= len(fence):
                fence = ""
            continue
        if opener:
            fence = opener.group(1)
            continue
        head = _HEADING.match(line)
        if head:
            if len(head.group(1)) == 2:
                section, group = head.group(2), ""
            else:
                group = head.group(2)
            continue
        m = _CMD_ROW.match(line.strip())
        if not m or m.group(1) == "command":
            continue
        name, purpose = m.group(1), m.group(2)
        am = _ALIAS.search(purpose)
        aliases = _CODE.findall(am.group(1)) if am else []
        out.append(
            {"name": name, "category": group or section, "aliases": aliases, "purpose": purpose}
        )
    return _filter_category(out, category) if category else out


def read_command(command: str, root: Path | None = None) -> str:
    root = root or plugin_root()
    cmd_dir = _nitpicker_dir(root) / "commands"
    valid = {p.stem for p in cmd_dir.glob("*.md") if not p.name.startswith("_")}
    if command not in valid:
        raise KeyError(command)
    return (cmd_dir / f"{command}.md").read_text(encoding="utf-8")


def read_reference(name: str, root: Path | None = None) -> str:
    """Read a shared `_`-prefixed command file (`_conventions`, `_audit-coverage`).

    Separate from `read_command` on purpose: that one's contract is "a public
    command by the name the dispatcher resolved", and the shared files are not
    dispatchable — they have no row in SKILL.md's command tables and
    `list_commands` never returns them. Without this function the router's own
    step 1 (`_conventions.md` binds every command) had no tool and stayed a
    direct file read, which is the one gap that forced every session to fall
    back to the filesystem.

    The leading underscore is optional in the argument: prose cites the file as
    `_conventions.md` and the reader cites the section as `conventions`, so both
    resolve. Resolution stays a lookup in the enumerated set — no path is ever
    built from the argument, so `../` in a name misses the set and raises.
    """
    root = root or plugin_root()
    refs = {p.stem: p for p in (_nitpicker_dir(root) / "commands").glob("_*.md")}
    key = name if name.startswith("_") else f"_{name}"
    if key not in refs:
        raise KeyError(name)
    return refs[key].read_text(encoding="utf-8")
