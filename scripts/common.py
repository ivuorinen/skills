"""Shared utilities for ivuorinen-skills scripts."""

import importlib.util
from pathlib import Path

# Single source of truth for the SKILL.md frontmatter parser: the shipped,
# stdlib-only findings.py. Internal tooling depending on a shipped tool points
# the dependency the safe direction — shipped tools ship without scripts/, so
# the shipped tool can never import back into here. Same precedent as
# scripts/validate-rules.py, which path-loads check-rules-anatomy.py.
_FINDINGS_PATH = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "findings.py"
_spec = importlib.util.spec_from_file_location("findings_for_common", _FINDINGS_PATH)
_findings = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_findings)  # type: ignore[union-attr]

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
