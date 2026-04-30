"""Tests for scripts/hooks/validate-audit-findings-hook.py."""

import importlib.util
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "validate_audit_findings_hook",
    Path(__file__).parent.parent / "scripts" / "hooks" / "validate-audit-findings-hook.py",
)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]
parse_and_fix = _mod.parse_and_fix
ensure_pass_header = _mod._ensure_pass_header


# ── _ensure_pass_header ─────────────────────────────────────────────────────


class TestEnsurePassHeader:
    def test_empty_returns_unchanged(self):
        msgs: list[str] = []
        assert ensure_pass_header([], msgs, "Fixed") == []
        assert msgs == []

    def test_h3_before_h4_unchanged(self):
        lines = ["### Pass 1 — 2026-01-01", "", "#### [X-001] Finding", "Notes: ok"]
        msgs: list[str] = []
        result = ensure_pass_header(lines, msgs, "Fixed")
        assert result == lines
        assert msgs == []

    def test_orphaned_h4_no_existing_passes_wraps_in_pass_1(self):
        lines = ["#### [X-001] Finding", "Fixed: 2026-01-15", "Notes: ok"]
        msgs: list[str] = []
        result = ensure_pass_header(lines, msgs, "Fixed", "2026-01-15")
        assert result[0] == "### Pass 1 — 2026-01-15"
        assert any("Pass 1" in m for m in msgs)

    def test_orphaned_h4_before_pass_2_wraps_in_pass_1(self):
        lines = [
            "#### [X-001] Orphaned",
            "Fixed: 2026-01-10",
            "Notes: old",
            "",
            "### Pass 2 — 2026-01-20",
            "",
            "#### [X-002] Existing",
        ]
        msgs: list[str] = []
        result = ensure_pass_header(lines, msgs, "Fixed", "2026-01-10")
        pass_headers = [ln for ln in result if ln.startswith("### Pass ")]
        assert "### Pass 1 — 2026-01-10" in pass_headers
        assert "### Pass 2 — 2026-01-20" in pass_headers

    def test_n046_orphaned_h4_before_pass_1_no_duplicate(self):
        """N-046: orphaned h4 before existing Pass 1 must not produce two Pass 1 headers."""
        lines = [
            "#### [X-001] Orphaned",
            "Fixed: 2026-01-05",
            "Notes: orphaned",
            "",
            "### Pass 1 — 2026-01-10",
            "",
            "#### [X-002] Existing",
            "Fixed: 2026-01-10",
            "Notes: existing",
        ]
        msgs: list[str] = []
        result = ensure_pass_header(lines, msgs, "Fixed", "2026-01-05")
        pass_1 = [ln for ln in result if re.match(r"^### Pass 1 ", ln)]
        assert len(pass_1) == 1, f"Expected 1 Pass 1 header, got {len(pass_1)}: {pass_1}"

    def test_n046_orphaned_before_pass_1_and_2_uses_pass_3(self):
        """N-046: orphaned h4 before passes 1 and 2 must use Pass 3 (max+1)."""
        lines = [
            "#### [X-001] Orphaned",
            "",
            "### Pass 1 — 2026-01-10",
            "",
            "#### [X-002] Finding",
            "",
            "### Pass 2 — 2026-01-20",
            "",
            "#### [X-003] Finding",
        ]
        msgs: list[str] = []
        result = ensure_pass_header(lines, msgs, "Fixed", "2026-01-05")
        pass_nums = [
            int(m.group(1))
            for ln in result
            if (m := re.match(r"^### Pass (\d+)", ln))
        ]
        assert len(pass_nums) == len(set(pass_nums)), f"Duplicate pass numbers: {pass_nums}"


# ── parse_and_fix ────────────────────────────────────────────────────────────


def _text_to_fixed(text: str) -> tuple[str, list[str]]:
    return parse_and_fix(text)


CLEAN = """\
# Findings
Generated: 2026-04-01
Last validated: 2026-04-30

## Summary
- Total: 1 | Open: 0 | Fixed: 1 | Invalid: 0

## Open Findings

(none)

## Fixed

### Pass 1 — 2026-04-30

#### [X-001] Fixed finding
Fixed: 2026-04-30
Notes: done

## Invalid

(none)
"""


class TestParseAndFix:
    def test_clean_file_unchanged(self):
        fixed, msgs = _text_to_fixed(CLEAN)
        assert fixed == CLEAN
        assert msgs == []

    def test_duplicate_fixed_sections_merged(self):
        text = """\
# Findings
Generated: 2026-04-01

## Summary
- Total: 2 | Open: 0 | Fixed: 2 | Invalid: 0

## Open Findings

(none)

## Fixed

### Pass 1 — 2026-04-01

#### [X-001] First

## Fixed

### Pass 2 — 2026-04-02

#### [X-002] Second

## Invalid

(none)
"""
        fixed, msgs = _text_to_fixed(text)
        assert fixed.count("## Fixed") == 1
        assert any("merged" in m for m in msgs)

    def test_summary_counts_corrected(self):
        text = """\
# Findings
Generated: 2026-04-01

## Summary
- Total: 99 | Open: 99 | Fixed: 0 | Invalid: 0

## Open Findings

#### [X-001] Open finding

## Fixed

(none)

## Invalid

(none)
"""
        fixed, _ = _text_to_fixed(text)
        assert "Total: 1 | Open: 1 | Fixed: 0 | Invalid: 0" in fixed

    def test_nonconforming_h3_renamed(self):
        text = """\
# Findings
Generated: 2026-04-01

## Summary
- Total: 1 | Open: 0 | Fixed: 1 | Invalid: 0

## Open Findings

(none)

## Fixed

### 2026-04-01, first pass

#### [X-001] Finding
Fixed: 2026-04-01
Notes: done

## Invalid

(none)
"""
        fixed, msgs = _text_to_fixed(text)
        assert "### Pass 1 — 2026-04-01" in fixed
        assert any("renamed" in m for m in msgs)

    def test_orphaned_h4_wrapped_in_pass(self):
        text = """\
# Findings
Generated: 2026-04-01
Last validated: 2026-04-30

## Summary
- Total: 1 | Open: 0 | Fixed: 1 | Invalid: 0

## Open Findings

(none)

## Fixed

#### [X-001] Orphaned finding
Fixed: 2026-04-30
Notes: done

## Invalid

(none)
"""
        fixed, msgs = _text_to_fixed(text)
        assert "### Pass" in fixed
        assert any("added missing pass header" in m for m in msgs)
