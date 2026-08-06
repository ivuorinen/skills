"""Tests for scripts/validate-rules.py — validate()."""

import importlib.util
import runpy
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "validate-rules.py"
_spec = importlib.util.spec_from_file_location("validate_rules", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
validate = _mod.validate
_discover_targets = _mod._discover_targets


def _index_repo(tmp_path, claude_md: str, rule_names: list[str]) -> Path:
    """A minimal repo root: CLAUDE.md plus .claude/rules/<name> for each rule."""
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    for name in rule_names:
        (rules / name).write_text("body\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    return tmp_path


def test_rules_index_anchors_on_the_real_level_two_heading(tmp_path):
    """A `### Conventions` in another section, or the heading named in prose, must
    not become the anchor — the check would then read the wrong block and miss
    real drift in the actual section."""
    claude = (
        "# T\n\n"
        "## Setup\n\n"
        "Everything below the `## Conventions` heading indexes the rules.\n\n"
        "### Conventions\n\n"
        "- `decoy.md`\n\n"
        "## Conventions\n\n"
        "- `real.md`\n\n"
        "## After\n\n"
        "- `unrelated.md`\n"
    )
    root = _index_repo(tmp_path, claude, ["real.md"])
    errors: list[str] = []
    _mod.check_rules_index(root, errors)
    assert errors == [], errors  # decoy.md/unrelated.md are outside the real section


def test_rules_index_captures_non_kebab_filenames(tmp_path):
    """_iter_rules yields every .md, so the list parser must be able to read every
    .md — a narrower grammar reports a listed rule as missing."""
    root = _index_repo(
        tmp_path,
        "## Conventions\n\n- `README.md`\n- `_security.md`\n- `rule_v2.md`\n",
        ["README.md", "_security.md", "rule_v2.md"],
    )
    errors: list[str] = []
    _mod.check_rules_index(root, errors)
    assert errors == [], errors


def test_rules_index_reports_drift_in_both_directions(tmp_path):
    root = _index_repo(
        tmp_path, "## Conventions\n\n- `listed.md`\n- `ghost.md`\n", ["listed.md", "orphan.md"]
    )
    errors: list[str] = []
    _mod.check_rules_index(root, errors)
    joined = "\n".join(errors)
    assert "orphan.md is not listed" in joined
    assert "lists ghost.md" in joined


def test_rules_index_fails_loudly_when_discovery_is_incomplete(tmp_path, monkeypatch):
    """An unreadable subtree makes on_disk partial, which would hide an unindexed
    rule and let the check pass. Report and stop instead."""
    root = _index_repo(tmp_path, "## Conventions\n\n- `a.md`\n", ["a.md"])

    def _partial(rules_dir, seen=None, errors=None):
        if errors is not None:
            errors.append(rules_dir / "unreadable")
        return []

    monkeypatch.setattr(_mod._anatomy, "_iter_rules", _partial)
    errors: list[str] = []
    _mod.check_rules_index(root, errors)
    assert any("rule discovery is" in e for e in errors), errors


def test_main_exits_zero_and_prints_ok_when_clean(monkeypatch, tmp_path, capsys):
    target = tmp_path / "r.md"
    target.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate-rules.py", str(target)])
    monkeypatch.setattr(_mod, "validate", lambda *a, **k: None)
    _mod.main()  # no SystemExit
    assert "OK" in capsys.readouterr().out


def test_main_exits_one_when_validate_reports_errors(monkeypatch, tmp_path, capsys):
    target = tmp_path / "r.md"
    target.write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate-rules.py", str(target)])

    def _fake(path, errors, warnings, repo_root):
        errors.append("BOOM injected error")

    monkeypatch.setattr(_mod, "validate", _fake)
    with pytest.raises(SystemExit) as exc:
        _mod.main()
    assert exc.value.code == 1
    assert "BOOM" in capsys.readouterr().out


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


def test_non_utf8_file_reports_error_not_traceback(tmp_path):
    # A non-UTF-8 byte in a scanned .md or .py must produce a clean ERROR, not an
    # uncaught UnicodeDecodeError crashing the whole validator.
    (tmp_path / "skills" / "demo").mkdir(parents=True)
    (tmp_path / "skills" / "demo" / "SKILL.md").write_bytes(b"\xff\xfe bad bytes")
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "thing.py").write_bytes(b"\xff not utf-8")
    errors = _repo_errors(tmp_path)  # must not raise
    assert _has(errors, "cannot read file")
    assert sum("cannot read file" in e for e in errors) == 2


# ── validate() error paths and main() (tests-781e4953, tests-b4fcf9ec) ────────


def _validate(tmp_path, path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    validate(path, errors, warnings, tmp_path)
    return errors, warnings


def test_unreadable_rule_file_reports_an_error(tmp_path):
    # A directory named like a rule: read_text raises IsADirectoryError (an OSError).
    path = tmp_path / "a-rule.md"
    path.mkdir()
    errors, _ = _validate(tmp_path, path)
    assert _has(errors, "cannot read file")


def test_frontmatter_without_paths_and_an_empty_body_warns(tmp_path):
    path = tmp_path / "a-rule.md"
    path.write_text("---\ntitle: x\n---\n\n   \n", encoding="utf-8")
    errors, warnings = _validate(tmp_path, path)
    assert errors == []
    assert _has(warnings, "body is empty after frontmatter")


def test_paths_glob_traversing_outside_the_repo_is_rejected(tmp_path):
    path = tmp_path / "a-rule.md"
    path.write_text("---\npaths:\n  - ../../etc/*.conf\n---\n\nBody.\n", encoding="utf-8")
    errors, _ = _validate(tmp_path, path)
    assert _has(errors, "must not traverse outside repo root")


def test_unreadable_claude_md_reports_an_error(tmp_path):
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").mkdir()
    errors: list[str] = []
    _mod.check_repo_rules(tmp_path, errors)
    assert _has(errors, "CLAUDE.md: cannot read file")


def test_claude_md_without_a_conventions_section_is_an_error(tmp_path):
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    (tmp_path / "CLAUDE.md").write_text("# Title\n\nNo conventions here.\n", encoding="utf-8")
    errors: list[str] = []
    _mod.check_repo_rules(tmp_path, errors)
    assert _has(errors, "no '## Conventions' section")


def _main_on(monkeypatch, tmp_path, argv: list[str]):
    monkeypatch.setattr(sys, "argv", ["validate-rules.py", *argv])
    monkeypatch.setattr(_mod, "__file__", str(tmp_path / "scripts" / "validate-rules.py"))
    return _mod.main()


def test_main_without_argv_exits_zero_when_there_is_no_rules_dir(tmp_path, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        _main_on(monkeypatch, tmp_path, [])
    assert exc.value.code == 0


def test_main_without_argv_discovers_rules_and_prints_warnings(tmp_path, monkeypatch, capsys):
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "a-rule.md").write_text("---\ntitle: x\n---\n\n", encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text("## Conventions\n\n- `a-rule.md`\n", encoding="utf-8")
    assert _main_on(monkeypatch, tmp_path, []) is None
    out = capsys.readouterr().out
    assert "WARN" in out
    assert "OK  1 rule(s) validated." in out


def test_main_exits_one_when_a_rule_is_invalid(tmp_path, monkeypatch, capsys):
    """The non-zero exit is the only signal pre-commit and CI act on."""
    bad = tmp_path / "Not_Kebab.md"
    bad.write_text("---\npaths: nope\n---\n\nBody.\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        _main_on(monkeypatch, tmp_path, [str(bad)])
    assert exc.value.code == 1
    assert "error(s). Fix before committing." in capsys.readouterr().out


def test_module_runs_as_a_script(tmp_path, monkeypatch, capsys):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    bad = tmp_path / "Not_Kebab.md"
    bad.write_text("---\npaths: nope\n---\n\nBody.\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["validate-rules.py", str(bad)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 1
    assert "kebab-case" in capsys.readouterr().out
