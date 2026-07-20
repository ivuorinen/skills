"""Tests for scripts/list-skills.py — collect_commands() and print_section()."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "list_skills",
    Path(__file__).parent.parent / "scripts" / "list-skills.py",
)
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
