"""Tests for skills/nitpicker/scripts/check-rules-anatomy.py."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_TOOL = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "check-rules-anatomy.py"
_spec = importlib.util.spec_from_file_location("check_rules_anatomy", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_parse_frontmatter = _mod._parse_frontmatter
_check_file = _mod._check_file
_iter_rules = _mod._iter_rules


def _has(findings: list[dict], code: str) -> bool:
    return any(f["code"] == code for f in findings)


def _severity(findings: list[dict], code: str) -> str | None:
    for f in findings:
        if f["code"] == code:
            return f["severity"]
    return None


# ── _parse_frontmatter ────────────────────────────────────────────────────────


class TestParseFrontmatter:
    def test_no_frontmatter_returns_empty_dict_and_full_text(self):
        text = "# Title\n\nNever use grep.\n"
        fm, body = _parse_frontmatter(text)
        assert fm == {}
        assert body == text

    def test_valid_path_scoped_frontmatter(self):
        text = '---\npaths:\n  - "src/**/*.ts"\n---\n\nAlways use strict mode.\n'
        fm, body = _parse_frontmatter(text)
        assert fm["paths"] == ["src/**/*.ts"]
        assert "strict mode" in body

    def test_valid_plain_frontmatter_no_paths(self):
        text = "---\ntitle: some rule\n---\n\nNever commit without review.\n"
        fm, _ = _parse_frontmatter(text)
        assert fm.get("title") == "some rule"

    def test_malformed_unclosed_frontmatter_returns_none(self):
        text = "---\npaths:\n  - src/**\nno closing\n"
        fm, _ = _parse_frontmatter(text)
        assert fm is None

    def test_multiple_paths(self):
        text = '---\npaths:\n  - "src/**/*.ts"\n  - "src/**/*.tsx"\n---\n\nBody.\n'
        fm, _ = _parse_frontmatter(text)
        assert fm["paths"] == ["src/**/*.ts", "src/**/*.tsx"]

    def test_flow_style_paths_list(self):
        """paths: ["src/**"] must parse as a list, not a scalar (else false paths_not_list)."""
        text = "---\npaths: [\"src/**\", 'lib/**']\n---\n\nBody.\n"
        fm, _ = _parse_frontmatter(text)
        assert fm["paths"] == ["src/**", "lib/**"]

    def test_blank_line_inside_paths_list_keeps_all_items(self):
        # A blank line between block-sequence items must not drop earlier items.
        # Single source of truth: validate-rules.py imports this parser.
        text = '---\npaths:\n  - "stale/removed/*"\n\n  - "src/*"\n---\nbody\n'
        fm, _ = _parse_frontmatter(text)
        assert fm is not None and fm["paths"] == ["stale/removed/*", "src/*"]

    def test_crlf_frontmatter_is_parsed(self):
        """CRLF line endings must not defeat frontmatter detection."""
        text = '---\r\npaths:\r\n  - "src/**"\r\n---\r\n\r\nBody.\r\n'
        fm, _ = _parse_frontmatter(text)
        assert fm is not None and fm["paths"] == ["src/**"]

    def test_scalar_value_in_frontmatter(self):
        text = "---\nname: my-rule\ndescription: test\n---\n\nBody.\n"
        fm, _ = _parse_frontmatter(text)
        assert fm["name"] == "my-rule"
        assert fm["description"] == "test"


# ── _check_file ────────────────────────────────────────────────────────────────


class TestCheckFile:
    def test_valid_plain_rule_no_findings(self, tmp_path):
        f = tmp_path / "my-rule.md"
        f.write_text("# My Rule\n\nNever run git push without review.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert findings == []

    def test_valid_path_scoped_rule_no_findings(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "foo.ts").write_text("// ts file", encoding="utf-8")
        f = tmp_path / "ts-rule.md"
        content = '---\npaths:\n  - "src/**/*.ts"\n---\n\nAlways add return types.\n'
        f.write_text(content, encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert not _has(findings, "stale_glob")
        assert not _has(findings, "malformed_frontmatter")

    def test_non_md_extension(self, tmp_path):
        f = tmp_path / "my-rule.txt"
        f.write_text("Never use grep.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "non_md_extension")

    def test_non_kebab_case_filename(self, tmp_path):
        f = tmp_path / "MyRule.md"
        f.write_text("Never use grep.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "non_kebab_case")

    def test_uppercase_filename(self, tmp_path):
        f = tmp_path / "SEARCH_TOOLS.md"
        f.write_text("Never use grep.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "non_kebab_case")

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty-rule.md"
        f.write_text("", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "empty_file")
        assert _severity(findings, "empty_file") == "High"

    def test_whitespace_only_file(self, tmp_path):
        f = tmp_path / "blank-rule.md"
        f.write_text("   \n  \n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "empty_file")

    def test_malformed_frontmatter(self, tmp_path):
        f = tmp_path / "bad-rule.md"
        f.write_text("---\npaths:\n  - src/**\nno close\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "malformed_frontmatter")

    def test_empty_body_after_frontmatter(self, tmp_path):
        f = tmp_path / "no-body.md"
        f.write_text("---\nkey: val\n---\n\n   \n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "empty_body")

    def test_paths_not_a_list(self, tmp_path):
        f = tmp_path / "bad-paths.md"
        f.write_text("---\npaths: src/**/*.ts\n---\n\nAlways add types.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "paths_not_list")

    def test_empty_glob(self, tmp_path):
        f = tmp_path / "empty-glob.md"
        f.write_text('---\npaths:\n  - ""\n---\n\nAlways add types.\n', encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "empty_glob")

    def test_absolute_glob(self, tmp_path):
        f = tmp_path / "abs-glob.md"
        content = "---\npaths:\n  - /absolute/path/*.ts\n---\n\nAlways add types.\n"
        f.write_text(content, encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "absolute_glob")

    def test_traversal_glob(self, tmp_path):
        f = tmp_path / "traverse-glob.md"
        content = "---\npaths:\n  - ../outside/*.ts\n---\n\nAlways add types.\n"
        f.write_text(content, encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "traversal_glob")

    def test_stale_glob_warns(self, tmp_path):
        f = tmp_path / "stale-glob.md"
        content = "---\npaths:\n  - nonexistent/**/*.ts\n---\n\nAlways add types.\n"
        f.write_text(content, encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "stale_glob")
        assert _severity(findings, "stale_glob") == "Low"

    def test_hedged_language_prefer(self, tmp_path):
        f = tmp_path / "hedged-rule.md"
        f.write_text("# Rule\n\nPrefer rg over grep.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "hedged_language")
        assert _severity(findings, "hedged_language") == "High"

    def test_hedged_language_try_to(self, tmp_path):
        f = tmp_path / "hedged-rule.md"
        f.write_text("# Rule\n\nTry to avoid using grep.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "hedged_language")

    def test_hedged_language_consider(self, tmp_path):
        f = tmp_path / "hedged-rule.md"
        f.write_text("# Rule\n\nConsider using rg.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "hedged_language")

    def test_hedged_language_in_code_block_not_flagged(self, tmp_path):
        f = tmp_path / "clean-rule.md"
        f.write_text("# Rule\n\nNever use grep.\n\n```\nprefer rg\n```\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert not _has(findings, "hedged_language")

    def test_hedged_language_in_tilde_fence_not_flagged(self, tmp_path):
        f = tmp_path / "clean-rule.md"
        f.write_text("# Rule\n\nNever use grep.\n\n~~~\ntry to use rg\n~~~\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert not _has(findings, "hedged_language")

    def test_heading_lines_not_flagged_for_hedged(self, tmp_path):
        f = tmp_path / "heading-rule.md"
        f.write_text("# Prefer rg over grep\n\nNever use grep.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert not _has(findings, "hedged_language")

    def test_hedged_language_line_number_is_file_relative(self, tmp_path):
        # frontmatter is 3 lines (---\nkey: val\n---), body starts at line 4
        f = tmp_path / "with-fm.md"
        f.write_text("---\nkey: val\n---\n\nPrefer rg.\n", encoding="utf-8")
        findings = _check_file(f, tmp_path)
        assert _has(findings, "hedged_language")
        detail = next(fi["detail"] for fi in findings if fi["code"] == "hedged_language")
        # file line 5 (frontmatter=3 lines + blank + "Prefer rg.")
        assert "Line 5" in detail

    def test_dangling_symlink(self, tmp_path):
        sym = tmp_path / "dangling-rule.md"
        sym.symlink_to(tmp_path / "nonexistent.md")
        findings = _check_file(sym, tmp_path)
        assert _has(findings, "dangling_symlink")
        assert findings[0]["severity"] == "High"
        assert len(findings) == 1  # returns early


# ── _iter_rules ────────────────────────────────────────────────────────────────


class TestIterRules:
    def test_empty_directory(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        result = _iter_rules(rules_dir)
        assert result == []

    def test_single_md_file(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        f = rules_dir / "my-rule.md"
        f.write_text("Never use grep.\n", encoding="utf-8")
        result = _iter_rules(rules_dir)
        assert result == [f]

    def test_non_md_files_excluded(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "rule.md").write_text("x", encoding="utf-8")
        (rules_dir / "rule.txt").write_text("x", encoding="utf-8")
        result = _iter_rules(rules_dir)
        assert len(result) == 1
        assert result[0].name == "rule.md"

    def test_nested_directories(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        sub = rules_dir / "sub"
        sub.mkdir(parents=True)
        (rules_dir / "top.md").write_text("x", encoding="utf-8")
        (sub / "nested.md").write_text("x", encoding="utf-8")
        result = _iter_rules(rules_dir)
        assert len(result) == 2

    def test_dangling_symlink_included(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        sym = rules_dir / "dangling.md"
        sym.symlink_to(rules_dir / "nonexistent.md")
        result = _iter_rules(rules_dir)
        assert sym in result

    def test_symlink_loop_prevention(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "rule.md").write_text("x", encoding="utf-8")
        result = _iter_rules(rules_dir)
        assert len(result) == 1  # no infinite loop

    def test_returns_sorted(self, tmp_path):
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "z-rule.md").write_text("x", encoding="utf-8")
        (rules_dir / "a-rule.md").write_text("x", encoding="utf-8")
        result = _iter_rules(rules_dir)
        assert result[0].name == "a-rule.md"


# ── main ──────────────────────────────────────────────────────────────────────


class TestMain:
    def _setup_rules(self, tmp_path: Path, rules: dict[str, str]) -> None:
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        for name, content in rules.items():
            (rules_dir / name).write_text(content, encoding="utf-8")

    def _main(self, monkeypatch, args):
        monkeypatch.setattr(sys, "argv", args)
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        return exc.value.code

    def test_explicit_path_without_rules_dir_exits_1(self, tmp_path, capsys, monkeypatch):
        # The argument is a project root. A supplied path lacking .claude/rules/
        # is a misconfiguration (e.g. passing `.claude/rules/` itself), not a
        # clean repo — it must fail rather than report a silently green run.
        code = self._main(monkeypatch, ["prog", str(tmp_path)])
        assert code == 1
        assert "not found" in capsys.readouterr().err

    def test_no_arg_and_no_rules_dir_exits_0(self, tmp_path, capsys, monkeypatch):
        monkeypatch.chdir(tmp_path)
        code = self._main(monkeypatch, ["prog"])
        assert code == 0
        data = __import__("json").loads(capsys.readouterr().out)
        assert data["exists"] is False

    def test_empty_rules_dir_exits_0(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        code = self._main(monkeypatch, ["prog", str(tmp_path)])
        assert code == 0
        data = __import__("json").loads(capsys.readouterr().out)
        assert data["message"] == ".claude/rules/ exists but is empty"

    def test_clean_rules_exits_0(self, tmp_path, capsys, monkeypatch):
        self._setup_rules(tmp_path, {"my-rule.md": "# Title\n\nNever use grep.\n"})
        code = self._main(monkeypatch, ["prog", str(tmp_path)])
        assert code == 0
        data = __import__("json").loads(capsys.readouterr().out)
        assert data["summary"]["ok"] == 1

    def test_rules_with_high_issue_exits_1(self, tmp_path, monkeypatch):
        self._setup_rules(tmp_path, {"empty-rule.md": ""})
        code = self._main(monkeypatch, ["prog", str(tmp_path)])
        assert code == 1

    def test_rules_with_only_low_issue_exits_0(self, tmp_path, capsys, monkeypatch):
        self._setup_rules(tmp_path, {"MyRule.md": "# Rule\n\nNever use grep.\n"})
        code = self._main(monkeypatch, ["prog", str(tmp_path)])
        assert code == 0
        data = __import__("json").loads(capsys.readouterr().out)
        assert data["summary"]["with_issues"] == 1

    def test_hedged_language_exits_1(self, tmp_path, monkeypatch):
        # Hedged phrasing blocks: a detector that never sets the exit code is
        # decoration, and unconditional phrasing is the point of a rule file.
        self._setup_rules(tmp_path, {"my-rule.md": "# Rule\n\nPrefer rg.\n"})
        assert self._main(monkeypatch, ["prog", str(tmp_path)]) == 1

    def test_default_cwd_used_when_no_arg(self, tmp_path, capsys, monkeypatch):
        (tmp_path / ".claude" / "rules").mkdir(parents=True)
        monkeypatch.chdir(tmp_path)
        code = self._main(monkeypatch, ["prog"])
        assert code == 0
        data = __import__("json").loads(capsys.readouterr().out)
        assert data["exists"] is True

    def test_json_report_structure(self, tmp_path, capsys, monkeypatch):
        self._setup_rules(tmp_path, {"my-rule.md": "# Rule\n\nNever use grep.\n"})
        self._main(monkeypatch, ["prog", str(tmp_path)])
        data = __import__("json").loads(capsys.readouterr().out)
        assert "files" in data
        assert "summary" in data
        assert data["summary"]["total"] == 1

    def test_path_outside_project_root_uses_absolute(self, tmp_path, capsys, monkeypatch):
        """path.relative_to() raises ValueError when path is outside project_root."""
        self._setup_rules(tmp_path, {"my-rule.md": "Never use grep.\n"})

        def raise_value_error(*_args, **_kwargs):
            raise ValueError("not relative")

        with patch.object(Path, "relative_to", raise_value_error):
            self._main(monkeypatch, ["prog", str(tmp_path)])
        data = __import__("json").loads(capsys.readouterr().out)
        assert data["files"][0]["file"].startswith("/")


# ── edge cases not covered above ─────────────────────────────────────────────


class TestAdditionalCoverage:
    """Cover lines missed by the main test classes."""

    def test_parse_frontmatter_else_branch(self):
        """A frontmatter line with no ':' and no '  - ' hits the else branch (line 75)."""
        text = "---\nname: rule\ncontinuation-without-colon\n---\n\nNever use grep.\n"
        fm, body = _parse_frontmatter(text)
        assert "name" in fm
        assert "Never use grep" in body

    def test_check_file_oserror_on_read(self, tmp_path):
        """OSError reading the file (lines 98-100).

        Patches the read rather than chmod'ing to 0o000: root ignores
        permission bits, so a permission-based test silently skips under any
        container-based or self-hosted CI running as root.
        """
        f = tmp_path / "unreadable.md"
        f.write_text("Never use grep.\n", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            findings = _check_file(f, tmp_path)
        assert any(fi["code"] == "unreadable" for fi in findings)

    def test_iter_rules_permission_error(self, tmp_path):
        """PermissionError in os.scandir is swallowed (lines 175-176)."""
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        with patch("os.scandir", side_effect=PermissionError("denied")):
            result = _iter_rules(rules_dir)
        assert result == []

    def test_iter_rules_resolve_oserror(self, tmp_path):
        """OSError in rules_dir.resolve() returns [] (lines 158-159)."""
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        with patch.object(Path, "resolve", side_effect=OSError("io error")):
            result = _iter_rules(rules_dir)
        assert result == []

    def test_iter_rules_seen_prevents_revisit(self, tmp_path):
        """'real in seen' guard prevents revisiting (line 161)."""
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "rule.md").write_text("x", encoding="utf-8")
        real = rules_dir.resolve()
        # Pass seen set already containing this directory
        result = _iter_rules(rules_dir, seen={real})
        assert result == []


# --- Regression test for audit fix (2026-07-09) ---


def test_paths_list_parsed_at_non_two_space_indent():
    text = '---\ndescription: d\npaths:\n    - "src/**"\n    - "lib/**"\n---\nbody\n'
    fm, _ = _parse_frontmatter(text)
    assert fm.get("paths") == ["src/**", "lib/**"]


def test_unindented_block_sequence_matches_indented():
    unindented = '---\npaths:\n- "src/**"\n- "lib/**"\n---\nbody\n'
    indented = '---\npaths:\n  - "src/**"\n  - "lib/**"\n---\nbody\n'
    assert _parse_frontmatter(unindented)[0]["paths"] == ["src/**", "lib/**"]
    assert _parse_frontmatter(unindented)[0] == _parse_frontmatter(indented)[0]


def test_unindented_block_sequence_runs_path_glob_checks(tmp_path):
    """paths from an unindented block sequence must not be dropped (else all glob checks skip)."""
    f = tmp_path / "abs-rule.md"
    f.write_text("---\npaths:\n- /absolute/*.ts\n---\n\nAlways add types.\n", encoding="utf-8")
    findings = _check_file(f, tmp_path)
    assert _has(findings, "absolute_glob")
