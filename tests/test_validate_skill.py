"""Tests for scripts/validate-skill.py — validate()."""

import importlib.util
import runpy
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "validate-skill.py"
_spec = importlib.util.spec_from_file_location("validate_skill", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
validate = _mod.validate


def _run(tmp_path: Path, content: str, skill_name: str = "my-skill") -> tuple[list[str], list[str]]:
    skill_dir = tmp_path / skill_name
    skill_dir.mkdir(exist_ok=True)
    path = skill_dir / "SKILL.md"
    path.write_text(content, encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []
    validate(path, errors, warnings)
    return errors, warnings


def _errors(tmp_path: Path, content: str, skill_name: str = "my-skill") -> list[str]:
    e, _ = _run(tmp_path, content, skill_name)
    return e


def _warnings(tmp_path: Path, content: str, skill_name: str = "my-skill") -> list[str]:
    _, w = _run(tmp_path, content, skill_name)
    return w


def _has(items: list[str], fragment: str) -> bool:
    return any(fragment in item for item in items)


VALID = (
    "---\nname: my-skill\n"
    "description: Performs a test action. Use when testing this skill.\n"
    "---\n\n## Overview\n\nBody.\n"
)


def test_unterminated_fence_in_skill_body_flagged(tmp_path):
    content = VALID + "\n```python\nunclosed fence\n"
    assert _has(_errors(tmp_path, content), "unterminated code fence")


def test_four_backtick_fence_not_closed_by_three(tmp_path):
    # A four-backtick opener must not be closed by a three-backtick line.
    content = VALID + "\n````\n```\n"
    assert _has(_errors(tmp_path, content), "unterminated code fence")


def test_duplicate_table_commands_detected():
    body = "| `foo` | a |\n| `foo` | dup |\n| `bar` | b |\n"
    assert _mod._duplicate_table_commands(body) == ["foo"]


class TestVendoredSkip:
    def test_vendored_skill_is_filtered_out(self):
        targets = [
            Path(".claude/skills/graphify/SKILL.md"),
            Path("skills/nitpicker/SKILL.md"),
        ]
        kept, skipped = _mod.filter_vendored(targets)
        assert Path("skills/nitpicker/SKILL.md") in kept
        assert Path(".claude/skills/graphify/SKILL.md") not in kept
        assert "graphify" in skipped

    def test_authored_skills_all_kept(self):
        targets = [
            Path(f".claude/skills/{n}/SKILL.md")
            for n in ("new-command", "release-prep", "skill-tester", "skills", "validate-skills")
        ]
        kept, skipped = _mod.filter_vendored(targets)
        assert kept == targets
        assert skipped == []

    def test_allowlist_contains_only_approved_entries(self):
        # Governance guard: the vendored allowlist is human-curated. graphify is
        # the only user-approved entry. If this fails because an entry was added,
        # the addition needs explicit user approval — do not "fix" it by editing
        # this assertion.
        assert frozenset({"graphify"}) == _mod.VENDORED_SKILLS

    def test_vendored_skills_carry_a_license(self):
        # Vendored content is redistributed under its upstream license, not
        # ours. No LICENSE in the skill dir means the allowlist grew without
        # provenance — see .claude/rules/vendored-skills.md.
        repo_root = Path(__file__).parent.parent
        for name in _mod.VENDORED_SKILLS:
            assert (repo_root / ".claude" / "skills" / name / "LICENSE").is_file(), (
                f"vendored skill {name!r} has no LICENSE"
            )


class TestValidate:
    def test_valid_skill_no_errors(self, tmp_path):
        assert _errors(tmp_path, VALID) == []

    def test_no_frontmatter(self, tmp_path):
        assert _has(_errors(tmp_path, "# No frontmatter\n"), "missing YAML frontmatter")

    def test_missing_name(self, tmp_path):
        text = "---\ndescription: Use when testing\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "missing 'name'")

    def test_missing_description(self, tmp_path):
        text = "---\nname: my-skill\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "missing 'description'")

    def test_description_must_contain_use_when(self, tmp_path):
        text = "---\nname: my-skill\ndescription: This skill does things\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "'Use when'")

    def test_description_capability_prefix_with_use_when_passes(self, tmp_path):
        text = (
            "---\nname: my-skill\n"
            "description: Analyzes code and finds bugs. Use when reviewing a PR.\n"
            "---\nbody\n"
        )
        assert _errors(tmp_path, text) == []

    def test_description_too_long(self, tmp_path):
        long_desc = "Use when " + "x" * 1016
        text = f"---\nname: my-skill\ndescription: {long_desc}\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "must be ≤1024")

    def test_description_unquoted_colon_space_errors(self, tmp_path):
        text = (
            "---\nname: my-skill\n"
            "description: Use when the task requires: deep inspection\n---\nbody\n"
        )
        assert _has(_errors(tmp_path, text), "contains ': '")

    def test_description_single_quoted_colon_space_ok(self, tmp_path):
        text = (
            "---\nname: my-skill\n"
            "description: 'Use when the task requires: deep inspection'\n---\nbody\n"
        )
        assert not _has(_errors(tmp_path, text), "contains ': '")

    def test_description_double_quoted_colon_space_errors(self, tmp_path):
        # Convention is single quotes; double-quoted values must also be flagged
        text = (
            "---\nname: my-skill\n"
            'description: "Use when the task requires: deep inspection"\n---\nbody\n'
        )
        assert _has(_errors(tmp_path, text), "contains ': '")

    def test_name_mismatch_errors(self, tmp_path):
        text = "---\nname: wrong-name\ndescription: Use when testing\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "does not match directory")

    def test_name_over_64_chars_errors(self, tmp_path):
        long_name = "a" * 65
        text = f"---\nname: {long_name}\ndescription: Use when testing\n---\nbody\n"
        assert _has(_errors(tmp_path, text, long_name), "must be ≤64")

    def test_name_with_invalid_characters_errors(self, tmp_path):
        text = "---\nname: My_Skill\ndescription: Use when testing\n---\nbody\n"
        assert _has(_errors(tmp_path, text, "My_Skill"), "lowercase letters, digits and hyphens")

    def test_name_with_reserved_word_errors(self, tmp_path):
        text = "---\nname: claude-helper\ndescription: Use when testing\n---\nbody\n"
        assert _has(_errors(tmp_path, text, "claude-helper"), "reserved word 'claude'")

    def test_header_level_jump_errors(self, tmp_path):
        text = VALID + "\n#### [N-001] Jump skipping h3\n"
        assert _has(_errors(tmp_path, text), "header level jumps")

    def test_header_inside_fenced_code_block_ignored(self, tmp_path):
        text = VALID + "\n```\n#### Not a real header\n```\n"
        assert not _has(_errors(tmp_path, text), "header level jumps")

    def test_duplicate_header_errors(self, tmp_path):
        text = VALID + "\n## Overview\n\nA second Overview section.\n"
        assert _has(_errors(tmp_path, text), "duplicate header")

    def test_duplicate_header_in_fenced_block_ignored(self, tmp_path):
        text = VALID + "\n```\n## Overview\n```\n"
        assert not _has(_errors(tmp_path, text), "duplicate header")

    def test_same_title_different_level_not_duplicate(self, tmp_path):
        text = VALID + "\n### Overview\n\nA subsection, not a duplicate section.\n"
        assert not _has(_errors(tmp_path, text), "duplicate header")

    def test_legacy_path_in_prose_warns(self, tmp_path):
        text = VALID + "\nWrite results to codereview.md.\n"
        assert _has(_warnings(tmp_path, text), "legacy output path")

    def test_legacy_path_in_fenced_block_no_warning(self, tmp_path):
        text = VALID + "\n```\nWrite to codereview.md\n```\n"
        assert not _has(_warnings(tmp_path, text), "legacy output path")

    def test_body_too_long_warns(self, tmp_path):
        long_body = "\n".join(["Line." for _ in range(502)])
        text = (
            "---\nname: my-skill\n"
            "description: Does something. Use when needed.\n---\n\n"
            f"{long_body}\n"
        )
        assert _has(_warnings(tmp_path, text), "500")

    def test_crlf_frontmatter_valid(self, tmp_path):
        assert _errors(tmp_path, VALID.replace("\n", "\r\n")) == []


class TestTargetDiscovery:
    def test_no_args_includes_dot_claude_skills(self, tmp_path, monkeypatch, capsys):
        for base, skill in (("skills", "pub"), (".claude/skills", "internal")):
            d = tmp_path / base / skill
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(VALID.replace("my-skill", skill), encoding="utf-8")
        # main() derives repo_root from the module's __file__ as scripts/validate-skill.py.
        monkeypatch.setattr(_mod, "__file__", str(tmp_path / "scripts" / "validate-skill.py"))
        monkeypatch.setattr(_mod.sys, "argv", ["validate-skill.py"])
        _mod.main()
        assert "2 skill(s) validated" in capsys.readouterr().out


# ── command-file validation (skills with a commands/ directory) ─────────────

COMMANDS_SKILL = (
    "---\nname: my-skill\n"
    "description: Dispatches commands. Use when testing command dispatch.\n"
    "---\n\n## Commands\n\n"
    "| Command | Aliases | Purpose |\n"
    "|---------|---------|---------|\n"
    "| `alpha` | `old-alpha` | First |\n"
    "| `beta` | — | Second |\n"
)

GOOD_COMMAND = "# /my-skill {name} — Title\n\nPurpose line.\n\n## When to use\n\nTriggers.\n"


def _run_commands(tmp_path: Path, files: dict[str, str]) -> list[str]:
    skill_dir = tmp_path / "my-skill"
    cmd_dir = skill_dir / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(COMMANDS_SKILL, encoding="utf-8")
    for fname, content in files.items():
        (cmd_dir / fname).write_text(content, encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []
    validate(skill_dir / "SKILL.md", errors, warnings)
    return errors


def _cmd(name: str) -> str:
    return GOOD_COMMAND.format(name=name)


class TestCommandValidation:
    def test_happy_path(self, tmp_path):
        errors = _run_commands(tmp_path, {"alpha.md": _cmd("alpha"), "beta.md": _cmd("beta")})
        assert errors == []

    def test_underscore_files_ignored(self, tmp_path):
        errors = _run_commands(
            tmp_path,
            {"alpha.md": _cmd("alpha"), "beta.md": _cmd("beta"), "_conventions.md": "# Shared\n"},
        )
        assert errors == []

    def test_table_row_without_file(self, tmp_path):
        errors = _run_commands(tmp_path, {"alpha.md": _cmd("alpha")})
        assert _has(errors, "beta")
        assert _has(errors, "no commands/beta.md")

    def test_file_without_table_row(self, tmp_path):
        errors = _run_commands(
            tmp_path,
            {"alpha.md": _cmd("alpha"), "beta.md": _cmd("beta"), "gamma.md": _cmd("gamma")},
        )
        assert _has(errors, "gamma")
        assert _has(errors, "not in the Commands table")

    def test_wrong_h1(self, tmp_path):
        bad = "# /my-skill wrong — Title\n\nPurpose.\n\n## When to use\n\nT.\n"
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "h1 must be '# /my-skill alpha — <Title>'")

    def test_h1_without_title_rejected(self, tmp_path):
        bad = "# /my-skill alpha\n\nPurpose.\n\n## When to use\n\nT.\n"
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "h1 must be '# /my-skill alpha — <Title>'")

    def test_command_frontmatter_rejected(self, tmp_path):
        bad = "---\ndescription: sneaky\n---\n" + _cmd("alpha")
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "must not have YAML frontmatter")

    def test_when_to_use_inside_fence_rejected(self, tmp_path):
        bad = "# /my-skill alpha — Title\n\nPurpose.\n\n```\n## When to use\n```\n\nT.\n"
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "missing '## When to use'")

    def test_headerless_command_file(self, tmp_path):
        errors = _run_commands(tmp_path, {"alpha.md": "just prose\n", "beta.md": _cmd("beta")})
        assert _has(errors, "h1 must be '# /my-skill alpha — <Title>'")
        assert _has(errors, "missing '## When to use'")

    def test_missing_when_to_use(self, tmp_path):
        bad = "# /my-skill alpha — Title\n\nPurpose.\n\n## Something else\n\nT.\n"
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "missing '## When to use'")

    def test_header_jump_in_command(self, tmp_path):
        bad = "# /my-skill alpha — Title\n\nPurpose.\n\n## When to use\n\nT.\n\n#### Deep\n\nX.\n"
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "header level jumps")

    def test_unterminated_fence_in_command(self, tmp_path):
        bad = _cmd("alpha") + "\n```python\nnever closed\n"
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "unterminated code fence")

    def test_second_h1_in_command(self, tmp_path):
        bad = _cmd("alpha") + "\n# A second title\n\nX.\n"
        errors = _run_commands(tmp_path, {"alpha.md": bad, "beta.md": _cmd("beta")})
        assert _has(errors, "command file has 2 h1 headers")

    def test_unreadable_command_file(self, tmp_path):
        # A directory named alpha.md: read_text raises IsADirectoryError (an OSError).
        skill_dir = tmp_path / "my-skill"
        (skill_dir / "commands" / "alpha.md").mkdir(parents=True)
        errors = _run_commands(tmp_path, {"beta.md": _cmd("beta")})
        assert _has(errors, "cannot read file")

    def test_duplicate_table_row(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        (skill_dir / "commands").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            COMMANDS_SKILL + "| `alpha` | — | Listed twice |\n", encoding="utf-8"
        )
        for name in ("alpha", "beta"):
            (skill_dir / "commands" / f"{name}.md").write_text(_cmd(name), encoding="utf-8")
        errors: list[str] = []
        validate(skill_dir / "SKILL.md", errors, [])
        assert _has(errors, "appears in more than one Commands-table row")

    def test_commands_table_without_a_commands_directory(self, tmp_path):
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(COMMANDS_SKILL, encoding="utf-8")
        errors: list[str] = []
        validate(skill_dir / "SKILL.md", errors, [])
        assert _has(errors, "commands/ does not exist")


def test_unreadable_skill_file(tmp_path):
    # A directory named SKILL.md: read_text raises IsADirectoryError (an OSError).
    path = tmp_path / "my-skill" / "SKILL.md"
    path.mkdir(parents=True)
    errors: list[str] = []
    validate(path, errors, [])
    assert _has(errors, "cannot read file")


# ── main(): the exit-code contract CI and pre-commit observe (tests-781e4953) ──


def _main_on(monkeypatch, tmp_path, argv: list[str]):
    monkeypatch.setattr(_mod.sys, "argv", ["validate-skill.py", *argv])
    monkeypatch.setattr(_mod, "__file__", str(tmp_path / "scripts" / "validate-skill.py"))
    return _mod.main()


def test_main_exits_zero_and_prints_ok_for_a_valid_skill(tmp_path, monkeypatch, capsys):
    path = tmp_path / "my-skill" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(VALID, encoding="utf-8")
    assert _main_on(monkeypatch, tmp_path, [str(path)]) is None
    assert "OK  1 skill(s) validated." in capsys.readouterr().out


def test_main_exits_one_and_prints_every_error(tmp_path, monkeypatch, capsys):
    """The non-zero exit is the only signal pre-commit and CI act on."""
    path = tmp_path / "my-skill" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("no frontmatter at all\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _main_on(monkeypatch, tmp_path, [str(path)])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "error(s). Fix before committing." in out


def test_main_prints_warnings_without_failing(tmp_path, monkeypatch, capsys):
    path = tmp_path / "my-skill" / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(VALID + "\nWrite results to codereview.md.\n", encoding="utf-8")
    assert _main_on(monkeypatch, tmp_path, [str(path)]) is None
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "OK  1 skill(s) validated." in out


def test_main_skips_vendored_skills_and_exits_zero(tmp_path, monkeypatch, capsys):
    vendored = next(iter(_mod.VENDORED_SKILLS))
    path = tmp_path / vendored / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("whatever, never validated\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _main_on(monkeypatch, tmp_path, [str(path)])
    assert exc.value.code == 0
    assert f"SKIP   {vendored}" in capsys.readouterr().out


def test_main_reports_an_empty_tree_rather_than_passing_silently(tmp_path, monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        _main_on(monkeypatch, tmp_path, [])
    assert exc.value.code == 0
    assert "No SKILL.md files found." in capsys.readouterr().out


def test_module_runs_as_a_script(tmp_path, monkeypatch, capsys):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    monkeypatch.setattr(sys, "argv", ["validate-skill.py", str(tmp_path / "nothing")])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 1
    assert "cannot read file" in capsys.readouterr().out
