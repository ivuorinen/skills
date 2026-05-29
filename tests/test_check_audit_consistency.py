"""Tests for skills/nitpicker/check-audit-consistency.py."""

import importlib.util
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "skills" / "nitpicker" / "check-audit-consistency.py"
_spec = importlib.util.spec_from_file_location("check_audit_consistency", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

check_file = _mod.check_file


def _run(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    check_file(path, errors, warnings)
    return errors, warnings


def _has(items: list[str], fragment: str) -> bool:
    return any(fragment in item for item in items)


# ── fixtures ──────────────────────────────────────────────────────────────────

VALID_FINDINGS = """\
# Nitpicker Findings
Generated: 2026-01-01
Last validated: 2026-01-01

## Summary
- Total: 2 | Open: 1 | Fixed: 1 | Invalid: 0

## Open Findings

### High

#### [N-001] Some open finding
Category: correctness
Area: src/
Problem: A problem.
Evidence: Some evidence.
Impact: Some impact.
Fix: A fix.

## Fixed

### Pass 1 — 2026-01-01

#### [N-002] A fixed finding
Fixed: 2026-01-01
Notes: Fixed it.

## Invalid

### Pass 1 — 2026-01-01

"""

VALID_NO_FINDINGS = """\
# Nitpicker Findings
Generated: 2026-01-01
Last validated: 2026-01-01

## Summary
- Total: 0 | Open: 0 | Fixed: 0 | Invalid: 0

## Open Findings

## Fixed

## Invalid

"""


# ── check_file: valid inputs ───────────────────────────────────────────────────


class TestCheckFileValid:
    def test_valid_findings_no_errors(self, tmp_path):
        f = tmp_path / "nitpicker-findings.md"
        f.write_text(VALID_FINDINGS, encoding="utf-8")
        errors, _ = _run(f)
        assert errors == []

    def test_valid_empty_findings_no_errors(self, tmp_path):
        f = tmp_path / "nitpicker-findings.md"
        f.write_text(VALID_NO_FINDINGS, encoding="utf-8")
        errors, _ = _run(f)
        assert errors == []

    def test_no_warnings_on_valid(self, tmp_path):
        f = tmp_path / "nitpicker-findings.md"
        f.write_text(VALID_FINDINGS, encoding="utf-8")
        _, warnings = _run(f)
        assert warnings == []


# ── check_file: unreadable ─────────────────────────────────────────────────────


class TestCheckFileUnreadable:
    def test_unreadable_file_produces_error(self, tmp_path):
        missing = tmp_path / "missing.md"
        errors, _ = _run(missing)
        assert _has(errors, "cannot read")


# ── check_file: missing sections ──────────────────────────────────────────────


class TestMissingSections:
    def test_missing_summary(self, tmp_path):
        content = VALID_FINDINGS.replace("## Summary\n", "")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "missing required section '## Summary'")

    def test_missing_open_findings(self, tmp_path):
        content = VALID_FINDINGS.replace("## Open Findings\n", "")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "'## Open Findings'")

    def test_missing_fixed(self, tmp_path):
        content = VALID_FINDINGS.replace("## Fixed\n", "")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "'## Fixed'")

    def test_missing_invalid(self, tmp_path):
        content = VALID_FINDINGS.replace("## Invalid\n", "")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "'## Invalid'")


# ── check_file: summary count mismatch ────────────────────────────────────────


class TestSummaryMismatch:
    def test_wrong_open_count(self, tmp_path):
        content = VALID_FINDINGS.replace("Open: 1", "Open: 5")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "Summary Open:")

    def test_wrong_fixed_count(self, tmp_path):
        content = VALID_FINDINGS.replace("Fixed: 1", "Fixed: 0")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "Summary Fixed:")

    def test_wrong_invalid_count(self, tmp_path):
        content = VALID_FINDINGS.replace("Invalid: 0", "Invalid: 3")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "Summary Invalid:")

    def test_wrong_total_count(self, tmp_path):
        content = VALID_FINDINGS.replace("Total: 2", "Total: 99")
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "Summary Total:")

    def test_no_summary_line_warns(self, tmp_path):
        content = VALID_FINDINGS.replace(
            "- Total: 2 | Open: 1 | Fixed: 1 | Invalid: 0", "- no counts here"
        )
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        _, warnings = _run(f)
        assert _has(warnings, "no Summary line")


# ── check_file: ID uniqueness ──────────────────────────────────────────────────


class TestIdUniqueness:
    def test_duplicate_id_in_open(self, tmp_path):
        content = """\
# Findings
Generated: 2026-01-01
Last validated: 2026-01-01

## Summary
- Total: 2 | Open: 2 | Fixed: 0 | Invalid: 0

## Open Findings

### High

#### [N-001] First
#### [N-001] Duplicate

## Fixed

## Invalid

"""
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "duplicate ID [N-001]")

    def test_id_in_both_open_and_fixed(self, tmp_path):
        content = """\
# Findings
Generated: 2026-01-01
Last validated: 2026-01-01

## Summary
- Total: 2 | Open: 1 | Fixed: 1 | Invalid: 0

## Open Findings

### High

#### [N-001] Open finding

## Fixed

### Pass 1 — 2026-01-01

#### [N-001] Same ID in Fixed

## Invalid

"""
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "both Open Findings and Fixed/Invalid")

    def test_id_in_both_open_and_invalid(self, tmp_path):
        content = """\
# Findings
Generated: 2026-01-01
Last validated: 2026-01-01

## Summary
- Total: 2 | Open: 1 | Fixed: 0 | Invalid: 1

## Open Findings

### High

#### [N-001] Open finding

## Fixed

## Invalid

### Pass 1 — 2026-01-01

#### [N-001] Same ID in Invalid

"""
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "both Open Findings and Fixed/Invalid")


# ── check_file: pass header enforcement ───────────────────────────────────────


class TestPassHeaders:
    def test_fixed_without_pass_header_errors(self, tmp_path):
        content = """\
# Findings
Generated: 2026-01-01
Last validated: 2026-01-01

## Summary
- Total: 1 | Open: 0 | Fixed: 1 | Invalid: 0

## Open Findings

## Fixed

#### [N-001] No pass header

## Invalid

"""
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "not under '### Pass N — YYYY-MM-DD'")

    def test_invalid_without_pass_header_errors(self, tmp_path):
        content = """\
# Findings
Generated: 2026-01-01
Last validated: 2026-01-01

## Summary
- Total: 1 | Open: 0 | Fixed: 0 | Invalid: 1

## Open Findings

## Fixed

## Invalid

#### [N-001] No pass header

"""
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "not under '### Pass N — YYYY-MM-DD'")

    def test_valid_pass_header_no_error(self, tmp_path):
        f = tmp_path / "x-findings.md"
        f.write_text(VALID_FINDINGS, encoding="utf-8")
        errors, _ = _run(f)
        assert not _has(errors, "not under")


# ── check_file: header level jumps ────────────────────────────────────────────


class TestHeaderLevelJumps:
    def test_header_jump_h2_to_h4_errors(self, tmp_path):
        content = """\
# Title

## Section

#### Jump

## Summary
- Total: 0 | Open: 0 | Fixed: 0 | Invalid: 0

## Open Findings

## Fixed

## Invalid

"""
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        assert _has(errors, "header jumps from h2 to h4")

    def test_header_inside_fence_not_flagged(self, tmp_path):
        content = VALID_NO_FINDINGS.replace(
            "## Open Findings\n",
            "## Open Findings\n\n```\n## inside fence\n```\n\n",
        )
        f = tmp_path / "x-findings.md"
        f.write_text(content, encoding="utf-8")
        errors, _ = _run(f)
        # The fence content may affect counts but not cause header-jump error
        assert not _has(errors, "header jumps")


# ── main ──────────────────────────────────────────────────────────────────────


class TestMain:
    def test_main_with_explicit_valid_file(self, tmp_path, capsys, monkeypatch):
        f = tmp_path / "nitpicker-findings.md"
        f.write_text(VALID_FINDINGS, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        _mod.main()
        out, _ = capsys.readouterr()
        assert "OK" in out

    def test_main_with_explicit_error_file(self, tmp_path, capsys, monkeypatch):
        content = VALID_FINDINGS.replace("Open: 1", "Open: 99")
        f = tmp_path / "nitpicker-findings.md"
        f.write_text(content, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        out, _ = capsys.readouterr()
        assert "error" in out.lower()

    def test_main_no_args_no_docs_audit(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog"])
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 0
        out, _ = capsys.readouterr()
        assert "docs/audit/ not found" in out

    def test_main_no_args_empty_docs_audit(self, tmp_path, capsys, monkeypatch):
        audit_dir = tmp_path / "docs" / "audit"
        audit_dir.mkdir(parents=True)
        monkeypatch.setattr(sys, "argv", ["prog"])
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 0
        out, _ = capsys.readouterr()
        assert "no *-findings.md" in out

    def test_main_no_args_finds_and_checks(self, tmp_path, capsys, monkeypatch):
        audit_dir = tmp_path / "docs" / "audit"
        audit_dir.mkdir(parents=True)
        f = audit_dir / "nitpicker-findings.md"
        f.write_text(VALID_FINDINGS, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["prog"])
        monkeypatch.chdir(tmp_path)
        _mod.main()
        out, _ = capsys.readouterr()
        assert "OK" in out

    def test_main_warnings_printed(self, tmp_path, capsys, monkeypatch):
        content = VALID_FINDINGS.replace(
            "- Total: 2 | Open: 1 | Fixed: 1 | Invalid: 0", "- no counts here"
        )
        f = tmp_path / "nitpicker-findings.md"
        f.write_text(content, encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        _mod.main()
        out, _ = capsys.readouterr()
        assert "WARN" in out
