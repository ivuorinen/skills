"""Tests for skills/nitpicker/scripts/skill_catalog.py."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "skill_catalog",
    Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "skill_catalog.py",
)
sc = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(sc)  # type: ignore[union-attr]


def test_plugin_root_is_repo_root():
    # skill_catalog.py lives at <root>/skills/nitpicker/scripts/, so parents[3] is <root>.
    assert (sc.plugin_root() / "skills" / "nitpicker" / "SKILL.md").is_file()


def test_list_skills_includes_nitpicker_with_commands():
    skills = sc.list_skills()
    names = {s["name"] for s in skills}
    assert "nitpicker" in names
    nit = next(s for s in skills if s["name"] == "nitpicker")
    assert nit["description"]
    assert "review" in nit["commands"]


def test_list_skills_lists_nitpicker_once():
    names = [s["name"] for s in sc.list_skills()]
    assert names.count("nitpicker") == 1


def test_list_skills_excludes_the_internal_dot_claude_tier():
    # `.claude/skills/` is the internal dev tier here and the user's own private
    # skill directory on a consumer machine — never part of what this tool reads.
    assert all(s["path"].startswith("skills/") for s in sc.list_skills())


def test_read_skill_returns_frontmatter_text():
    text = sc.read_skill("nitpicker")
    assert "name: nitpicker" in text


def test_read_skill_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        sc.read_skill("does-not-exist")


def test_list_commands_parses_name_alias_purpose():
    cmds = sc.list_commands()
    by_name = {c["name"]: c for c in cmds}
    assert "review" in by_name
    assert "adversarial-reviewer" in by_name["review"]["aliases"]
    assert by_name["review"]["purpose"]


def test_read_command_known_and_traversal_rejected():
    import pytest

    assert "# /nitpicker review" in sc.read_command("review")
    with pytest.raises(KeyError):
        sc.read_command("../../../../etc/passwd")
    with pytest.raises(KeyError):
        sc.read_command("_conventions")  # underscore files are not public commands
