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
VALID_SCOPED = "---\npaths:\n  - \"src/**/*.ts\"\n---\n\nAlways add explicit return types.\n"


class TestValidate:
    def test_valid_plain_file_no_errors(self, tmp_path):
        assert _errors(tmp_path, VALID_PLAIN) == []

    def test_valid_path_scoped_file_no_errors(self, tmp_path):
        # uses tmp_path as repo_root; glob won't match but no ERROR for non-empty valid glob
        assert _errors(tmp_path, VALID_SCOPED) == []

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
        content = "---\npaths:\n  - \"\"\n---\n\nBody.\n"
        assert _has(_errors(tmp_path, content), "empty glob string")

    def test_absolute_glob_errors(self, tmp_path):
        content = "---\npaths:\n  - \"/src/**/*.ts\"\n---\n\nBody.\n"
        assert _has(_errors(tmp_path, content), "must be relative")

    def test_invalid_glob_no_match_warns(self, tmp_path):
        # Python's Path.glob() is lenient — [unclosed matches nothing → stale WARN
        content = "---\npaths:\n  - \"[unclosed\"\n---\n\nBody.\n"
        errors, warnings = _run(tmp_path, content)
        assert errors == []
        assert _has(warnings, "stale")

    def test_stale_glob_warns(self, tmp_path):
        # glob matches nothing in tmp_path (no .ts files there)
        errors, warnings = _run(tmp_path, VALID_SCOPED)
        assert errors == []
        assert _has(warnings, "stale")

    def test_body_empty_after_frontmatter_warns(self, tmp_path):
        content = "---\npaths:\n  - \"src/**/*.ts\"\n---\n\n"
        errors, warnings = _run(tmp_path, content)
        assert errors == []
        assert _has(warnings, "empty")

    def test_unclosed_frontmatter_errors(self, tmp_path):
        content = "---\npaths:\n  - \"src/**/*.ts\"\n"
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
        content = "---\npaths:\n  - \"src/**/*.ts\"\n---\n\nAlways add explicit return types.\n"
        errors, warnings = _run(tmp_path, content)
        assert errors == []
        assert not _has(warnings, "stale")
