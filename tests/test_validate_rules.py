"""Tests for scripts/validate-rules.py — validate()."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "validate_rules",
    Path(__file__).parent.parent / "scripts" / "validate-rules.py",
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
validate = _mod.validate
_discover_targets = _mod._discover_targets


def _run(tmp_path: Path, content: str, filename: str = "my-rule.md") -> tuple[list[str], list[str]]:
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    errors: list[str] = []
    warnings: list[str] = []
    validate(path, errors, warnings, tmp_path)
    return errors, warnings


def _errors(tmp_path: Path, content: str, filename: str = "my-rule.md") -> list[str]:
    e, _ = _run(tmp_path, content, filename)
    return e


def _has(items: list[str], fragment: str) -> bool:
    return any(fragment in item for item in items)


VALID_PLAIN = "# No Commits\n\nNever run `git commit` without explicit user instruction.\n"
VALID_SCOPED = '---\npaths:\n  - "src/**/*.ts"\n---\n\nAlways add explicit return types.\n'


class TestValidate:
    def test_valid_plain_file_no_errors(self, tmp_path):
        assert _errors(tmp_path, VALID_PLAIN) == []

    def test_valid_path_scoped_file_no_errors(self, tmp_path):
        # uses tmp_path as repo_root; glob won't match but no ERROR for non-empty valid glob
        assert _errors(tmp_path, VALID_SCOPED) == []

    def test_flow_style_paths_list_accepted(self, tmp_path):
        # A YAML flow-style list must parse as a list, not a scalar — kept in sync
        # with check-rules-anatomy.py. Regression for the two-validator divergence.
        content = (
            '---\npaths: ["src/**/*.ts", "lib/**"]\n---\n\nAlways add explicit return types.\n'
        )
        assert not _has(_errors(tmp_path, content), "must be a list")

    def test_non_kebab_filename_errors(self, tmp_path):
        assert _has(_errors(tmp_path, VALID_PLAIN, "SEARCH_TOOLS.md"), "kebab-case")

    def test_non_md_extension_errors(self, tmp_path):
        path = tmp_path / "my-rule.txt"
        path.write_text(VALID_PLAIN, encoding="utf-8")
        errors: list[str] = []
        warnings: list[str] = []
        validate(path, errors, warnings, tmp_path)
        assert _has(errors, ".md extension")

    def test_empty_file_errors(self, tmp_path):
        assert _has(_errors(tmp_path, ""), "empty")

    def test_paths_scalar_not_list_errors(self, tmp_path):
        content = "---\npaths: src/**/*.ts\n---\n\nBody.\n"
        assert _has(_errors(tmp_path, content), "must be a list")

    def test_empty_glob_string_errors(self, tmp_path):
        content = '---\npaths:\n  - ""\n---\n\nBody.\n'
        assert _has(_errors(tmp_path, content), "empty glob string")

    def test_absolute_glob_errors(self, tmp_path):
        content = '---\npaths:\n  - "/src/**/*.ts"\n---\n\nBody.\n'
        assert _has(_errors(tmp_path, content), "must be relative")

    def test_invalid_glob_no_match_warns(self, tmp_path):
        # Python's Path.glob() is lenient — [unclosed matches nothing → stale WARN
        content = '---\npaths:\n  - "[unclosed"\n---\n\nBody.\n'
        errors, warnings = _run(tmp_path, content)
        assert errors == []
        assert _has(warnings, "stale")

    def test_stale_glob_warns(self, tmp_path):
        # glob matches nothing in tmp_path (no .ts files there)
        errors, warnings = _run(tmp_path, VALID_SCOPED)
        assert errors == []
        assert _has(warnings, "stale")

    def test_body_empty_after_frontmatter_warns(self, tmp_path):
        content = '---\npaths:\n  - "src/**/*.ts"\n---\n\n'
        errors, warnings = _run(tmp_path, content)
        assert errors == []
        assert _has(warnings, "empty")

    def test_unclosed_frontmatter_errors(self, tmp_path):
        content = '---\npaths:\n  - "src/**/*.ts"\n'
        assert _has(_errors(tmp_path, content), "never closed")

    def test_dangling_symlink_errors(self, tmp_path):
        link = tmp_path / "dangling-link.md"
        link.symlink_to(tmp_path / "nonexistent-target.md")
        errors: list[str] = []
        warnings: list[str] = []
        validate(link, errors, warnings, tmp_path)
        assert _has(errors, "dangling symlink")

    def test_empty_rules_dir_returns_no_targets(self, tmp_path):
        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        assert _discover_targets(tmp_path) == []

    def test_dangling_symlink_found_in_discovery(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        link = rules_dir / "dangling.md"
        link.symlink_to(rules_dir / "nonexistent.md")
        targets = _discover_targets(tmp_path)
        assert link in targets

    def test_valid_scoped_with_matching_file_no_warn(self, tmp_path):
        # Create a matching .ts file so the glob is not stale
        ts_dir = tmp_path / "src"
        ts_dir.mkdir()
        (ts_dir / "app.ts").write_text("export const x = 1;", encoding="utf-8")
        content = '---\npaths:\n  - "src/**/*.ts"\n---\n\nAlways add explicit return types.\n'
        errors, warnings = _run(tmp_path, content)
        assert errors == []
        assert not _has(warnings, "stale")


# --- Regression test for audit fix (2026-07-09) ---


def test_paths_list_parsed_at_four_space_indent():
    text = '---\ndescription: d\npaths:\n    - "src/**"\n    - "lib/**"\n---\nbody\n'
    fm, _ = _mod.parse_rules_frontmatter(text)
    assert fm is not None and fm.get("paths") == ["src/**", "lib/**"]


def test_paths_list_parsed_at_column_zero():
    # A block sequence at column 0 is valid YAML and must still be recognized,
    # so its globs are validated rather than silently skipped.
    text = '---\npaths:\n- "src/**"\n- "lib/**"\n---\nbody\n'
    fm, _ = _mod.parse_rules_frontmatter(text)
    assert fm is not None and fm.get("paths") == ["src/**", "lib/**"]


def test_column_zero_absolute_glob_is_rejected(tmp_path):
    # The bug let a column-0 list bypass the absolute-path check entirely.
    text = '---\npaths:\n- "/etc/passwd"\n---\nbody\n'
    errors = _errors(tmp_path, text)
    assert _has(errors, "must be relative, not absolute")


def test_invalid_double_star_glob_reported_not_crashed(tmp_path):
    # '**' adjacent to other chars in a path component raises ValueError from
    # Path.glob on CPython <3.13; the validator must report it, never traceback.
    content = '---\npaths:\n  - "src/**foo/*.ts"\n---\n\nBody.\n'
    errors, warnings = _run(tmp_path, content)  # must not raise ValueError
    assert _has(errors, "not a valid pattern") or _has(warnings, "stale")


def test_blank_line_inside_paths_list_keeps_all_items():
    text = '---\npaths:\n  - "stale/removed/*"\n\n  - "src/*"\n---\nbody\n'
    fm, _ = _mod.parse_rules_frontmatter(text)
    assert fm is not None and fm.get("paths") == ["stale/removed/*", "src/*"]


# ── check_repo_rules: enforcement for two previously unenforced rules ─────────


def _repo_errors(tmp_path: Path) -> list[str]:
    errors: list[str] = []
    _mod.check_repo_rules(tmp_path, errors)
    return errors


def _skill_md(tmp_path: Path, body: str) -> None:
    d = tmp_path / "skills" / "demo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")


def _script(tmp_path: Path, name: str, body: str) -> None:
    d = tmp_path / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_date_literal_in_shipped_skill_is_rejected(tmp_path):
    _skill_md(tmp_path, "# Skill\n\nAs of 2026-07-19 this holds.\n")
    assert _has(_repo_errors(tmp_path), "time-sensitive content")


def test_skill_without_a_date_is_accepted(tmp_path):
    # Version-like literals (WCAG criteria, IP masks, spec versions) stay legal —
    # only the date half is enforced.
    _skill_md(tmp_path, "# Skill\n\nWCAG 1.4.3 contrast, and `0.0.0.0/0` ingress.\n")
    assert _repo_errors(tmp_path) == []


def test_internal_script_without_uv_shebang_is_rejected(tmp_path):
    _script(tmp_path, "thing.py", "#!/usr/bin/env python3\nprint(1)\n")
    assert _has(_repo_errors(tmp_path), "must be first line") or _has(
        _repo_errors(tmp_path), "uv run --quiet"
    )


def test_internal_script_with_uv_shebang_is_accepted(tmp_path):
    _script(tmp_path, "thing.py", "#!/usr/bin/env -S uv run --quiet\nprint(1)\n")
    assert _repo_errors(tmp_path) == []


def test_import_only_modules_are_exempt_from_the_shebang_rule(tmp_path):
    # common.py and _hooklib.py are imported, never executed — a shebang there
    # would claim a runner they do not have.
    _script(tmp_path, "common.py", '"""Shared utilities."""\n')
    (tmp_path / "scripts" / "hooks").mkdir(parents=True)
    (tmp_path / "scripts" / "hooks" / "_hooklib.py").write_text('"""Shared."""\n', encoding="utf-8")
    assert _repo_errors(tmp_path) == []
