"""Shared utilities for ivuorinen-skills scripts."""

import importlib.util
import sys
from importlib.machinery import ModuleSpec
from pathlib import Path
from types import ModuleType


def load_spec(spec: ModuleSpec | None, path: Path) -> ModuleType:
    """Execute the module `spec` describes, loaded from `path`, and return it.

    The one checked copy of the path-load tail (audit-b7943908): the copies it
    replaces suppressed pyright over an Optional they never checked, so a moved
    script failed as `'NoneType' object has no attribute 'loader'` rather than
    naming the path. It is registered in `sys.modules` before it runs, because a
    dataclass resolves its annotations through `sys.modules[cls.__module__]`.

    It takes the spec rather than the path on purpose: the caller writes
    `spec_from_file_location` with its literal path, which is what
    check-ring-deps.py resolves into an edge. A helper taking the path would
    hide every such edge behind one parameter the tool cannot resolve.
    """
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load a module from {path}: no module loader for it")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Single source of truth for the SKILL.md frontmatter parser: the shipped,
# stdlib-only findings.py. Internal tooling depending on a shipped tool points
# the dependency the safe direction — shipped tools ship without scripts/, so
# the shipped tool can never import back into here. Same precedent as
# scripts/validate-rules.py, which path-loads check-rules-anatomy.py.
_FINDINGS_PATH = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "findings.py"
_findings = load_spec(
    importlib.util.spec_from_file_location("findings_for_common", _FINDINGS_PATH), _FINDINGS_PATH
)

# The shipped fence rule (``` and ~~~, length-aware). Internal validators strip
# fences through it rather than a private copy that drifts from it: validate-skill
# once paired backtick runs with a regex and scanned the wrong lines
# (audit-4562b342).
_MD_FENCES_PATH = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "md_fences.py"
md_fences = load_spec(
    importlib.util.spec_from_file_location("md_fences_for_common", _MD_FENCES_PATH),
    _MD_FENCES_PATH,
)

# Re-exported so callers (and tests) keep importing it from this module.
parse_frontmatter = _findings.parse_frontmatter


def collect_skills(base: Path) -> list[tuple[str, str]]:
    """Return (name, description) for all skills under base, sorted by name."""
    results = []
    for skill_md in sorted(base.glob("*/SKILL.md")):
        fm, _ = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
        name = fm.get("name", "").strip() or skill_md.parent.name
        description = fm.get("description", "").strip() or "(no description)"
        results.append((name, description))
    return results
