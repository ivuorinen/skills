"""Tests for skills/nitpicker/scripts/findings.py — the per-finding audit store CLI."""

import importlib.util
import json
import os
import re
import runpy
import stat
import sys
from pathlib import Path
from typing import ClassVar

import pytest

_TOOL = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "findings.py"
_spec = importlib.util.spec_from_file_location("findings", _TOOL)
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


class TestWriteLedgerTempFile:
    """`write_ledger` renames its temp file over the ledger, so the temp file's
    own properties become the ledger's. Three ways that went wrong, each measured
    before it was fixed and each pinned here."""

    RECORD: ClassVar[dict] = {
        "id": "audit-00000001",
        "auditor": "audit",
        "severity": "low",
        "category": "docs",
        "area": "x",
        "title": "t",
        "status": "fixed",
        "found": "2026-01-01",
        "resolved": "2026-01-01",
        "body": "b",
    }

    @staticmethod
    def _prepared(tmp_path):
        """A store root whose ledger directory exists, plus the ledger path."""
        p = findings.ledger_path(tmp_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def test_a_stale_wide_mode_temp_file_does_not_widen_the_ledger(self, tmp_path):
        """A mode argument applies only when `os.open` *creates* the file.

        With O_CREAT|O_TRUNC and no O_EXCL, a stale temp file left by a crashed
        run kept its own mode and `replace` carried it onto the ledger —
        measured at 0o666, silently undoing the 0o600 the append path sets.
        """
        p = self._prepared(tmp_path)
        stale = p.with_name(f"{p.name}.{os.getpid()}.tmp")
        stale.write_text("", encoding="utf-8")
        stale.chmod(0o666)

        findings.write_ledger(tmp_path, [self.RECORD])
        assert stat.S_IMODE(p.stat().st_mode) == 0o600

    def test_a_symlinked_temp_path_is_not_followed(self, tmp_path):
        """O_CREAT|O_TRUNC follows a symlink and truncates its target.

        Anyone able to pre-create the temp name in the store directory therefore
        had an arbitrary-file write: the victim was measured overwritten with
        ledger content. mkstemp's O_EXCL refuses to follow one.
        """
        p = self._prepared(tmp_path)
        victim = tmp_path / "VICTIM.txt"
        victim.write_text("IMPORTANT DATA\n", encoding="utf-8")
        p.with_name(f"{p.name}.{os.getpid()}.tmp").symlink_to(victim)

        findings.write_ledger(tmp_path, [self.RECORD])
        assert victim.read_text(encoding="utf-8") == "IMPORTANT DATA\n"
        assert p.exists()

    def test_a_failed_write_leaves_no_temp_file_behind(self, tmp_path, monkeypatch):
        """mkstemp names are random, so nothing would ever clean one up.

        The PID-derived name it replaced was at least predictable enough for a
        later run to overwrite; an abandoned random one accumulates forever.
        """
        p = self._prepared(tmp_path)

        def _boom(_record):
            """Simulate a serialization failure partway through the write."""
            raise RuntimeError("serialization failed")

        monkeypatch.setattr(findings, "_ledger_line", _boom)
        with pytest.raises(RuntimeError, match="serialization failed"):
            findings.write_ledger(tmp_path, [self.RECORD])

        assert list(p.parent.glob("*.tmp")) == []
        assert not p.exists()


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
    with pytest.raises(findings.FindingError, match="no open finding with id security-deadbeef"):
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


def test_new_whitespace_padded_title_refiles_idempotently(tmp_path):
    # A title with surrounding whitespace is stripped before hashing and before
    # writing, so re-filing the identical finding hits the "already exists"
    # branch, not a false "different finding" collision.
    _new(tmp_path, title="Padded title ")
    with pytest.raises(findings.FindingError, match="already exists"):
        _new(tmp_path, title="Padded title ")


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


def test_new_finding_runs_inside_store_lock(tmp_path, monkeypatch):
    entered = []
    orig = findings.store_lock
    monkeypatch.setattr(findings, "store_lock", lambda root: entered.append(root) or orig(root))
    _new(tmp_path)
    assert entered, "new_finding must acquire store_lock"


def test_resolve_finding_runs_inside_store_lock(tmp_path, monkeypatch):
    path = _new(tmp_path)
    entered = []
    orig = findings.store_lock
    monkeypatch.setattr(findings, "store_lock", lambda root: entered.append(root) or orig(root))
    findings.resolve_finding(tmp_path, path.stem, "fixed", "done")
    assert entered, "resolve_finding must acquire store_lock"


def test_resolve_force_refuses_to_drop_unparseable_ledger_line(tmp_path):
    path = _new(tmp_path)
    fid = path.stem
    findings.resolve_finding(tmp_path, fid, "fixed", "done")
    ledger = findings.ledger_path(tmp_path)
    ledger.write_text(ledger.read_text(encoding="utf-8") + "{ not json\n", encoding="utf-8")
    with pytest.raises(findings.FindingError, match="would be lost"):
        findings.resolve_finding(tmp_path, fid, "invalid", "again", force=True)


def test_new_force_refuses_reopen_when_ledger_unparseable_and_writes_no_open_file(tmp_path):
    # Re-opening a resolved finding must fail BEFORE the open file is written when
    # the ledger has a corrupt line, so the store is never left both-open-and-
    # resolved (a both-state validate would flag).
    args = dict(
        auditor="security",
        severity="high",
        category="security",
        area="src/auth.py",
        title="Token compared with ==",
        body=BODY,
        found="2026-07-08",
    )
    fid = findings.new_finding(tmp_path, **args).stem
    findings.resolve_finding(tmp_path, fid, "fixed", "done")  # id now in ledger, open file gone
    ledger = findings.ledger_path(tmp_path)
    ledger.write_text(ledger.read_text(encoding="utf-8") + "{ not json\n", encoding="utf-8")
    with pytest.raises(findings.FindingError, match="unparseable"):
        findings.new_finding(tmp_path, force=True, **args)
    assert not (tmp_path / "security" / "open" / f"{fid}.md").exists()


def test_validate_flags_duplicate_ledger_id(tmp_path):
    path = _new(tmp_path)
    findings.resolve_finding(tmp_path, path.stem, "fixed", "done")
    ledger = findings.ledger_path(tmp_path)
    line = ledger.read_text(encoding="utf-8").strip()
    ledger.write_text(line + "\n" + line + "\n", encoding="utf-8")
    assert any("duplicate ledger id" in e for e in findings.validate_store(tmp_path))


def test_migrate_resolved_same_run_duplicate_id_conflicts(tmp_path):
    # Two legacy files share a hand-assigned id but differ in content: this must be a
    # conflict, not a silent shadow that appends both and deletes both sources.
    base = _new(tmp_path)
    text = base.read_text(encoding="utf-8").replace("status: open", "status: fixed")
    text = text.replace("found: 2026-07-08", "found: 2026-07-08\nresolved: 2026-07-09")
    text = re.sub(r"^id: .*$", "id: DUP-1", text, count=1, flags=re.M)
    base.unlink()
    for auditor, title in (("security", "First finding"), ("arch", "Second finding")):
        d = tmp_path / auditor / "resolved"
        d.mkdir(parents=True, exist_ok=True)
        (d / "DUP-1.md").write_text(
            re.sub(r"^# .*$", f"# {title}", text, count=1, flags=re.M), encoding="utf-8"
        )
    with pytest.raises(findings.FindingError, match="different content"):
        findings.migrate_resolved(tmp_path)


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


def test_ensure_store_gitignore_augments_existing_without_clobbering(tmp_path):
    (tmp_path / ".git").mkdir()
    store = tmp_path / "docs" / "audit" / "findings"
    store.mkdir(parents=True)
    (store / ".gitignore").write_text("custom-artifact/\n", encoding="utf-8")
    findings.ensure_store_gitattributes(store)
    lines = (store / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "custom-artifact/" in lines  # pre-existing rule preserved
    assert ".lock" in lines and "*.tmp" in lines  # managed patterns appended


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


def test_append_ledger_creates_the_ledger_private(tmp_path):
    """0o600, because the ledger quotes evidence out of the audited repository.

    Pinned separately from the write_ledger temp-file check: that one covers the
    mkstemp path, so a mutation of this `os.open` mode passed the whole file
    green. Line coverage cannot catch it — the line runs either way.
    """
    findings.append_ledger(tmp_path, {"id": "y"})
    assert stat.S_IMODE(findings.ledger_path(tmp_path).stat().st_mode) == 0o600


def test_write_ledger_survives_a_filesystem_without_directory_fsync(tmp_path, monkeypatch):
    """Not every filesystem commits a rename this way; a rewrite must not fail.

    The directory fsync makes the rename durable where it is supported. Where it
    is not, the write is still correct — losing it is not worth failing on.
    """
    real_fsync = findings.os.fsync

    def _fsync(fd):
        if stat.S_ISDIR(findings.os.fstat(fd).st_mode):
            raise OSError("directory fsync unsupported")
        return real_fsync(fd)

    monkeypatch.setattr(findings.os, "fsync", _fsync)
    findings.write_ledger(tmp_path, [{"id": "a"}])
    assert findings.read_ledger(tmp_path) == [{"id": "a"}]


def test_append_ledger_narrows_an_existing_permissive_ledger(tmp_path):
    """A mode argument binds only on creation, so an inherited 0o644 survived.

    A store created before the 0o600 rule, or one a umask widened, kept a
    world-readable ledger and every later append added evidence to it.
    """
    ledger = findings.ledger_path(tmp_path)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text('{"id": "x"}\n', encoding="utf-8")
    ledger.chmod(0o644)

    findings.append_ledger(tmp_path, {"id": "y"})

    assert stat.S_IMODE(ledger.stat().st_mode) == 0o600


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
    # match=: the append must be refused for the truncated last line, not for some
    # other FindingError that would leave the same open file in place.
    with pytest.raises(findings.FindingError, match="last line"):
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


def test_resolve_redacts_a_body_new_finding_never_wrote(tmp_path):
    """redact() must cover copying, not just authoring.

    An open finding file can reach the store without passing new_finding — a
    hand-written file, a v1 migration. resolve then copies its body into the
    append-only ledger AND deletes the open file, so an unredacted copy is
    permanent and the redactable original is gone.
    """
    open_dir = tmp_path / "audit" / "open"
    open_dir.mkdir(parents=True)
    (open_dir / "audit-deadbeef.md").write_text(
        "---\nid: audit-deadbeef\nauditor: audit\nseverity: high\ncategory: security\n"
        "area: src/x.py\nstatus: open\nfound: 2026-07-08\n---\n\n"
        "# Hardcoded token\n\n## Problem\nInline.\n\n"
        '## Evidence\n`TOKEN = "AKIAIOSFODNN7EXAMPLE"`, owner <alice@example.com>\n\n'
        "## Impact\nLeak.\n\n## Fix\nUse env var.\n",
        encoding="utf-8",
    )
    findings.resolve_finding(tmp_path, "audit-deadbeef", "fixed", "moved to env")

    ledger = findings.ledger_path(tmp_path).read_text(encoding="utf-8")
    assert "AKIAIOSFODNN7EXAMPLE" not in ledger
    assert "AKIA***MPLE" in ledger
    assert "alice@example.com" not in ledger
    assert "<email>" in ledger
    assert not (open_dir / "audit-deadbeef.md").exists()  # the unredacted copy is gone


def test_migrate_v1_redacts_the_open_findings_it_writes(tmp_path):
    """A v1 document is untrusted text this tool did not author."""
    src = tmp_path / "security-findings.md"
    src.write_text(
        "Generated: 2026-07-08\n\n## Open findings\n\n### High\n\n"
        "#### [N-001] Hardcoded key\n"
        "Category: security\n"
        "Area: src/x.py\n"
        "Problem: Inline.\n"
        'Evidence: `KEY = "AKIAIOSFODNN7EXAMPLE"` owned by <bob@example.com>\n'
        "Impact: Leak.\n"
        "Fix: Env var.\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    assert findings.migrate_v1(src, store) == 1
    written = (store / "security" / "open" / "N-001.md").read_text(encoding="utf-8")
    assert "AKIAIOSFODNN7EXAMPLE" not in written
    assert "AKIA***MPLE" in written
    assert "bob@example.com" not in written


def test_migrate_v1_redacts_the_resolved_records_it_appends(tmp_path):
    """_build_v1's resolved branch builds its ledger record directly and
    migrate_v1 appends it as-is, so it never passes _record_from_finding's
    redaction. The v1 `Notes:` field is untrusted text, and the ledger is
    append-only — an unredacted secret landing there is permanent.
    """
    src = tmp_path / "security-findings.md"
    src.write_text(
        "Generated: 2026-07-08\n\n## Fixed\n\n### Pass 1 — 2026-07-09\n\n"
        "#### [N-002] Rotated the leaked deploy key\n"
        "Fixed: 2026-07-09\n"
        "Notes: old key AKIAIOSFODNN7EXAMPLE revoked; owner <carol@example.com> notified\n",
        encoding="utf-8",
    )
    store = tmp_path / "store"
    assert findings.migrate_v1(src, store) == 1

    ledger = findings.ledger_path(store).read_text(encoding="utf-8")
    assert "AKIAIOSFODNN7EXAMPLE" not in ledger
    assert "AKIA***MPLE" in ledger
    assert "carol@example.com" not in ledger
    assert "<email>" in ledger


class TestRedactVendorCoverage:
    """The register for `_SECRET_RE`. Add a vendor here and in findings.py together.

    A credential shape the repo tells users to configure but cannot redact is a
    silent gap: the ledger is append-only, so a secret that reaches it is
    permanent, and the store's linguist-generated mark collapses these files in
    PR review — removing the human check that would otherwise catch it. Pinning
    one correctly-shaped token per vendor turns the next gap into a red test.
    """

    # (label, token) — shape-accurate, not real credentials.
    #
    # Fixtures that look like credentials trip the repo's own scanners, and the
    # right answer is to keep the scanners strict rather than allowlist this
    # file: the JWT is joined from its three segments so the contiguous
    # `eyJ…​.eyJ…​.` shape never appears in the source for gitleaks to match, and
    # TestRedactPrivateKeys assembles its PEM markers for detect-private-key for
    # the same reason. Anything added here must clear both.
    VENDORS: ClassVar[list[tuple[str, str]]] = [
        ("github classic", "ghp_" + "A" * 36),
        ("github fine-grained", "github_pat_" + "A" * 22 + "_" + "B" * 59),
        ("gitlab pat", "glpat-" + "A" * 20),
        ("gitlab runner modern", "glrt-" + "A" * 20),
        ("gitlab runner legacy", "GR1348941" + "A" * 20),
        ("bitbucket app password", "ATBB" + "A" * 28),
        # BITBUCKET_TOKEN holds an Atlassian API/scoped token, not an app
        # password — the ATBB prefix above never covered the variable the docs
        # actually tell users to set.
        ("atlassian api token", "ATATT" + "A" * 180),
        ("atlassian scoped token", "ATCTT" + "A" * 180),
        ("openai", "sk-" + "A" * 40),
        ("aws key id", "AKIA" + "B" * 16),
        ("google api key", "AIza" + "A" * 35),
        ("npm token", "npm_" + "A" * 36),
        ("slack", "xoxb-1234567890-abcdefghij"),
        ("jwt", ".".join(["eyJ" + "h" * 18, "eyJ" + "z" * 18, "s" * 12])),
    ]

    @pytest.mark.parametrize("label, token", VENDORS, ids=[v[0] for v in VENDORS])
    def test_vendor_token_never_survives_redaction(self, label, token):
        assert token not in findings.redact(f"found in config: {token}"), label

    @pytest.mark.parametrize("label, token", VENDORS, ids=[v[0] for v in VENDORS])
    def test_vendor_token_redacted_on_every_write_path(self, label, token, tmp_path):
        # Not just the function — the store writer that actually persists it.
        path = findings.new_finding(
            tmp_path,
            auditor="audit",
            severity="low",
            category="security",
            area="cfg.env",
            title="leaked",
            body=f"## Problem\n{token}\n\n## Evidence\ne\n\n## Impact\ni\n\n## Fix\nf\n",
        )
        assert token not in path.read_text(encoding="utf-8"), label

    def test_documented_env_vars_all_have_a_vendor_entry(self):
        """The repo must not document a credential it cannot redact.

        `cr.md` names the variables a user is told to set; every platform named
        there needs a shape in the register above.
        """
        covered = " ".join(label for label, _ in self.VENDORS)
        for platform in ("github", "gitlab", "bitbucket"):
            assert platform in covered, f"{platform} credentials are documented but unregistered"


class TestRedactPrivateKeys:
    """PEM markers are assembled at runtime, never written as literals.

    pre-commit's `detect private key` hook scans this file too, and a real-looking
    header in the source fails the commit — so the fixtures build the marker from
    parts. Verified by watching that hook fail on the literal form first.
    """

    _BODY = "MIIEpAIBAAKCAQEA" + "x" * 60
    _D = "-" * 5

    def _pem(self, kind: str, body: str = "", closed: bool = True) -> str:
        head = f"{self._D}BEGIN {kind} PRIVATE KEY{self._D}"
        return (
            f"{head}\n{body}\n{self._D}END {kind} PRIVATE KEY{self._D}"
            if closed
            else f"{head}\n{body}"
        )

    def test_whole_pem_block_is_removed_not_just_the_header(self):
        # Masking the header alone would leave the key material in the record
        # while reading as redacted — worse than no redaction.
        out = findings.redact(f"key was committed:\n{self._pem('RSA', self._BODY)}\n")
        assert self._BODY not in out
        assert "BEGIN RSA" not in out and "END RSA" not in out
        assert "[REDACTED PRIVATE KEY]" in out

    def test_truncated_pem_keeps_no_short_trailing_line(self):
        """A real PEM's last line is a short base64 remainder.

        The first fix required 16+ characters per run, so `CC==` survived and the
        output read as redacted while still carrying key material. A narrowly
        wrapped body would have survived in full.
        """
        body = "A" * 64 + "\n" + "B" * 64 + "\nCC=="
        out = findings.redact(self._pem("RSA", body, closed=False))
        assert "A" * 64 not in out
        assert "CC==" not in out

    def test_truncated_pem_stops_at_the_first_non_base64_line(self):
        # The line-shaped match is what keeps ordinary evidence out; without it a
        # lower length floor would swallow the prose after the key.
        text = self._pem("RSA", "A" * 64, closed=False) + "\nfound at src/app.py:42"
        out = findings.redact(text)
        assert "found at src/app.py:42" in out
        assert "A" * 64 not in out

    def test_truncated_pem_without_an_end_marker_takes_the_body_too(self):
        """Evidence is often clipped, and the clipped case is the dangerous one.

        Matching the header alone replaced it with the redaction marker and left
        the base64 body on the following line — output that reads as redacted
        while still carrying the key. Caught by this test, not by review.
        """
        out = findings.redact(self._pem("OPENSSH", self._BODY, closed=False))
        assert "BEGIN OPENSSH" not in out
        assert self._BODY not in out

    def test_pem_is_unreachable_from_the_word_boundary_pattern(self):
        """Why _PEM_RE exists at all: `_SECRET_RE` opens with `\\b`, which cannot
        match before a leading `-`, so a PEM block can never match inside it."""
        assert findings._SECRET_RE.search(self._pem("RSA", closed=False)) is None


def test_redact_leaves_a_bare_aws_secret_alone_by_design():
    """A 40-char unprefixed base64 blob is indistinguishable from a hash or diff
    noise, so it is deliberately not matched. Pinned so the omission stays a
    recorded decision rather than being 'fixed' into a false-positive machine."""
    blob = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    assert findings.redact(blob) == blob


def test_every_store_writer_redacts(tmp_path):
    """Guards the invariant rather than one call site.

    _record_from_finding is not the only funnel — _build_v1 writes both its open
    and resolved records directly. A new writer that skips redact() is the exact
    defect this pins, so assert the property end to end on both migrate paths
    and on resolve, not the presence of a call.
    """
    secret = "AKIAIOSFODNN7EXAMPLE"

    # resolve: body copied from an open file this tool did not author
    a = tmp_path / "a"
    (a / "audit" / "open").mkdir(parents=True)
    (a / "audit" / "open" / "audit-deadbeef.md").write_text(
        "---\nid: audit-deadbeef\nauditor: audit\nseverity: low\ncategory: security\n"
        f"area: x\nstatus: open\nfound: 2026-07-08\n---\n\n# T\n\n## Problem\n{secret}\n\n"
        "## Evidence\ne\n\n## Impact\ni\n\n## Fix\nf\n",
        encoding="utf-8",
    )
    findings.resolve_finding(a, "audit-deadbeef", "fixed", "n")

    # migrate-resolved: legacy resolved/*.md folded into the ledger
    b = tmp_path / "b"
    (b / "audit" / "resolved").mkdir(parents=True)
    (b / "audit" / "resolved" / "N-003.md").write_text(
        "---\nid: N-003\nauditor: audit\nstatus: fixed\nfound: 2026-07-08\n"
        f"resolved: 2026-07-09\n---\n\n# T\n\n## Resolution\n{secret}\n",
        encoding="utf-8",
    )
    findings.migrate_resolved(b)

    for root in (a, b):
        text = findings.ledger_path(root).read_text(encoding="utf-8")
        assert secret not in text, f"{root.name}: unredacted secret reached the ledger"
        assert "AKIA***MPLE" in text


def test_list_severity_rejects_out_of_vocab(tmp_path, capsys):
    """A typo must fail loudly, not filter everything out and exit 0.

    gather_findings filters on exact equality, so an unconstrained bad value can
    only match zero rows — and an empty list reads as a clean store to any gate
    that consumes the output.
    """
    with pytest.raises(SystemExit) as exc:
        findings.main(["list", "--root", str(tmp_path), "--severity", "hgih"])
    assert exc.value.code == 2
    assert "hgih" in capsys.readouterr().err
    # the correct spelling still works
    assert findings.main(["list", "--root", str(tmp_path), "--severity", "high"]) == 0


# --- validate_file / validate_ledger_record reject branches (tests-ecd0ec10) ---
#
# These are the integrity gate `make check` and CI run. Every reject branch gets
# a case that fails if the branch is deleted — the suite previously exercised
# only four of them.

GOOD_FM = {
    "id": "security-aabbccdd",
    "auditor": "security",
    "severity": "high",
    "category": "security",
    "area": "src/auth.py",
    "status": "open",
    "found": "2026-07-08",
}


def _render(fm: dict, title: str = "T", body: str = BODY) -> str:
    front = "\n".join(f"{k}: {v}" for k, v in fm.items())
    heading = f"# {title}\n\n" if title else ""
    return f"---\n{front}\n---\n\n{heading}{body}"


def _write_finding(root: Path, fm: dict, *, state: str = "open", title: str = "T") -> Path:
    path = root / fm.get("auditor", "security") / state / f"{fm.get('id', 'security-aabbccdd')}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(fm, title), encoding="utf-8")
    return path


def _drop(*keys: str) -> dict:
    return {k: v for k, v in GOOD_FM.items() if k not in keys}


def test_validate_file_accepts_the_baseline_fixture(tmp_path):
    """Guards the table below: every mutation must be the only reason it fails."""
    assert findings.validate_file(_write_finding(tmp_path, dict(GOOD_FM))) == []


@pytest.mark.parametrize(
    ("fm", "state", "title", "expected"),
    [
        (_drop("id"), "open", "T", "missing id"),
        ({**GOOD_FM, "id": "notahash"}, "open", "T", "malformed id"),
        (_drop("auditor"), "open", "T", "missing auditor"),
        (_drop("status"), "open", "T", "missing status"),
        (_drop("found"), "open", "T", "missing found"),
        ({**GOOD_FM, "status": "opne"}, "open", "T", "invalid status 'opne'"),
        ({**GOOD_FM, "category": "banana"}, "open", "T", "invalid category 'banana'"),
        ({**GOOD_FM, "status": "fixed"}, "open", "T", "file in open/ but status is 'fixed'"),
        ({**GOOD_FM, "status": "open"}, "resolved", "T", "file in resolved/ but status is 'open'"),
        (dict(GOOD_FM), "archive", "T", "file not under open/ or resolved/"),
        (_drop("severity"), "open", "T", "missing severity"),
        (_drop("category"), "open", "T", "missing category"),
        (_drop("area"), "open", "T", "missing area"),
        (
            {**_drop("severity", "category", "area"), "status": "fixed"},
            "resolved",
            "T",
            "resolved finding missing resolved date",
        ),
        (
            {**_drop("severity", "category", "area"), "status": "fixed", "resolved": "07/09/2026"},
            "resolved",
            "T",
            "invalid resolved date",
        ),
        (dict(GOOD_FM), "open", "", "missing '# <title>' heading"),
    ],
)
def test_validate_file_rejects_each_malformed_field(tmp_path, fm, state, title, expected):
    path = _write_finding(tmp_path, fm, state=state, title=title)
    assert any(expected in e for e in findings.validate_file(path)), findings.validate_file(path)


def test_validate_file_rejects_auditor_directory_mismatch(tmp_path):
    # The file lives under security/, but claims auditor: tests.
    path = tmp_path / "security" / "open" / "security-aabbccdd.md"
    path.parent.mkdir(parents=True)
    path.write_text(_render({**GOOD_FM, "auditor": "tests"}), encoding="utf-8")
    assert any("does not match directory" in e for e in findings.validate_file(path))


def test_validate_file_reports_unreadable_path(tmp_path):
    # A directory named like a finding: read_text raises IsADirectoryError (an OSError).
    d = tmp_path / "security" / "open" / "security-aabbccdd.md"
    d.mkdir(parents=True)
    errors = findings.validate_file(d)
    assert len(errors) == 1
    assert "cannot read" in errors[0]


def test_validate_file_reports_missing_frontmatter(tmp_path):
    path = tmp_path / "security" / "open" / "security-aabbccdd.md"
    path.parent.mkdir(parents=True)
    path.write_text("# T\n\nno frontmatter here\n", encoding="utf-8")
    assert findings.validate_file(path) == [f"{path}: missing frontmatter"]


GOOD_REC = {
    "id": "security-aabbccdd",
    "auditor": "security",
    "status": "fixed",
    "found": "2026-07-08",
    "resolved": "2026-07-09",
    "title": "T",
    "severity": "high",
    "category": "security",
}


def test_validate_ledger_record_accepts_the_baseline_fixture():
    assert findings.validate_ledger_record(dict(GOOD_REC), Path("resolved.jsonl"), 1) == []


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ({"id": ""}, "missing id"),
        ({"id": "notahash"}, "malformed id"),
        ({"status": "open"}, "resolved status must be fixed|invalid"),
        ({"auditor": ""}, "missing auditor"),
        ({"found": ""}, "missing found"),
        ({"resolved": ""}, "missing resolved"),
        ({"title": ""}, "missing title"),
        ({"found": "08-07-2026"}, "invalid found date"),
        ({"resolved": "yesterday"}, "invalid resolved date"),
        ({"severity": "enormous"}, "invalid severity"),
        ({"category": "banana"}, "invalid category"),
        ({"auditor": "Not An Auditor"}, "invalid auditor"),
    ],
)
def test_validate_ledger_record_rejects_each_malformed_field(mutation, expected):
    rec = {**GOOD_REC, **mutation}
    errors = findings.validate_ledger_record(rec, Path("resolved.jsonl"), 7)
    assert any(expected in e for e in errors), errors
    assert all(e.startswith("resolved.jsonl:7: ") for e in errors)


# --- store hygiene helpers and ledger-read guards (tests-47aa18b9) ---


def test_render_finding_rejects_a_quoted_frontmatter_value():
    """A pre-quoted value would not round-trip through parse_frontmatter, so the
    stored area would differ from the one that produced the content-hashed id."""
    with pytest.raises(findings.FindingError, match="must not be wrapped in quotes"):
        findings.render_finding({**GOOD_FM, "area": '"src/auth.py"'}, "T", BODY)


def test_read_ledger_reports_an_unreadable_ledger(tmp_path):
    findings.ledger_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    findings.ledger_path(tmp_path).mkdir()  # a directory where the file belongs
    errors: list[str] = []
    assert findings.read_ledger(tmp_path, errors) == []
    assert any("cannot read" in e for e in errors)


def test_read_ledger_skips_blanks_and_flags_non_object_lines(tmp_path):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(f"\n  \n{json.dumps(GOOD_REC)}\n[1, 2]\n", encoding="utf-8")
    errors: list[str] = []
    recs = findings.read_ledger(tmp_path, errors)
    assert [r["id"] for r in recs] == [GOOD_REC["id"]]
    assert any("not a JSON object" in e for e in errors)


def test_resolved_records_tolerates_blank_bad_and_scalar_lines(tmp_path):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(f"\nnot json\n42\n{json.dumps(GOOD_REC)}\n", encoding="utf-8")
    assert list(findings.resolved_records(tmp_path)) == [GOOD_REC["id"]]


def test_resolved_records_returns_empty_on_an_unreadable_ledger(tmp_path):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.mkdir()
    assert findings.resolved_records(tmp_path) == {}


def test_ledger_summary_skips_junk_lines(tmp_path):
    """INDEX.md is generated from this streaming read; a junk line must be skipped,
    not crash the regeneration `make check` depends on."""
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(f"\nnot json\n[1]\n{json.dumps(GOOD_REC)}\n", encoding="utf-8")
    assert findings._ledger_summary(tmp_path) == {GOOD_REC["id"]: ("security", "fixed")}


def test_ledger_reads_skip_records_with_no_id(tmp_path):
    """An id-less record cannot be keyed; both readers must drop it rather than
    index it under None and shadow a real finding."""
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    idless = {k: v for k, v in GOOD_REC.items() if k != "id"}
    lp.write_text(f"{json.dumps(idless)}\n{json.dumps(GOOD_REC)}\n", encoding="utf-8")
    assert list(findings.resolved_records(tmp_path)) == [GOOD_REC["id"]]
    assert list(findings._ledger_summary(tmp_path)) == [GOOD_REC["id"]]


def test_validate_store_does_not_track_id_less_ledger_records_as_duplicates(tmp_path):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    idless = {k: v for k, v in GOOD_REC.items() if k != "id"}
    lp.write_text(f"{json.dumps(idless)}\n{json.dumps(idless)}\n", encoding="utf-8")
    errors = findings.validate_store(tmp_path)
    assert any("missing id" in e for e in errors)
    assert not any("duplicate ledger id" in e for e in errors)


@pytest.mark.parametrize("notes", ["", "   \n  "])
def test_resolve_with_blank_notes_appends_no_resolution_section(tmp_path, notes):
    """The ledger is append-only, so a blank `## Resolution` heading written by a
    regression here is permanent."""
    _new(tmp_path)
    fid = findings.finding_id("security", "src/auth.py", "Token compared with ==")
    findings.resolve_finding(tmp_path, fid, "fixed", notes, date="2026-07-09")
    body = findings.resolved_records(tmp_path)[fid]["body"]
    assert "## Resolution" not in body
    assert "## Problem" in body  # the original body survived intact


def test_force_reresolve_with_blank_notes_leaves_the_recorded_body_alone(tmp_path):
    _new(tmp_path)
    fid = findings.finding_id("security", "src/auth.py", "Token compared with ==")
    findings.resolve_finding(tmp_path, fid, "fixed", "first pass", date="2026-07-09")
    findings.resolve_finding(tmp_path, fid, "invalid", "", date="2026-07-10", force=True)
    rec = findings.resolved_records(tmp_path)[fid]
    assert rec["status"] == "invalid"
    assert rec["body"].count("## Resolution") == 1  # the original note, not a second empty one
    assert "first pass" in rec["body"]


def test_validate_accepts_a_resolved_file_with_a_well_formed_date(tmp_path):
    """The valid-date arm: previously only the missing and malformed dates were
    exercised, so a regression accepting nothing would still have passed."""
    fm = {**_drop("severity", "category", "area"), "status": "fixed", "resolved": "2026-07-09"}
    path = _write_finding(tmp_path, fm, state="resolved")
    assert findings.validate_file(path) == []


def test_migrate_v1_keeps_a_fenced_block_that_precedes_any_field(tmp_path):
    """A fence opening before the first `Field:` line has no open field to append
    to — the parser must not crash or mis-attribute it."""
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(
        "# Nitpicker Findings\n"
        "Generated: 2026-04-24\n\n"
        "```text\n"
        "preamble fence, no finding is open yet\n"
        "```\n\n"
        "## Open Findings\n\n"
        "### Advisory\n\n"
        "#### [N-500] A finding\n"
        "Prose before any field line.\n"
        "Category: security\n"
        "Area: src/x.py\n"
        "Problem: p\n"
        "Evidence: e\n"
        "Impact: i\n"
        "Fix: f\n",
        encoding="utf-8",
    )
    root = tmp_path / "findings"
    assert findings.migrate_v1(src, root) == 1
    text = (root / "audit" / "open" / "N-500.md").read_text(encoding="utf-8")
    assert "preamble fence" not in text  # not attributed to the finding
    assert findings.validate_store(root) == []


def test_ledger_summary_returns_empty_on_an_unreadable_ledger(tmp_path, capsys):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.mkdir()
    assert findings._ledger_summary(tmp_path) == {}
    assert "cannot read" in capsys.readouterr().err


def test_pattern_covers_ignores_a_wildcard_only_pattern():
    # `**` collapses to an empty base — treating that as a match would report every
    # store as gitignored.
    assert findings._pattern_covers("**", "docs/audit/findings") is False
    assert findings._pattern_covers("docs/audit", "docs/audit/findings") is True
    assert findings._pattern_covers("docs/audit/findings/x.md", "docs/audit/findings") is False


def test_store_rel_falls_back_to_the_canonical_path_without_a_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(findings, "find_repo_root", lambda _p: None)
    assert findings._store_rel(tmp_path) == "docs/audit/findings"


def test_store_rel_falls_back_when_the_store_is_outside_the_repo(tmp_path, monkeypatch):
    monkeypatch.setattr(findings, "find_repo_root", lambda _p: tmp_path / "elsewhere")
    assert findings._store_rel(tmp_path) == "docs/audit/findings"


def test_gitignore_scan_skips_comments_and_negations_and_survives_oserror(tmp_path):
    repo = tmp_path
    (repo / ".git").mkdir()
    store = repo / "docs" / "audit" / "findings"
    store.mkdir(parents=True)
    (repo / ".gitignore").write_text(
        "# a comment\n\n!docs/audit/findings\nunrelated/\n", encoding="utf-8"
    )
    assert findings.is_store_gitignored(store) is False

    (repo / ".gitignore").unlink()
    (repo / ".gitignore").mkdir()  # read_text now raises IsADirectoryError
    assert findings.is_store_gitignored(store) is False


def test_gitattributes_probe_and_writer_survive_an_unreadable_path(tmp_path):
    store = tmp_path / "docs" / "audit" / "findings"
    store.mkdir(parents=True)
    (store / ".gitattributes").mkdir()
    assert findings.store_gitattributes_present(store) is False

    (store / ".gitignore").mkdir()  # read_text raises inside ensure_store_gitattributes
    findings.ensure_store_gitattributes(store)  # must swallow the OSError, not crash


def test_new_finding_reports_a_collision_when_the_existing_file_is_unreadable(tmp_path):
    fid = findings.finding_id("security", "src/auth.py", "Token compared with ==")
    path = tmp_path / "security" / "open" / f"{fid}.md"
    path.mkdir(parents=True)  # a directory: exists() passes, read_text raises
    with pytest.raises(findings.FindingError, match="id collision"):
        _new(tmp_path)


def test_resolve_infers_the_auditor_from_the_directory(tmp_path):
    """A hand-written finding with no `auditor:` still resolves — the directory is
    the fallback, and the resulting ledger record must carry it."""
    path = tmp_path / "security" / "open" / "security-aabbccdd.md"
    path.parent.mkdir(parents=True)
    path.write_text(_render(_drop("auditor")), encoding="utf-8")
    findings.resolve_finding(tmp_path, "security-aabbccdd", "fixed", "done", date="2026-07-09")
    assert findings.resolved_records(tmp_path)["security-aabbccdd"]["auditor"] == "security"


def test_force_resolve_rewrites_the_ledger_when_the_id_is_open_and_recorded(tmp_path):
    """The both-halves state validate_store flags: force must rewrite the record in
    place rather than appending a second one."""
    path = _write_finding(tmp_path, dict(GOOD_FM))
    findings.append_ledger(tmp_path, {**GOOD_REC, "title": "stale"})
    findings.resolve_finding(
        tmp_path, GOOD_FM["id"], "invalid", "wrong call", date="2026-07-10", force=True
    )
    recs = [
        json.loads(ln)
        for ln in findings.ledger_path(tmp_path).read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert [r["id"] for r in recs] == [GOOD_FM["id"]]  # rewritten, not duplicated
    assert recs[0]["status"] == "invalid"
    assert not path.exists()


def test_show_falls_through_to_the_ledger_when_the_open_file_vanishes(tmp_path, monkeypatch):
    """A concurrent resolve can unlink the open file between the glob and the read."""
    open_file = _write_finding(tmp_path, dict(GOOD_FM))
    findings.append_ledger(tmp_path, GOOD_REC)
    real_read_text = Path.read_text

    def _vanished(self, *a, **k):
        if self == open_file:
            raise FileNotFoundError("resolved concurrently")
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _vanished)
    shown = findings.show_finding(tmp_path, GOOD_FM["id"])
    assert "status: fixed" in shown


def test_validate_store_flags_a_legacy_resolved_tree_and_duplicate_ids(tmp_path):
    legacy = tmp_path / "audit" / "resolved" / "N-003.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(_render({**GOOD_FM, "id": "N-003"}), encoding="utf-8")
    _write_finding(tmp_path, dict(GOOD_FM))
    _write_finding(tmp_path, {**GOOD_FM, "auditor": "tests"})
    errors = findings.validate_store(tmp_path)
    assert any("legacy resolved file outside the ledger" in e for e in errors)
    assert any("duplicate id" in e for e in errors)


def test_validate_store_reports_an_unreadable_ledger(tmp_path):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.mkdir()
    assert any("cannot read" in e for e in findings.validate_store(tmp_path))


def test_validate_store_skips_blank_ledger_lines_and_flags_scalars(tmp_path):
    lp = findings.ledger_path(tmp_path)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.write_text(f'\n{json.dumps(GOOD_REC)}\n"a string"\n', encoding="utf-8")
    errors = findings.validate_store(tmp_path)
    assert any("not a JSON object" in e for e in errors)


def _legacy_resolved(root: Path, auditor: str, fid: str, **fm) -> Path:
    path = root / auditor / "resolved" / f"{fid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = {"id": fid, "status": "fixed", "found": "2026-07-08", "resolved": "2026-07-09", **fm}
    path.write_text(_render(front, title="T", body="## Resolution\nDone.\n"), encoding="utf-8")
    return path


def test_migrate_resolved_dry_run_reports_without_writing(tmp_path, capsys):
    path = _legacy_resolved(tmp_path, "audit", "N-001")
    appended, total = findings.migrate_resolved(tmp_path, dry_run=True)
    assert (appended, total) == (1, 1)
    out = capsys.readouterr().out
    assert "WOULD APPEND N-001" in out
    assert f"WOULD DELETE {path}" in out
    assert path.exists()
    assert not findings.ledger_path(tmp_path).exists()


def test_migrate_resolved_deletes_an_already_recorded_duplicate(tmp_path):
    _legacy_resolved(tmp_path, "audit", "N-001")
    findings.migrate_resolved(tmp_path)
    again = _legacy_resolved(tmp_path, "audit", "N-001")
    appended, total = findings.migrate_resolved(tmp_path)
    assert (appended, total) == (0, 1)  # nothing appended, the file still removed
    assert not again.exists()


def test_migrate_resolved_synthesises_a_date_when_none_is_recorded(tmp_path):
    path = tmp_path / "audit" / "resolved" / "N-002.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        _render({"id": "N-002", "auditor": "audit", "status": "fixed"}, body="## Resolution\nx\n"),
        encoding="utf-8",
    )
    findings.migrate_resolved(tmp_path)
    rec = findings.resolved_records(tmp_path)["N-002"]
    assert rec["resolved"] == "1970-01-01"
    assert rec["date_synthesised"] is True


def test_migrate_resolved_infers_the_auditor_and_rejects_a_bad_status(tmp_path):
    path = tmp_path / "audit" / "resolved" / "N-004.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        _render({"id": "N-004", "status": "fixed", "resolved": "2026-07-09"}, body="## R\nx\n"),
        encoding="utf-8",
    )
    findings.migrate_resolved(tmp_path)
    assert findings.resolved_records(tmp_path)["N-004"]["auditor"] == "audit"

    bad = tmp_path / "audit" / "resolved" / "N-005.md"
    bad.parent.mkdir(parents=True, exist_ok=True)  # migrate_resolved removed the tree
    bad.write_text(
        _render({"id": "N-005", "auditor": "audit", "status": "open"}, body="## R\nx\n"),
        encoding="utf-8",
    )
    with pytest.raises(findings.FindingError, match="unrecognised status"):
        findings.migrate_resolved(tmp_path)


def test_migrate_resolved_reports_an_unreadable_legacy_file(tmp_path):
    (tmp_path / "audit" / "resolved" / "N-006.md").mkdir(parents=True)
    with pytest.raises(findings.FindingError, match="cannot read"):
        findings.migrate_resolved(tmp_path)


def test_migrate_v1_dry_run_reports_without_writing(tmp_path, capsys):
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(V1_DOC, encoding="utf-8")
    root = tmp_path / "findings"
    assert findings.migrate_v1(src, root, dry_run=True) == 3
    out = capsys.readouterr().out
    assert "WOULD WRITE" in out
    assert "WOULD APPEND" in out
    assert not root.exists() or list(root.glob("*/open/*.md")) == []


def test_migrate_v1_refuses_when_an_open_id_is_already_in_the_ledger(tmp_path):
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(V1_DOC, encoding="utf-8")
    root = tmp_path / "findings"
    findings.migrate_v1(src, root)
    # Re-resolve the migrated open finding, then re-migrate: the id is now in the
    # ledger while the source still lists it as open.
    findings.resolve_finding(root, "N-090", "fixed", "done", date="2026-07-09")
    with pytest.raises(findings.FindingError, match="duplicate id N-090"):
        findings.migrate_v1(src, root)


def test_migrate_v1_refuses_when_a_resolved_id_is_open_on_disk(tmp_path):
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(V1_DOC, encoding="utf-8")
    root = tmp_path / "findings"
    findings.migrate_v1(src, root)
    findings.ledger_path(root).unlink()  # drop the ledger, keep N-102 open on disk
    (root / "audit" / "open" / "N-102.md").write_text(
        _render(
            {
                "id": "N-102",
                "auditor": "audit",
                "status": "open",
                "severity": "low",
                "category": "security",
                "area": "x",
                "found": "2026-07-08",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(findings.FindingError, match="duplicate id N-102"):
        findings.migrate_v1(src, root)


def test_list_filters_resolved_records_by_status(tmp_path):
    findings.append_ledger(tmp_path, GOOD_REC)
    findings.append_ledger(tmp_path, {**GOOD_REC, "id": "security-11223344", "status": "invalid"})
    fixed = findings.gather_findings(tmp_path, status="fixed")
    assert [r["id"] for r in fixed] == [GOOD_REC["id"]]


# --- CLI: the only findings-store interface in Copilot, pi and CI ---


def test_cli_new_reports_a_duplicate_and_exits_one(tmp_path, capsys):
    _new(tmp_path)
    code = findings.main(
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
    assert code == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_resolve_reports_an_unknown_id_and_exits_one(tmp_path, capsys):
    code = findings.main(
        [
            "resolve",
            "--root",
            str(tmp_path),
            "security-deadbeef",
            "--status",
            "fixed",
            "--notes",
            "n",
        ]
    )
    assert code == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_show_prints_a_finding_and_reports_an_unknown_id(tmp_path, capsys):
    path = _new(tmp_path)
    assert findings.main(["show", "--root", str(tmp_path), path.stem]) == 0
    assert "# Token compared with ==" in capsys.readouterr().out

    assert findings.main(["show", "--root", str(tmp_path), "security-deadbeef"]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_validate_on_explicit_paths(tmp_path, capsys):
    good = _write_finding(tmp_path, dict(GOOD_FM))
    assert findings.main(["validate", "--root", str(tmp_path), str(good)]) == 0
    assert "OK  findings store consistent." in capsys.readouterr().out

    bad = _write_finding(tmp_path, {**GOOD_FM, "status": "opne"})
    assert findings.main(["validate", "--root", str(tmp_path), str(bad)]) == 1
    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "error(s) in findings store." in out


def test_cli_validate_on_a_missing_root_is_not_a_failure(tmp_path, capsys):
    missing = tmp_path / "nope"
    assert findings.main(["validate", "--root", str(missing)]) == 0
    assert "nothing to check" in capsys.readouterr().out


def test_cli_validate_warns_about_review_hygiene(tmp_path, capsys):
    _write_finding(tmp_path, dict(GOOD_FM))
    assert findings.main(["validate", "--root", str(tmp_path)]) == 0
    assert "WARNING" in capsys.readouterr().out


def test_cli_baseline_clear(tmp_path, capsys):
    assert findings.main(["baseline", "--root", str(tmp_path), "--clear"]) == 0
    assert "no baseline to clear" in capsys.readouterr().out

    _new(tmp_path)
    findings.main(["baseline", "--root", str(tmp_path)])
    capsys.readouterr()
    assert findings.main(["baseline", "--root", str(tmp_path), "--clear"]) == 0
    assert "baseline cleared" in capsys.readouterr().out


def test_cli_migrate_dry_run_then_real(tmp_path, capsys):
    src = tmp_path / "nitpicker-findings.md"
    src.write_text(V1_DOC, encoding="utf-8")
    root = tmp_path / "findings"

    assert findings.main(["migrate", "--root", str(root), "--dry-run", str(src)]) == 0
    out = capsys.readouterr().out
    assert "would migrate 3 finding(s)" in out
    assert "dry run: would migrate 3 finding(s) in total" in out

    assert findings.main(["migrate", "--root", str(root), str(src)]) == 0
    assert "total: 3" in capsys.readouterr().out
    assert (root / "INDEX.md").exists()


def test_cli_migrate_reports_a_bad_source_and_exits_one(tmp_path, capsys):
    root = tmp_path / "findings"
    assert findings.main(["migrate", "--root", str(root), str(tmp_path / "gone.md")]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_cli_migrate_resolved_dry_run_then_real(tmp_path, capsys):
    _legacy_resolved(tmp_path, "audit", "N-001")

    assert findings.main(["migrate-resolved", "--root", str(tmp_path), "--dry-run"]) == 0
    assert "would migrate 1 finding(s), remove 1 file(s)" in capsys.readouterr().out

    assert findings.main(["migrate-resolved", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "migrated 1 resolved finding(s)" in out
    assert "(1 file(s) removed)" in out
    assert findings.resolved_records(tmp_path)["N-001"]["status"] == "fixed"


def test_cli_migrate_resolved_reports_a_conflict_and_exits_one(tmp_path, capsys):
    (tmp_path / "audit" / "resolved" / "N-006.md").mkdir(parents=True)
    assert findings.main(["migrate-resolved", "--root", str(tmp_path)]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_module_runs_as_a_script(monkeypatch, capsys, tmp_path):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    monkeypatch.setattr(sys, "argv", ["findings.py", "validate", "--root", str(tmp_path / "nope")])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0
    assert "nothing to check" in capsys.readouterr().out
