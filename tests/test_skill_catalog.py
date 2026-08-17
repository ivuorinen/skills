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


def test_list_skills_attaches_commands_only_to_nitpicker(tmp_path):
    """Every other skill must come back without a `commands` key — attaching it
    everywhere would advertise a command surface those skills do not have."""
    from pathlib import Path

    for name, desc in (("nitpicker", "Audits."), ("other-skill", "Does not dispatch.")):
        d = tmp_path / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {desc}\n---\n\nBody.\n", encoding="utf-8"
        )
    cmds = tmp_path / "skills" / "nitpicker" / "commands"
    cmds.mkdir()
    (cmds / "review.md").write_text("# /nitpicker review — R\n\nP.\n", encoding="utf-8")
    (tmp_path / "skills" / "nitpicker" / "SKILL.md").write_text(
        "---\nname: nitpicker\ndescription: Audits.\n---\n\n## Commands\n\n"
        "| Command | Purpose |\n| --- | --- |\n| `review` | Hostile review |\n",
        encoding="utf-8",
    )

    by_name = {s["name"]: s for s in sc.list_skills(root=Path(tmp_path))}
    assert "commands" in by_name["nitpicker"]
    assert "commands" not in by_name["other-skill"]


def test_read_skill_returns_frontmatter_text():
    text = sc.read_skill("nitpicker")
    assert "name: nitpicker" in text


def test_read_skill_unknown_raises():
    import pytest

    with pytest.raises(KeyError, match="does-not-exist"):
        sc.read_skill("does-not-exist")


def test_list_commands_parses_name_alias_purpose():
    cmds = sc.list_commands()
    by_name = {c["name"]: c for c in cmds}
    assert "review" in by_name
    assert "adversarial-reviewer" in by_name["review"]["aliases"]
    assert by_name["review"]["purpose"]


def test_list_commands_tags_each_row_with_its_heading():
    """The `###` group is the category; a table with no group falls back to its `##`.

    That fallback is what keeps the internal table distinguishable — `help` and
    `triage` both need "public commands only", and before the category existed the
    only way to get it was to hardcode the internal command's name.
    """
    by_name = {c["name"]: c["category"] for c in sc.list_commands()}
    assert by_name["review"] == "Review and fixing"
    assert by_name["plan"] == "Planning"
    assert by_name["x-findings-migrator"] == "Internal commands"


def test_list_commands_filters_by_category_in_any_spelling():
    prose = sc.list_commands(category="Security and data")
    assert [c["name"] for c in prose] == sc_security_names()
    assert sc.list_commands(category="security-and-data") == prose
    assert sc.list_commands(category="SECURITY AND DATA") == prose


def sc_security_names():
    """The Security-and-data rows, read straight from SKILL.md rather than pinned.

    Hardcoding the five names here would make this test fail on any future
    addition to that category — a maintenance tax that proves nothing about
    filtering.
    """
    body = (sc.plugin_root() / "skills" / "nitpicker" / "SKILL.md").read_text(encoding="utf-8")
    section = body.split("### Security and data")[1].split("###")[0]
    return [c["name"] for c in sc.list_commands() if f"`{c['name']}`" in section]


def test_list_commands_rejects_an_unknown_category():
    """An empty list would read as "that category is empty", hiding the typo."""
    import pytest

    with pytest.raises(ValueError, match="unknown category 'planing'"):
        sc.list_commands(category="planing")
    with pytest.raises(ValueError, match="Review and fixing"):
        sc.list_commands(category="planing")


def test_read_command_known_and_traversal_rejected(monkeypatch):
    """The rejection must happen *before* any read.

    A bare `pytest.raises(KeyError)` cannot tell an allowlist rejection from an
    ordinary unknown-name lookup, and would still pass if the implementation
    became read-then-validate — by which point the traversal has already read the
    file. Failing the test on any read of the rejected path pins the ordering.
    """
    import re
    from pathlib import Path

    import pytest

    assert "# /nitpicker review" in sc.read_command("review")

    real_read_text = Path.read_text
    reads: list[str] = []

    def _recording_read_text(self, *a, **k):
        reads.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _recording_read_text)

    for rejected in ("../../../../etc/passwd", "_conventions"):
        reads.clear()
        with pytest.raises(KeyError, match=re.escape(rejected)):
            sc.read_command(rejected)
        assert not any("passwd" in r or r.endswith("_conventions.md") for r in reads), (
            f"read_command({rejected!r}) touched the file before rejecting it"
        )


def test_read_reference_serves_the_shared_files_in_both_spellings():
    """`read_command` refuses these names, so the router needs its own reader.

    The underscore is optional because prose cites the file (`_conventions.md`)
    and a reader cites the section (`conventions`); a tool that accepted only one
    spelling would fail half the calls it exists to serve.
    """
    underscored = sc.read_reference("_conventions")
    assert "# Shared Conventions" in underscored
    assert sc.read_reference("conventions") == underscored
    assert "## How audit uses this file" in sc.read_reference("audit-coverage")


def test_read_reference_rejects_non_reference_names_before_reading(monkeypatch):
    """Public commands and traversal both miss the enumerated set — no path is built.

    Same ordering guarantee `read_command` carries: rejection precedes any read,
    so a future read-then-validate rewrite fails here instead of shipping.
    """
    import re
    from pathlib import Path

    import pytest

    real_read_text = Path.read_text
    reads: list[str] = []

    def _recording_read_text(self, *a, **k):
        reads.append(str(self))
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _recording_read_text)

    for rejected in ("review", "../../../../etc/passwd"):
        reads.clear()
        with pytest.raises(KeyError, match=re.escape(rejected)):
            sc.read_reference(rejected)
        assert not reads, f"read_reference({rejected!r}) read a file before rejecting it"
