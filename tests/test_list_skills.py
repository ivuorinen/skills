"""Tests for scripts/list-skills.py — collect_commands() and print_section()."""

import importlib.util
import runpy
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "list-skills.py"
_spec = importlib.util.spec_from_file_location("list_skills", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
collect_commands = _mod.collect_commands
print_section = _mod.print_section


def _command(skill_dir: Path, name: str, body: str) -> None:
    commands = skill_dir / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    (commands / name).write_text(body, encoding="utf-8")


class TestCollectCommands:
    def test_returns_first_non_heading_line_as_purpose(self, tmp_path):
        _command(tmp_path, "security.md", "# /nitpicker security — Audit\n\nFinds vulns.\nMore.\n")
        assert collect_commands(tmp_path) == [("security", "Finds vulns.")]

    def test_underscore_prefixed_files_skipped(self, tmp_path):
        _command(tmp_path, "_conventions.md", "# Conventions\n\nShared rules.\n")
        _command(tmp_path, "tests.md", "# /nitpicker tests — Audit\n\nAudits tests.\n")
        assert [name for name, _ in collect_commands(tmp_path)] == ["tests"]

    def test_headings_and_blanks_only_yields_placeholder(self, tmp_path):
        _command(tmp_path, "empty.md", "# /nitpicker empty — Nothing\n\n## When to use\n\n")
        assert collect_commands(tmp_path) == [("empty", "(no purpose line)")]


class TestPrintSection:
    def test_empty_description_does_not_raise(self, capsys):
        # textwrap.wrap("") returns [], which used to raise IndexError on lines[0].
        print_section("Public", [("my-skill", "")])
        assert "my-skill" in capsys.readouterr().out

    def test_no_skills_prints_none(self, capsys):
        print_section("Public", [])
        assert "(none)" in capsys.readouterr().out

    def test_long_description_wraps_onto_indented_continuation_lines(self, capsys):
        print_section("Public", [("my-skill", "word " * 60)])
        lines = capsys.readouterr().out.splitlines()
        body = [ln for ln in lines if "word" in ln]
        assert len(body) > 1
        assert body[1].startswith(" " * (2 + len("my-skill") + 2))


# ── main(): the `make list` inventory (tests-f3ebae78) ────────────────────────


def _skill(root: Path, tree: str, name: str, description: str) -> Path:
    d = root / tree / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nBody.\n", encoding="utf-8"
    )
    return d


def test_main_lists_public_private_and_command_sections(tmp_path, monkeypatch, capsys):
    public = _skill(tmp_path, "skills", "nitpicker", "Audits things.")
    _skill(tmp_path, ".claude/skills", "internal-tool", "Dev only.")
    _command(public, "tests.md", "# /nitpicker tests — Audit\n\nAudits tests.\n")
    monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path)

    assert _mod.main() == 0
    out = capsys.readouterr().out
    assert "Public  (skills/)" in out
    assert "Commands (/nitpicker <command>)" in out
    assert "Private (.claude/skills/)" in out
    assert "Audits things." in out
    assert "Dev only." in out


def test_module_runs_as_a_script(tmp_path, monkeypatch, capsys):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0
    assert "Public  (skills/)" in capsys.readouterr().out
