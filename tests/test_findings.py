"""Tests for skills/nitpicker/scripts/findings.py — the per-finding audit store CLI."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "findings",
    Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "findings.py",
)
findings = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(findings)  # type: ignore[union-attr]

BODY = """## Problem
Token compared with `==`.

## Evidence
`src/auth.py:42` uses `token == expected`.

## Impact
Timing side-channel.

## Fix
Use `hmac.compare_digest`.
"""


def _new(root, **kw):
    args = {
        "auditor": "security",
        "severity": "high",
        "category": "security",
        "area": "src/auth.py",
        "title": "Token compared with ==",
        "body": BODY,
        "found": "2026-07-08",
    }
    args.update(kw)
    return findings.new_finding(root, **args)


def test_finding_id_stable_and_prefixed():
    a = findings.finding_id("security", "src/x.py", "Token compared with ==")
    b = findings.finding_id("security", "src/x.py", "Token compared with ==")
    assert a == b
    assert a.startswith("security-")
    suffix = a.rsplit("-", 1)[-1]
    assert len(suffix) == 8
    assert set(suffix) <= set("0123456789abcdef")
    assert findings.finding_id("security", "src/y.py", "Token compared with ==") != a


def test_new_writes_open_file_that_validates(tmp_path):
    path = _new(tmp_path)
    assert path.parent == tmp_path / "security" / "open"
    assert path.stem == findings.finding_id("security", "src/auth.py", "Token compared with ==")
    assert findings.validate_file(path) == []
    text = path.read_text(encoding="utf-8")
    assert "status: open" in text
    assert "# Token compared with ==" in text


def test_resolve_appends_ledger_and_deletes_open_file(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    ledger = findings.resolve_finding(
        tmp_path, fid, "fixed", "Switched to compare_digest.", date="2026-07-09"
    )
    assert not path.exists()
    assert ledger == findings.ledger_path(tmp_path)
    assert not (tmp_path / "security" / "resolved").exists()
    rec = findings.resolved_records(tmp_path)[fid]
    assert rec["status"] == "fixed"
    assert rec["resolved"] == "2026-07-09"
    assert "## Resolution" in rec["body"]
    assert "Switched to compare_digest." in rec["body"]
    # show reconstructs a valid finding document from the ledger
    shown = findings.show_finding(tmp_path, fid)
    assert "status: fixed" in shown
    assert "resolved: 2026-07-09" in shown
    assert findings.validate_store(tmp_path) == []


def test_resolve_unknown_id_raises(tmp_path):
    with pytest.raises(findings.FindingError):
        findings.resolve_finding(tmp_path, "security-deadbeef", "fixed", "n/a")


def test_validate_rejects_status_dir_mismatch(tmp_path):
    path = _new(tmp_path)
    moved = tmp_path / "security" / "resolved" / path.name
    moved.parent.mkdir(parents=True, exist_ok=True)
    path.rename(moved)
    errors = findings.validate_file(moved)
    assert any("status" in e for e in errors)


def test_validate_rejects_bad_enums_and_id_mismatch(tmp_path):
    path = _new(tmp_path)
    text = path.read_text(encoding="utf-8").replace("severity: high", "severity: enormous")
    path.write_text(text, encoding="utf-8")
    assert any("severity" in e for e in findings.validate_file(path))

    renamed = path.with_name("security-00000000.md")
    path.rename(renamed)
    text = renamed.read_text(encoding="utf-8").replace("severity: enormous", "severity: high")
    renamed.write_text(text, encoding="utf-8")
    assert any("does not match filename" in e for e in findings.validate_file(renamed))


def test_validate_requires_sections_for_open(tmp_path):
    path = _new(tmp_path, body="## Problem\nOnly a problem.\n")
    errors = findings.validate_file(path)
    assert any("Evidence" in e for e in errors)
    assert any("Fix" in e for e in errors)


def test_validate_accepts_legacy_id(tmp_path):
    path = _new(tmp_path)
    legacy = path.with_name("N-090.md")
    text = path.read_text(encoding="utf-8").replace(f"id: {path.stem}", "id: N-090")
    legacy.write_text(text, encoding="utf-8")
    path.unlink()
    assert findings.validate_file(legacy) == []


def test_store_validate_flags_id_open_and_resolved(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    open_text = path.read_text(encoding="utf-8")
    findings.resolve_finding(tmp_path, fid, "fixed", "done", date="2026-07-09")
    # Recreate the open file directly (corruption): the id is now both an open
    # file and a ledger record — validate must catch it.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(open_text, encoding="utf-8")
    errors = findings.validate_store(tmp_path)
    assert any("also open" in e for e in errors)


def test_index_deterministic_and_counts(tmp_path):
    _new(tmp_path)
    _new(
        tmp_path,
        auditor="tests",
        severity="critical",
        title="Assertion-free test",
        area="tests/test_x.py",
        category="tests",
    )
    p = _new(
        tmp_path,
        auditor="tests",
        severity="low",
        title="Sleepy test",
        area="tests/test_y.py",
        category="tests",
    )
    findings.resolve_finding(tmp_path, p.stem, "invalid", "Not flaky after all.", date="2026-07-09")

    out1 = findings.build_index(tmp_path)
    out2 = findings.build_index(tmp_path)
    assert out1 == out2
    compact = re.sub(r" +", " ", out1)
    assert "| security | 1 | 0 | 0 |" in compact
    assert "| tests | 1 | 0 | 1 |" in compact
    # critical sorts before high in the open list
    assert out1.index("Assertion-free test") < out1.index("Token compared with ==")
    path = findings.write_index(tmp_path)
    assert path.name == "INDEX.md"


V1_DOC = """# Nitpicker Findings
Generated: 2026-04-24
Last validated: 2026-07-06

## Summary
- Total: 3 | Open: 1 | Fixed: 1 | Invalid: 1

## Open Findings

### Advisory

#### [N-090] Skill name contains reserved word
Category: conventions
Area: skills/claude-rules-auditor/SKILL.md
Problem: The name contains "claude".
Evidence: Official docs forbid it.
Impact: Platform enforcement may reject the name.
Fix: Rename in the next major version.

## Fixed

### Pass 24 — 2026-07-06

#### [N-102] Workflow has no permissions block
Fixed: 2026-07-06
Notes: Added top-level permissions.

## Invalid

### Pass 3 — 2026-05-01

#### [N-014] Suspected dead code
Notes: The code path is reachable via the CLI.
"""


def test_migrate_v1_open_files_and_resolved_ledger(tmp_path):
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(V1_DOC, encoding="utf-8")
    root = tmp_path / "findings"
    count = findings.migrate_v1(src, root)
    assert count == 3

    open_file = root / "audit" / "open" / "N-090.md"
    assert open_file.exists()
    text = open_file.read_text(encoding="utf-8")
    assert "severity: advisory" in text
    assert "category: conventions" in text
    assert "area: skills/claude-rules-auditor/SKILL.md" in text
    assert "## Problem" in text and "## Fix" in text
    assert findings.validate_file(open_file) == []

    # resolved findings live in the ledger, not files
    assert not (root / "audit" / "resolved").exists()
    recs = findings.resolved_records(root)
    assert recs["N-102"]["status"] == "fixed"
    assert recs["N-102"]["resolved"] == "2026-07-06"
    assert "Added top-level permissions." in recs["N-102"]["body"]
    # provenance: v1 pass number and source file survive migration
    assert "Pass 24" in recs["N-102"]["body"]
    assert "nitpicker-findings.md" in recs["N-102"]["body"]
    assert recs["N-014"]["status"] == "invalid"
    assert recs["N-014"]["resolved"] == "2026-05-01"
    assert findings.validate_store(root) == []


@pytest.mark.parametrize(
    ("filename", "auditor"),
    [
        ("nitpicker-findings.md", "audit"),
        ("arch-findings.md", "arch"),
        ("doc-findings.md", "docs"),
        ("security-findings.md", "security"),
        ("claude-rules-auditor-findings.md", "agent-rules"),
        ("loophole-hunter-findings.md", "agent-loopholes"),
        ("hooks-enforcer-findings.md", "agent-hooks"),
        ("test-auditor-findings.md", "tests"),
        ("silent-failure-hunter-findings.md", "errors"),
    ],
)
def test_v1_auditor_mapping(filename, auditor):
    assert findings.v1_auditor(filename) == auditor


def test_cli_new_list_resolve_index(tmp_path, capsys):
    rc = findings.main(
        [
            "new",
            "--root",
            str(tmp_path),
            "--auditor",
            "security",
            "--severity",
            "high",
            "--category",
            "security",
            "--area",
            "src/auth.py",
            "--body",
            BODY,
            "Token compared with ==",
        ]
    )
    assert rc == 0
    fid = findings.finding_id("security", "src/auth.py", "Token compared with ==")

    rc = findings.main(["list", "--root", str(tmp_path)])
    assert rc == 0
    assert fid in capsys.readouterr().out

    rc = findings.main(
        ["resolve", "--root", str(tmp_path), fid, "--status", "fixed", "--notes", "done"]
    )
    assert rc == 0

    rc = findings.main(["validate", "--root", str(tmp_path)])
    assert rc == 0

    rc = findings.main(["index", "--root", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "INDEX.md").exists()


# ── hostile input and lifecycle guards ────────────────────────────────────────


def test_new_refuses_to_overwrite_existing_finding(tmp_path):
    path = _new(tmp_path)
    original = path.read_text(encoding="utf-8")
    with pytest.raises(findings.FindingError, match="already exists"):
        _new(tmp_path, severity="low", body="")
    assert path.read_text(encoding="utf-8") == original
    # --force overwrites deliberately
    forced = _new(tmp_path, severity="low", body="", force=True)
    assert forced == path
    assert "severity: low" in path.read_text(encoding="utf-8")


def test_new_refuses_overwrite_of_resolved_finding(tmp_path):
    path = _new(tmp_path)
    findings.resolve_finding(tmp_path, path.stem, "fixed", "done")
    with pytest.raises(findings.FindingError, match="already exists"):
        _new(tmp_path)


def test_new_rejects_path_traversal_auditor(tmp_path):
    with pytest.raises(findings.FindingError, match="invalid auditor"):
        _new(tmp_path, auditor="../../escape")
    assert not (tmp_path.parent / "escape").exists()


def test_new_rejects_newline_injection_in_fields(tmp_path):
    with pytest.raises(findings.FindingError, match="single-line"):
        _new(tmp_path, area="x\nseverity: critical")
    with pytest.raises(findings.FindingError, match="single-line"):
        _new(tmp_path, title="t\nstatus: fixed")


def test_resolve_rejects_glob_metacharacters_in_id(tmp_path):
    _new(tmp_path)
    with pytest.raises(findings.FindingError, match="malformed finding id"):
        findings.resolve_finding(tmp_path, "*", "fixed", "n/a")


def test_resolve_already_resolved_requires_force(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "done")
    with pytest.raises(findings.FindingError, match="already resolved"):
        findings.resolve_finding(tmp_path, fid, "invalid", "again")
    findings.resolve_finding(tmp_path, fid, "invalid", "again", force=True)
    rec = findings.resolved_records(tmp_path)[fid]
    assert rec["status"] == "invalid"
    # re-resolve replaced the ledger record rather than duplicating it
    assert sum(1 for r in findings.read_ledger(tmp_path) if r.get("id") == fid) == 1


def test_store_survives_non_utf8_file(tmp_path):
    _new(tmp_path)
    corrupt = tmp_path / "security" / "open" / "security-deadbeef.md"
    corrupt.write_bytes(b"\xff\xfe")
    errors = findings.validate_store(tmp_path)
    assert any("cannot read" in e for e in errors)
    # index generation skips the corrupt file instead of crashing
    out = findings.build_index(tmp_path)
    assert "Token compared with ==" in out


V1_FENCED_DOC = """# Security Findings
Generated: 2026-04-24

## Open Findings

### High

#### [N-200] Secret committed
Category: security
Area: src/cfg.py
Problem: A secret is hardcoded.
Evidence: the config contains
```python
secret = 1
```
Impact: Credential leak.
Fix: Move to env.
"""


def test_migrate_preserves_fenced_content(tmp_path):
    src = tmp_path / "security-findings.md"
    src.write_text(V1_FENCED_DOC, encoding="utf-8")
    root = tmp_path / "findings"
    assert findings.migrate_v1(src, root) == 1
    text = (root / "security" / "open" / "N-200.md").read_text(encoding="utf-8")
    assert "secret = 1" in text
    assert "Credential leak." in text
    assert findings.validate_file(root / "security" / "open" / "N-200.md") == []


# ── markdown formatting of generated files ───────────────────────────────────


def test_index_table_padded_to_column_width(tmp_path):
    _new(tmp_path)
    _new(
        tmp_path,
        auditor="tests",
        severity="critical",
        title="Assertion-free test",
        area="tests/test_x.py",
        category="tests",
    )
    out = findings.build_index(tmp_path)
    table = [ln for ln in out.splitlines() if ln.startswith("|")]
    assert len(table) >= 4
    # every row has identical length and identical pipe positions
    positions = [tuple(i for i, ch in enumerate(ln) if ch == "|") for ln in table]
    assert len(set(positions)) == 1
    # prettier style: "| Auditor  | ..." with space-padded pipes and dash-filled separator
    assert table[0].startswith("| Auditor")
    sep = table[1]
    cells = [c.strip() for c in sep.strip("|").split("|")]
    assert cells and all(c and set(c) == {"-"} for c in cells)
    assert sep.startswith("| -") and sep.endswith("- |")


def test_rendered_body_has_blank_lines_after_headings(tmp_path):
    path = _new(tmp_path, body="## Problem\np\n## Evidence\ne\n## Impact\ni\n## Fix\nf\n")
    text = path.read_text(encoding="utf-8")
    assert "## Problem\n\np" in text
    assert "## Evidence\n\ne" in text
    assert "\n\n\n" not in text
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_resolve_rejects_malformed_date(tmp_path):
    """A bad --date must be rejected before it lands in the append-only ledger."""
    path = _new(tmp_path)
    with pytest.raises(findings.FindingError, match="invalid --date"):
        findings.resolve_finding(tmp_path, path.stem, "fixed", "done", date="not-a-date")
    # the open file is untouched and nothing was written to the ledger
    assert path.exists()
    assert findings.read_ledger(tmp_path) == []


def test_baseline_write_read_roundtrip_and_clear(tmp_path):
    p1 = _new(tmp_path)
    findings.write_baseline(tmp_path, [p1.stem], "2026-07-10")
    assert findings.read_baseline(tmp_path) == {p1.stem}
    assert findings.baseline_path(tmp_path).exists()
    assert findings.clear_baseline(tmp_path) is True
    assert findings.read_baseline(tmp_path) == set()
    assert findings.clear_baseline(tmp_path) is False


def test_cli_baseline_then_list_excludes_baselined_but_shows_new(tmp_path, capsys):
    """release-gate ratchet: a pre-existing finding is baselined away, a NEW one is not."""
    old = _new(tmp_path)
    assert findings.main(["baseline", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    # a genuinely new finding filed after the baseline gets a new content-hash id
    new = _new(tmp_path, auditor="docs", title="Stale README", area="README.md", category="docs")
    assert (
        findings.main(["list", "--root", str(tmp_path), "--status", "open", "--exclude-baseline"])
        == 0
    )
    out = capsys.readouterr().out
    assert new.stem in out  # new finding blocks the gate
    assert old.stem not in out  # baselined finding is waived


def test_read_baseline_survives_malformed_file(tmp_path):
    _new(tmp_path)
    findings.baseline_path(tmp_path).write_text("{not json", encoding="utf-8")
    assert findings.read_baseline(tmp_path) == set()


def test_cli_baseline_refuses_overwrite_without_force(tmp_path, capsys):
    """The ratchet only tightens: re-baselining must be deliberate, not silent."""
    _new(tmp_path)
    assert findings.main(["baseline", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    _new(tmp_path, auditor="docs", title="New", area="n.md", category="docs")
    assert findings.main(["baseline", "--root", str(tmp_path)]) == 1  # refused
    assert "already exists" in capsys.readouterr().err
    assert findings.main(["baseline", "--root", str(tmp_path), "--force"]) == 0  # explicit


def test_pattern_covers_ignores_descendant_of_store():
    """A gitignore pattern naming a file inside the store must NOT be read as the
    whole store being ignored (else review-hygiene marking silently switches off)."""
    rel = "docs/audit/findings"
    assert findings._pattern_covers("docs/audit/findings", rel)  # exact
    assert findings._pattern_covers("docs", rel)  # ancestor
    assert not findings._pattern_covers("docs/audit/findings/resolved.jsonl", rel)  # descendant
    assert not findings._pattern_covers("docs/audit/findings/INDEX.md", rel)


def test_resolution_heading_gets_blank_line(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "All done.", date="2026-07-09")
    shown = findings.show_finding(tmp_path, fid)
    assert "## Resolution\n\nAll done." in shown
    assert "\n\n\n" not in shown


# ── audited fixes: duplicates, frontmatter, fences, v1 parser ─────────────────


def test_migrate_duplicate_id_across_sources_errors(tmp_path):
    doc = """# Security Findings
Generated: 2026-04-24

## Open Findings

### High

#### [N-300] First version
Category: security
Area: src/a.py
Problem: p
Evidence: e
Impact: i
Fix: f
"""
    src1 = tmp_path / "one" / "security-findings.md"
    src2 = tmp_path / "two" / "security-findings.md"
    src1.parent.mkdir()
    src2.parent.mkdir()
    src1.write_text(doc, encoding="utf-8")
    src2.write_text(doc.replace("First version", "Second version"), encoding="utf-8")
    root = tmp_path / "findings"
    assert findings.migrate_v1(src1, root) == 1
    target = root / "security" / "open" / "N-300.md"
    original = target.read_text(encoding="utf-8")
    with pytest.raises(findings.FindingError, match="duplicate id N-300"):
        findings.migrate_v1(src2, root)
    assert target.read_text(encoding="utf-8") == original


def test_resolve_preserves_unknown_frontmatter_keys(tmp_path):
    path = _new(tmp_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace("found: 2026-07-08", "found: 2026-07-08\ncve: CVE-2024-1234"),
        encoding="utf-8",
    )
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "done", date="2026-07-09")
    rec = findings.resolved_records(tmp_path)[fid]
    assert rec.get("extra", {}).get("cve") == "CVE-2024-1234"
    # and it round-trips back into the shown document
    assert "cve: CVE-2024-1234" in findings.show_finding(tmp_path, fid)
    assert findings.validate_store(tmp_path) == []


def test_normalize_body_preserves_fence_content():
    body = "## Problem\n```\n# comment\n~~~\n\n\nstill fenced\n```\nafter\n\n\nend\n"
    out = findings._normalize_body(body)
    # fence content byte-for-byte: pseudo-heading, ~~~ line, double blank
    assert "```\n# comment\n~~~\n\n\nstill fenced\n```" in out
    # blank runs outside fences still collapse
    assert "after\n\nend" in out


def test_fenced_pseudo_heading_survives_new_finding(tmp_path):
    path = _new(tmp_path, body=BODY + "\n```\n# not a heading\n```\n")
    text = path.read_text(encoding="utf-8")
    assert "```\n# not a heading\n```" in text


def test_migrate_preserves_multiparagraph_field_and_prose_colon_line(tmp_path):
    doc = """# Security Findings
Generated: 2026-04-24

## Open Findings

### High

#### [N-400] Multi-paragraph evidence
Category: security
Area: src/a.py
Problem: p
Evidence: first paragraph

second paragraph
Notes: part of evidence prose
Impact: i
Fix: f
"""
    src = tmp_path / "security-findings.md"
    src.write_text(doc, encoding="utf-8")
    root = tmp_path / "findings"
    assert findings.migrate_v1(src, root) == 1
    path = root / "security" / "open" / "N-400.md"
    text = path.read_text(encoding="utf-8")
    assert "first paragraph" in text
    assert "second paragraph" in text
    assert "Notes: part of evidence prose" in text
    assert "## Impact\n\ni" in text
    assert findings.validate_file(path) == []


def test_new_force_reopens_and_clears_ledger_entry(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "done")
    assert fid in findings.resolved_records(tmp_path)
    new_path = _new(tmp_path, force=True)
    assert new_path.parent.name == "open"
    # re-opening drops the ledger record so the id is not both open and resolved
    assert fid not in findings.resolved_records(tmp_path)
    assert findings.validate_store(tmp_path) == []


def test_new_collision_with_different_finding_named_in_error(tmp_path):
    path = _new(tmp_path)
    # hand-edited file whose title no longer matches what hashes to this id
    text = path.read_text(encoding="utf-8").replace(
        "# Token compared with ==", "# Something else entirely"
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(findings.FindingError, match="different finding"):
        _new(tmp_path)


def test_cli_migrate_missing_source_errors_cleanly(tmp_path, capsys):
    rc = findings.main(["migrate", "--root", str(tmp_path), str(tmp_path / "missing.md")])
    assert rc == 1
    assert "ERROR" in capsys.readouterr().err


# ── mutation-killing guards ───────────────────────────────────────────────────


def test_finding_id_field_boundaries():
    assert findings.finding_id("s", "ab", "c") != findings.finding_id("s", "a", "bc")


def test_resolve_rejects_open_status(tmp_path):
    path = _new(tmp_path)
    with pytest.raises(findings.FindingError, match="must be fixed"):
        findings.resolve_finding(tmp_path, path.stem, "open", "n/a")


def test_validate_rejects_malformed_dates(tmp_path):
    path = _new(tmp_path)
    text = path.read_text(encoding="utf-8").replace("found: 2026-07-08", "found: yesterday")
    path.write_text(text, encoding="utf-8")
    assert any("found date" in e for e in findings.validate_file(path))

    other = _new(tmp_path, title="Other finding")
    findings.resolve_finding(tmp_path, other.stem, "fixed", "done", date="2026-07-09")
    lp = findings.ledger_path(tmp_path)
    lp.write_text(
        lp.read_text(encoding="utf-8").replace('"resolved": "2026-07-09"', '"resolved": "someday"'),
        encoding="utf-8",
    )
    assert any("resolved date" in e for e in findings.validate_store(tmp_path))


def test_migrated_body_has_blank_lines_after_headings(tmp_path):
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(V1_DOC, encoding="utf-8")
    root = tmp_path / "findings"
    findings.migrate_v1(src, root)
    open_text = (root / "audit" / "open" / "N-090.md").read_text(encoding="utf-8")
    assert "## Problem\n\nThe name" in open_text
    assert "\n\n\n" not in open_text
    fixed_shown = findings.show_finding(root, "N-102")
    assert "## Resolution\n\nAdded top-level permissions." in fixed_shown
    assert "\n\n\n" not in fixed_shown


# --- Regression tests for audit fixes (2026-07-09) ---


def test_validate_flags_required_sections_hidden_in_code_fence(tmp_path):
    body = "## Problem\nreal\n\n```\n## Evidence\n## Impact\n## Fix\n```\n"
    path = _new(tmp_path, body=body)
    errors = findings.validate_file(path)
    assert any("Evidence" in e for e in errors)
    assert any("Impact" in e for e in errors)
    assert any("Fix" in e for e in errors)


def test_force_reresolve_replaces_resolution_without_duplicate(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "first note", date="2026-07-09")
    findings.resolve_finding(tmp_path, fid, "invalid", "second note", date="2026-07-10", force=True)
    rec = findings.resolved_records(tmp_path)[fid]
    assert rec["body"].count("## Resolution") == 1
    assert "second note" in rec["body"] and "first note" not in rec["body"]
    assert sum(1 for r in findings.read_ledger(tmp_path) if r.get("id") == fid) == 1
    assert findings.validate_store(tmp_path) == []


# --- Regression tests for audit fixes (2026-07-09, batch 2) ---


def test_migrate_rejects_unrecognized_v1_section(tmp_path):
    # FIX 1: a non-canonical '## ' section outside a finding must not be silently
    # dropped — it raises instead.
    doc = "# X Findings\nGenerated: 2026-04-24\n\n## Resolved\n\nstray text\n"
    src = tmp_path / "security-findings.md"
    src.write_text(doc, encoding="utf-8")
    with pytest.raises(findings.FindingError, match="unrecognized v1 section"):
        findings.migrate_v1(src, tmp_path / "findings")


def test_migrate_preserves_heading_inside_finding_field(tmp_path):
    # FIX 1: '## '/'### ' lines inside a finding are field content, not boundaries.
    doc = """# Security Findings
Generated: 2026-04-24

## Open Findings

### High

#### [N-500] Heading in body
Category: security
Area: src/a.py
Problem: intro
## a heading in the problem prose
### a sub heading too
trailing prose
Evidence: e
Impact: i
Fix: f
"""
    src = tmp_path / "security-findings.md"
    src.write_text(doc, encoding="utf-8")
    root = tmp_path / "findings"
    assert findings.migrate_v1(src, root) == 1
    out = root / "security" / "open" / "N-500.md"
    text = out.read_text(encoding="utf-8")
    assert "a heading in the problem prose" in text
    assert "a sub heading too" in text
    assert "trailing prose" in text
    assert "## Evidence\n\ne" in text
    assert findings.validate_file(out) == []


def test_migrate_v1_is_idempotent(tmp_path):
    # FIX 2: re-running migrate on identical input writes nothing and changes nothing.
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(V1_DOC, encoding="utf-8")
    root = tmp_path / "findings"
    assert findings.migrate_v1(src, root) == 3
    before_files = {p: p.read_text(encoding="utf-8") for p in root.glob("*/open/*.md")}
    before_ledger = findings.ledger_path(root).read_text(encoding="utf-8")
    assert findings.migrate_v1(src, root) == 0
    after_files = {p: p.read_text(encoding="utf-8") for p in root.glob("*/open/*.md")}
    assert before_files == after_files
    assert findings.ledger_path(root).read_text(encoding="utf-8") == before_ledger
    assert findings.validate_store(root) == []


def test_migrate_in_run_duplicate_writes_nothing(tmp_path):
    # FIX 2: a duplicate id within one source aborts before any file is written.
    doc = """# Security Findings
Generated: 2026-04-24

## Open Findings

### High

#### [N-600] first
Category: security
Area: src/a.py
Problem: p
Evidence: e
Impact: i
Fix: f

#### [N-600] duplicate id
Category: security
Area: src/b.py
Problem: p
Evidence: e
Impact: i
Fix: f
"""
    src = tmp_path / "security-findings.md"
    src.write_text(doc, encoding="utf-8")
    root = tmp_path / "findings"
    with pytest.raises(findings.FindingError, match="duplicate id N-600"):
        findings.migrate_v1(src, root)
    assert list(root.glob("*/open/*.md")) == []
    assert not findings.ledger_path(root).exists()


def test_new_finding_leaves_no_tmp_file(tmp_path):
    # FIX 3: atomic write leaves no '.tmp' sibling behind.
    path = _new(tmp_path)
    assert path.exists()
    assert list(tmp_path.glob("**/*.tmp")) == []


def test_index_warns_on_out_of_vocab_ledger_status(tmp_path, capsys):
    # A resolved status with no table column is surfaced on stderr, not dropped.
    path = _new(tmp_path)
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "done", date="2026-07-09")
    lp = findings.ledger_path(tmp_path)
    lp.write_text(
        lp.read_text(encoding="utf-8").replace('"status": "fixed"', '"status": "wontfix"'),
        encoding="utf-8",
    )
    findings.build_index(tmp_path)
    assert "wontfix" in capsys.readouterr().err


# --- resolved-ledger, show, migrate-resolved, and review-hygiene (2026-07-10) ---


def test_show_open_finding_returns_file_verbatim(tmp_path):
    path = _new(tmp_path)
    assert findings.show_finding(tmp_path, path.stem) == path.read_text(encoding="utf-8")


def test_show_unknown_id_raises(tmp_path):
    with pytest.raises(findings.FindingError, match="no finding"):
        findings.show_finding(tmp_path, "security-deadbeef")


def test_list_status_fixed_reads_from_ledger(tmp_path, capsys):
    path = _new(tmp_path)
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "done")
    findings.main(["list", "--root", str(tmp_path), "--status", "fixed"])
    out = capsys.readouterr().out
    assert fid in out and "fixed" in out


def test_validate_flags_malformed_ledger_json(tmp_path):
    _new(tmp_path)  # ensure the store dir exists
    lp = findings.ledger_path(tmp_path)
    lp.write_text('{"id": "audit-00000000"\n', encoding="utf-8")  # missing closing brace
    assert any("invalid JSON" in e for e in findings.validate_store(tmp_path))


def test_validate_flags_bad_ledger_record(tmp_path):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(json.dumps({"id": "audit-00000000", "status": "open"}) + "\n", encoding="utf-8")
    errors = findings.validate_store(tmp_path)
    assert any("status" in e for e in errors)  # 'open' is not a resolved status


def test_migrate_resolved_moves_legacy_files_to_ledger(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    legacy = tmp_path / "security" / "resolved" / f"{fid}.md"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8").replace("status: open", "status: fixed")
    text = text.replace("found: 2026-07-08", "found: 2026-07-08\nresolved: 2026-07-09")
    legacy.write_text(text, encoding="utf-8")
    path.unlink()  # only the legacy resolved file remains
    appended, total = findings.migrate_resolved(tmp_path)
    assert (appended, total) == (1, 1)
    assert not (tmp_path / "security" / "resolved").exists()
    assert findings.resolved_records(tmp_path)[fid]["status"] == "fixed"
    # idempotent: nothing left to migrate
    assert findings.migrate_resolved(tmp_path) == (0, 0)


def test_review_hygiene_warns_without_mark_or_gitignore(tmp_path):
    (tmp_path / ".git").mkdir()
    store = tmp_path / "docs" / "audit" / "findings"
    store.mkdir(parents=True)
    assert findings.check_review_hygiene(store) is not None


def test_review_hygiene_ok_when_gitignored(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("docs/audit/findings/\n", encoding="utf-8")
    store = tmp_path / "docs" / "audit" / "findings"
    store.mkdir(parents=True)
    assert findings.is_store_gitignored(store) is True
    assert findings.check_review_hygiene(store) is None


def test_ensure_store_gitattributes_writes_mark(tmp_path):
    (tmp_path / ".git").mkdir()
    store = tmp_path / "docs" / "audit" / "findings"
    store.mkdir(parents=True)
    findings.ensure_store_gitattributes(store)
    ga = store / ".gitattributes"
    assert ga.exists() and "linguist-generated" in ga.read_text(encoding="utf-8")
    assert findings.check_review_hygiene(store) is None


def test_ensure_store_gitattributes_skips_when_gitignored(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".gitignore").write_text("docs/audit/\n", encoding="utf-8")
    store = tmp_path / "docs" / "audit" / "findings"
    store.mkdir(parents=True)
    findings.ensure_store_gitattributes(store)
    assert not (store / ".gitattributes").exists()


# ── ledger durability: resolve deletes the open file on the strength of the
#    ledger write, so every way that write can silently not-happen is a test ───


def test_append_ledger_refuses_truncated_last_line(tmp_path):
    """A newline-less last line would merge two records into one unparseable line."""
    _new(tmp_path)
    ledger = findings.ledger_path(tmp_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"id": "x"}', encoding="utf-8")  # no trailing newline
    with pytest.raises(findings.FindingError, match="truncated"):
        findings.append_ledger(tmp_path, {"id": "y"})


def test_append_ledger_raises_on_short_write(tmp_path, monkeypatch):
    """A short write commits half a record; resolve would then delete a live finding."""
    real_write = findings.os.write
    monkeypatch.setattr(findings.os, "write", lambda fd, data: real_write(fd, data[:5]))
    with pytest.raises(findings.FindingError, match="short write"):
        findings.append_ledger(tmp_path, {"id": "y"})


def test_resolve_leaves_no_orphan_when_ledger_append_refuses(tmp_path):
    """The open file must survive a refused append — that is the whole point."""
    path = _new(tmp_path)
    fid = findings.parse_frontmatter(path.read_text(encoding="utf-8"))[0]["id"]
    ledger = findings.ledger_path(tmp_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"id": "x"}', encoding="utf-8")
    with pytest.raises(findings.FindingError):
        findings.resolve_finding(tmp_path, fid, "fixed", "done")
    assert path.exists(), "open finding deleted despite the ledger append failing"


# ── INDEX.md freshness: `make check` and CI both fail on a stale index ────────


@pytest.mark.parametrize("mutation", ["new", "resolve"])
def test_cli_mutation_leaves_index_fresh(tmp_path, mutation):
    """Regenerating after a CLI mutation must be a no-op, or index-check goes red."""
    findings.main(
        [
            "new",
            "--root",
            str(tmp_path),
            "--auditor",
            "security",
            "--severity",
            "high",
            "--category",
            "security",
            "--area",
            "src/auth.py",
            "--body",
            BODY,
            "Token compared with ==",
        ]
    )
    if mutation == "resolve":
        fid = findings.finding_id("security", "src/auth.py", "Token compared with ==")
        findings.main(
            ["resolve", "--root", str(tmp_path), fid, "--status", "fixed", "--notes", "d"]
        )
    after_mutation = (tmp_path / "INDEX.md").read_text(encoding="utf-8")
    findings.write_index(tmp_path)
    assert (tmp_path / "INDEX.md").read_text(encoding="utf-8") == after_mutation


def test_read_baseline_reports_corruption_instead_of_masking_it(tmp_path):
    """A damaged baseline must be distinguishable from an empty one."""
    _new(tmp_path)
    findings.baseline_path(tmp_path).write_text("{not json", encoding="utf-8")
    errors: list[str] = []
    assert findings.read_baseline(tmp_path, errors) == set()
    assert errors and "unreadable baseline" in errors[0]

    findings.baseline_path(tmp_path).write_text('{"accepted": []}', encoding="utf-8")
    errors = []
    assert findings.read_baseline(tmp_path, errors) == set()
    assert errors and "no 'ids' list" in errors[0]


def test_secrets_never_reach_the_written_finding(tmp_path):
    """The redaction convention is enforced at the writer, not by instruction."""
    token = "ghp_" + "A" * 30
    path = _new(
        tmp_path,
        title="Token leak",
        body=BODY.replace("Timing side-channel.", f"Found {token} for alice@example.com"),
    )
    written = path.read_text(encoding="utf-8")
    assert token not in written
    assert "ghp_***AAAA" in written
    assert "alice@example.com" not in written and "<email>" in written


def test_resolve_notes_are_redacted_before_the_append_only_ledger(tmp_path):
    path = _new(tmp_path)
    fid = findings.parse_frontmatter(path.read_text(encoding="utf-8"))[0]["id"]
    findings.resolve_finding(tmp_path, fid, "fixed", "rotated AKIAIOSFODNN7EXAMPLE")
    ledger = findings.ledger_path(tmp_path).read_text(encoding="utf-8")
    assert "AKIAIOSFODNN7EXAMPLE" not in ledger
    assert "AKIA***MPLE" in ledger


def test_redact_leaves_ordinary_prose_untouched():
    """A redactor that mangles normal evidence is worse than none."""
    prose = "`src/auth.py:42` uses `token == expected` — see RFC 6749 section 4.1."
    assert findings.redact(prose) == prose


def test_parse_frontmatter_ignores_indented_keys():
    """Indented lines are nested values; check-rules-anatomy's parser agrees."""
    fm, _ = findings.parse_frontmatter("---\n  indented: v\n---\nbody")
    assert fm == {}
    fm, _ = findings.parse_frontmatter("---\nname: v\n---\nbody")
    assert fm == {"name": "v"}
