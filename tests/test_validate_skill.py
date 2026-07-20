"""Tests for scripts/validate-skill.py — validate()."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "validate_skill",
    Path(__file__).parent.parent / "scripts" / "validate-skill.py",
)
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
