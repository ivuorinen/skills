"""Tests for scripts/hooks/validate-audit-findings-hook.py (thin store-validation hook)."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).parent.parent / "scripts" / "hooks" / "validate-audit-findings-hook.py"
FINDINGS_PATH = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "findings.py"

spec = importlib.util.spec_from_file_location("audit_hook", HOOK_PATH)
hook = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
spec.loader.exec_module(hook)  # type: ignore[union-attr]


def _store_file(repo: Path, rel: str, text: str = "x") -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_should_check_accepts_finding_file(tmp_path):
    path = _store_file(tmp_path, "docs/audit/findings/security/open/security-1a2b3c4d.md")
    assert hook.should_check(path, tmp_path)


def test_should_check_rejects_index_and_outsiders(tmp_path):
    index = _store_file(tmp_path, "docs/audit/findings/INDEX.md")
    outside = _store_file(tmp_path, "docs/audit/arch-profile.md")
    non_md = _store_file(tmp_path, "docs/audit/findings/security/open/tool.py")
    assert not hook.should_check(index, tmp_path)
    assert not hook.should_check(outside, tmp_path)
    assert not hook.should_check(non_md, tmp_path)


def test_should_check_rejects_missing_file(tmp_path):
    missing = tmp_path / "docs/audit/findings/security/open/gone.md"
    assert not hook.should_check(missing, tmp_path)


def test_should_check_matches_under_symlinked_repo_root(tmp_path):
    # Regression (audit fix 2026-07-09): a symlinked checkout must not disable
    # the hook. The caller resolves the edited path, so the root must resolve too.
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    path = _store_file(real, "docs/audit/findings/security/open/security-1a2b3c4d.md").resolve()
    assert hook.should_check(path, link)


def test_main_ignores_invalid_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    hook.main()
    assert capsys.readouterr().out == ""


def test_main_reports_invalid_finding_from_real_payload(monkeypatch, tmp_path, capsys):
    """PostToolUse delivers the path nested under tool_input; failure must be exit 2 + stderr."""
    path = _store_file(
        tmp_path, "docs/audit/findings/security/open/security-1a2b3c4d.md", "no frontmatter"
    )
    monkeypatch.setattr(hook, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hook, "FINDINGS", FINDINGS_PATH)
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc:
        hook.main()
    assert exc.value.code == 2
    assert "not a valid finding file" in capsys.readouterr().err


def test_main_accepts_legacy_toplevel_payload(monkeypatch, tmp_path, capsys):
    path = _store_file(
        tmp_path, "docs/audit/findings/security/open/security-1a2b3c4d.md", "no frontmatter"
    )
    monkeypatch.setattr(hook, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hook, "FINDINGS", FINDINGS_PATH)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"file_path": str(path)})))
    with pytest.raises(SystemExit) as exc:
        hook.main()
    assert exc.value.code == 2
    assert "not a valid finding file" in capsys.readouterr().err


@pytest.mark.parametrize("payload", [{}, {"file_path": ""}])
def test_main_noop_without_path(monkeypatch, payload, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    hook.main()
    assert capsys.readouterr().out == ""


def test_main_regenerates_index_for_valid_finding(monkeypatch, tmp_path, capsys):
    fspec = importlib.util.spec_from_file_location("findings", FINDINGS_PATH)
    findings = importlib.util.module_from_spec(fspec)  # type: ignore[arg-type]
    fspec.loader.exec_module(findings)  # type: ignore[union-attr]

    root = tmp_path / "docs" / "audit" / "findings"
    path = findings.new_finding(
        root,
        auditor="security",
        severity="high",
        category="security",
        area="src/auth.py",
        title="Token compared with ==",
        body="## Problem\np\n\n## Evidence\ne\n\n## Impact\ni\n\n## Fix\nf\n",
    )
    monkeypatch.setattr(hook, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hook, "FINDINGS", FINDINGS_PATH)
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    hook.main()
    assert capsys.readouterr().out == ""
    assert (root / "INDEX.md").exists()


def test_main_regenerated_index_uses_relative_paths(monkeypatch, tmp_path):
    # Regression (audit-307527a8): the hook must regenerate INDEX with the same
    # repo-relative paths as canonical `findings.py index` — never absolute paths,
    # which leak the checkout directory and fail make check / CI index-check.
    fspec = importlib.util.spec_from_file_location("findings", FINDINGS_PATH)
    findings = importlib.util.module_from_spec(fspec)  # type: ignore[arg-type]
    fspec.loader.exec_module(findings)  # type: ignore[union-attr]

    root = tmp_path / "docs" / "audit" / "findings"
    path = findings.new_finding(
        root,
        auditor="security",
        severity="high",
        category="security",
        area="src/auth.py",
        title="Token compared with ==",
        body="## Problem\np\n\n## Evidence\ne\n\n## Impact\ni\n\n## Fix\nf\n",
    )
    monkeypatch.setattr(hook, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hook, "FINDINGS", FINDINGS_PATH)
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(path)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    hook.main()

    index_text = (root / "INDEX.md").read_text(encoding="utf-8")
    assert str(tmp_path) not in index_text  # no absolute paths leaked
    assert "docs/audit/findings/security/open/" in index_text  # canonical relative form


def test_main_handles_resolved_ledger_edit(monkeypatch, tmp_path, capsys):
    # A resolved.jsonl edit is store-validated and regenerates INDEX (the ledger
    # has no per-line file, so there is nothing to per-file validate).
    fspec = importlib.util.spec_from_file_location("findings", FINDINGS_PATH)
    findings = importlib.util.module_from_spec(fspec)  # type: ignore[arg-type]
    fspec.loader.exec_module(findings)  # type: ignore[union-attr]

    root = tmp_path / "docs" / "audit" / "findings"
    path = findings.new_finding(
        root,
        auditor="security",
        severity="high",
        category="security",
        area="src/auth.py",
        title="Token compared with ==",
        body="## Problem\np\n\n## Evidence\ne\n\n## Impact\ni\n\n## Fix\nf\n",
    )
    findings.resolve_finding(root, path.stem, "fixed", "done")
    ledger = root / "resolved.jsonl"
    monkeypatch.setattr(hook, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hook, "FINDINGS", FINDINGS_PATH)
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(ledger)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    hook.main()  # no SystemExit — the ledger is valid
    assert capsys.readouterr().err == ""
    assert (root / "INDEX.md").exists()
