"""Tests for skills/nitpicker/scripts/check-rules-anatomy.py."""

import importlib.util
import runpy
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

    @pytest.mark.parametrize("flag", ["--help", "-h"])
    def test_help_prints_usage_and_exits_zero(self, flag, capsys, monkeypatch):
        # Checked before the argument is resolved as a path, or `--help` would
        # be treated as a project root and error out.
        monkeypatch.setattr(sys, "argv", ["prog", flag])
        _mod.main()
        assert "Usage:" in capsys.readouterr().out

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

    def test_unresolvable_path_is_treated_as_escaping_the_root(self, tmp_path):
        """A path that cannot be resolved cannot be vouched for, so it is refused.

        Failing open here would make an unresolvable link the single easiest way
        past the containment check — and an attacker plants the link, so it is
        the case they control most directly.
        """
        f = tmp_path / "rule.md"
        f.write_text("Never push to main.\n", encoding="utf-8")

        with patch.object(Path, "resolve", side_effect=OSError("io error")):
            findings = _check_file(f, tmp_path, tmp_path)

        assert any(x["code"] == "symlink_escapes_root" for x in findings), (
            "an unresolvable path must fail closed, not be scanned"
        )

    def test_looks_illustrative_covers_each_non_path_shape(self):
        """Three things wear the shape of a repo path and are not one.

        All three were false positives on this check's first run against this
        repo's own rules, which is why each has a branch rather than a comment.
        """
        assert _mod._looks_illustrative("claude.ai"), "a domain is not a file"
        assert _mod._looks_illustrative("PyCQA/bandit"), "an org/repo slug is not a path"
        assert _mod._looks_illustrative("src/auth.py"), "a documented example is not a claim"
        assert _mod._looks_illustrative("skills/**/*.md"), "a glob is not a path"
        assert _mod._looks_illustrative("<placeholder>/x.py")
        assert _mod._looks_illustrative("/etc/passwd"), "absolute paths are out of scope"
        assert not _mod._looks_illustrative("skills/nitpicker/scripts/findings.py")

    def test_tracked_indexes_relative_paths_and_basenames(self, tmp_path):
        """A rule cites a file by whichever spelling reads clearly, so both resolve.

        `findings.py` and `skills/nitpicker/scripts/findings.py` are both correct
        prose for the same file; neither is stale.
        """
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "thing.py").write_text("x\n", encoding="utf-8")
        _mod._tracked.cache_clear()
        rel, base = _mod._tracked(tmp_path)

        assert "pkg/thing.py" in rel
        assert "thing.py" in base

    def test_stale_path_flags_only_what_is_actually_absent(self, tmp_path):
        """The check earns its place only if it separates a real miss from a real hit."""
        (tmp_path / "real.py").write_text("x\n", encoding="utf-8")
        f = tmp_path / "r.md"
        f.write_text(
            "# R\n\nNever skip it. See `real.py` and also `gone/missing.py`.\n"
            "The example `src/auth.py` is illustrative and must not be flagged.\n",
            encoding="utf-8",
        )
        _mod._tracked.cache_clear()
        findings = _check_file(f, tmp_path)

        stale = [x for x in findings if x["code"] == "stale_path"]
        assert len(stale) == 1, f"expected exactly the absent path, got {stale}"
        assert "src/auth.py" not in str(stale), "a documented example is not a stale path"
        assert "gone/missing.py" in stale[0]["detail"]
        assert stale[0]["severity"] == "Low", "must not block a commit on a judgement call"

    def test_buried_directive_scores_section_openers_not_prose(self, tmp_path):
        """Scoring every sentence inverts the signal in a repo that mandates 'never'.

        `skill-style.md` requires unconditional phrasing, so the word saturates
        ordinary prose; the first cut of this check flagged hardest the files
        that followed the style guide best. Only a heading or a bolded lead-in
        titles a rule, so only those are scored.
        """
        filler = ["Ordinary prose that says never in passing."] * 25
        buried = ["# R", "", *filler, "", "## Never touch the ledger", "", *filler]
        f = tmp_path / "long.md"
        f.write_text("\n".join(buried) + "\n", encoding="utf-8")
        _mod._tracked.cache_clear()

        hits = [x for x in _check_file(f, tmp_path) if x["code"] == "buried_directive"]
        assert len(hits) == 1, "the heading is the finding; the prose lines are not"
        assert "Never touch the ledger" in hits[0]["detail"]
        assert hits[0]["severity"] == "Low"

    def test_buried_directive_ignores_short_files_and_the_edges(self, tmp_path):
        """Depth is meaningless until there is enough file to get lost in.

        In a 10-line rule every line sits at some percentage, and a directive at
        the top or bottom is the one an agent does read.
        """
        short = tmp_path / "short.md"
        short.write_text("# R\n\n## Never do it\n\nBody.\n", encoding="utf-8")
        _mod._tracked.cache_clear()
        assert not [x for x in _check_file(short, tmp_path) if x["code"] == "buried_directive"]

        filler = ["Filler."] * 45
        edge = tmp_path / "edge.md"
        edge.write_text("\n".join(["## Never do it", "", *filler]) + "\n", encoding="utf-8")
        assert not [x for x in _check_file(edge, tmp_path) if x["code"] == "buried_directive"], (
            "a directive at the very top is not buried"
        )

    def test_iter_rules_permission_error(self, tmp_path):
        """PermissionError in os.scandir is swallowed (lines 175-176)."""
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        with patch("os.scandir", side_effect=PermissionError("denied")):
            result = _iter_rules(rules_dir)
        assert result == []

    def test_unreadable_rules_path_is_not_reported_as_a_missing_one(self, tmp_path):
        """An unreadable `.claude/rules` must not report as a clean, absent one.

        `Path.exists()` gives two different wrong answers across the versions
        this repo supports (>=3.11), which is why the check cannot rest on it:
        3.12 propagates PermissionError, so it escaped a CLI catching only
        ValueError; 3.13+ swallows EACCES and returns False, so the same
        directory took the missing-directory branch and came back clean at exit 0
        with nothing scanned. `stat()` separates "not there" from "cannot look"
        on every version, and only the first is a clean result.

        Asserting on the ValueError rather than on `exists()` keeps this test
        version-independent — the precondition is what differs, not the contract.
        """
        import os

        if os.geteuid() == 0:
            pytest.skip("root ignores permission bits, so EACCES cannot be provoked")

        parent = tmp_path / ".claude"
        parent.mkdir()
        (parent / "rules").mkdir()
        parent.chmod(0o000)
        try:
            with pytest.raises(ValueError, match="rules left unread"):
                _mod.check(tmp_path, False)
        finally:
            parent.chmod(0o755)

    def test_rules_path_that_is_a_regular_file_raises_valueerror(self, tmp_path):
        """A `.claude/rules` that is a file passes `exists()` and reaches `os.scandir`.

        `os.scandir` raises NotADirectoryError there. It is an OSError but not a
        PermissionError, so a handler catching only the latter let it escape —
        past a CLI that catches only ValueError, as an uncaught traceback, and
        past the MCP tool's ValueError validation path.
        """
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude" / "rules").touch()

        with pytest.raises(ValueError, match="rules left unread"):
            _mod.check(tmp_path, True)

    def test_iter_rules_resolve_oserror(self, tmp_path):
        """OSError in rules_dir.resolve() returns [] (lines 158-159)."""
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        with patch.object(Path, "resolve", side_effect=OSError("io error")):
            result = _iter_rules(rules_dir)
        assert result == []

    def test_iter_rules_resolve_oserror_is_recorded_not_silently_empty(self, tmp_path):
        """Returning [] without recording the failure reports a narrowed scan as clean.

        `check` cannot tell an empty result from an unreadable one, so a
        `resolve()` failure surfaced as "exists but is empty" — exit 0 with the
        rules unread. The scandir path already recorded; this one did not.
        """
        rules_dir = tmp_path / ".claude" / "rules"
        rules_dir.mkdir(parents=True)
        errors: list = []
        with patch.object(Path, "resolve", side_effect=OSError("io error")):
            result = _iter_rules(rules_dir, errors=errors)

        assert result == []
        assert errors, "a resolve failure must be recorded, not swallowed"
        assert errors[0][0] == rules_dir

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


def test_unterminated_fence_flagged_high(tmp_path):
    f = tmp_path / "unclosed.md"
    f.write_text("---\ntitle: R\n---\n\nAlways do X.\n\n```\nunclosed fence\n", encoding="utf-8")
    findings = _check_file(f, tmp_path)
    assert _has(findings, "unterminated_fence")
    assert _severity(findings, "unterminated_fence") == "High"


def test_four_backtick_fence_not_closed_by_three(tmp_path):
    f = tmp_path / "four.md"
    f.write_text("---\ntitle: R\n---\n\nAlways do X.\n\n````\n```\n", encoding="utf-8")
    findings = _check_file(f, tmp_path)
    assert _has(findings, "unterminated_fence")


def test_hedged_word_after_closed_fence_still_detected(tmp_path):
    # A code fence must not silence the hedged-language gate for later lines.
    f = tmp_path / "hedged.md"
    f.write_text(
        "---\ntitle: R\n---\n\n```\ncode\n```\n\nYou should consider skipping this.\n",
        encoding="utf-8",
    )
    findings = _check_file(f, tmp_path)
    assert _has(findings, "hedged_language")


def test_unindented_block_sequence_runs_path_glob_checks(tmp_path):
    """paths from an unindented block sequence must not be dropped (else all glob checks skip)."""
    f = tmp_path / "abs-rule.md"
    f.write_text("---\npaths:\n- /absolute/*.ts\n---\n\nAlways add types.\n", encoding="utf-8")
    findings = _check_file(f, tmp_path)
    assert _has(findings, "absolute_glob")


def test_unreadable_rules_dir_fails_the_gate(monkeypatch, tmp_path, capsys):
    """A rules subtree the process cannot read must fail the gate, not exit 0 on a
    silently narrowed scan."""
    rules = tmp_path / ".claude" / "rules"
    (rules / "sub").mkdir(parents=True)
    (rules / "ok.md").write_text(
        "---\nname: x\n---\n\nAlways add explicit types.\n", encoding="utf-8"
    )

    real_scandir = _mod.os.scandir

    def _scandir(path, *a, **k):
        if str(path).endswith("sub"):
            raise PermissionError(13, "denied")
        return real_scandir(path, *a, **k)

    monkeypatch.setattr(_mod.os, "scandir", _scandir)
    monkeypatch.setattr(sys, "argv", ["check-rules-anatomy.py", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        _mod.main()
    assert exc.value.code == 1
    assert "cannot scan" in capsys.readouterr().err


def test_paths_glob_that_the_stdlib_rejects_is_reported_not_crashed(tmp_path, monkeypatch):
    """Path.glob raises ValueError on some '**' spellings (CPython <3.13). The run
    must report it as a bad pattern rather than aborting the whole scan."""
    f = tmp_path / "rule.md"
    f.write_text("---\npaths:\n  - 'src/**bad/*.py'\n---\n\nBody.\n", encoding="utf-8")

    def _raises(*_a, **_k):
        raise ValueError("Invalid pattern")

    monkeypatch.setattr(Path, "glob", _raises)
    findings = _check_file(f, tmp_path)
    assert _has(findings, "invalid_glob")
    assert not _has(findings, "stale_glob")  # the `continue` skipped the staleness check


def test_module_runs_as_a_script(tmp_path, monkeypatch, capsys):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    monkeypatch.setattr(sys, "argv", ["check-rules-anatomy.py", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0
    assert '"rules_dir"' in capsys.readouterr().out
