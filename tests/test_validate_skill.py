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


VALID = "---\nname: my-skill\ndescription: Use when testing this skill\n---\n\n## Overview\n\nBody.\n"


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

    def test_description_must_start_with_use_when(self, tmp_path):
        text = "---\nname: my-skill\ndescription: This skill does things\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "start with 'Use when'")

    def test_description_too_long(self, tmp_path):
        long_desc = "Use when " + "x" * 492
        text = f"---\nname: my-skill\ndescription: {long_desc}\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "must be ≤500")

    def test_description_unquoted_colon_space_errors(self, tmp_path):
        text = "---\nname: my-skill\ndescription: Use when the task requires: deep inspection\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "contains ': '")

    def test_description_single_quoted_colon_space_ok(self, tmp_path):
        text = "---\nname: my-skill\ndescription: 'Use when the task requires: deep inspection'\n---\nbody\n"
        assert not _has(_errors(tmp_path, text), "contains ': '")

    def test_description_double_quoted_colon_space_ok(self, tmp_path):
        text = '---\nname: my-skill\ndescription: "Use when the task requires: deep inspection"\n---\nbody\n'
        assert not _has(_errors(tmp_path, text), "contains ': '")

    def test_name_mismatch_errors(self, tmp_path):
        text = "---\nname: wrong-name\ndescription: Use when testing\n---\nbody\n"
        assert _has(_errors(tmp_path, text), "does not match directory")

    def test_header_level_jump_errors(self, tmp_path):
        text = VALID + "\n#### [N-001] Jump skipping h3\n"
        assert _has(_errors(tmp_path, text), "header level jumps")

    def test_header_inside_fenced_code_block_ignored(self, tmp_path):
        text = VALID + "\n```\n#### Not a real header\n```\n"
        assert not _has(_errors(tmp_path, text), "header level jumps")

    def test_legacy_path_in_prose_warns(self, tmp_path):
        text = VALID + "\nWrite results to codereview.md.\n"
        assert _has(_warnings(tmp_path, text), "legacy output path")

    def test_legacy_path_in_fenced_block_no_warning(self, tmp_path):
        text = VALID + "\n```\nWrite to codereview.md\n```\n"
        assert not _has(_warnings(tmp_path, text), "legacy output path")
