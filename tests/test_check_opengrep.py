"""Tests for scripts/check-opengrep.py.

The gate's whole value is that it fails when something is wrong, so most of these
drive it to a non-zero exit and assert on what it said. The two properties worth
naming, because both were defects in the first draft:

* a marker is a COMMENT token, never a textual match — this file's own prose
  mentions `# nosemgrep` and must not be read as a suppression;
* a scan error is fatal, because a file opengrep could not parse is a file it did
  not scan, and reporting the rest as clean is the silent gap the gate exists to
  close.
"""

import importlib.util
import json
import runpy
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
_TOOL = REPO_ROOT / "scripts" / "check-opengrep.py"

_spec = importlib.util.spec_from_file_location("check_opengrep", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _result(stdout: str = "", returncode: int = 0, stderr: str = ""):
    """A stand-in for the opengrep process, so no scanner runs during the tests.

    A real invocation would need the binary present and would reach the registry,
    making the suite depend on both a tool and the network.
    """
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _finding(path: str, line: int, rule: str = "python.lang.security.audit.x.dangerous-x"):
    """One opengrep result, trimmed to the three keys the tool actually reads.

    The fully-qualified `rule` is deliberate: the tool prints only the last
    dotted segment, and a short id here would let that truncation pass untested.
    """
    return {"path": path, "start": {"line": line}, "check_id": rule}


def _scan_json(results=(), errors=()):
    """A scan payload with both keys always present.

    `errors` is never omitted, because the tool treats a scan error as fatal and
    a fixture that dropped the key would exercise the `.get` default instead of
    the real shape opengrep emits.
    """
    return json.dumps({"results": list(results), "errors": list(errors)})


@pytest.fixture
def tool(monkeypatch, tmp_path):
    """The module with its scan roots pointed at a scratch tree."""
    monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(_mod, "SCAN_ROOTS", ("pkg",))
    (tmp_path / "pkg").mkdir()
    return _mod


# --------------------------------------------------------------------------
# argument handling
# --------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["-h", "--help"])
def test_help_prints_usage_on_stdout_and_exits_zero(flag, capsys):
    assert _mod.main([flag]) == 0
    out = capsys.readouterr().out
    assert "usage: check-opengrep.py" in out
    assert _mod.CONFIG in out


def test_an_unexpected_argument_is_a_usage_error(capsys):
    assert _mod.main(["bogus"]) == 2
    assert "unexpected argument: bogus" in capsys.readouterr().err


# --------------------------------------------------------------------------
# locating opengrep
# --------------------------------------------------------------------------


def test_missing_opengrep_outside_ci_skips(monkeypatch, capsys):
    monkeypatch.setattr(_mod.shutil, "which", lambda _: None)
    monkeypatch.delenv("CI", raising=False)
    assert _mod.main([]) == 0
    assert "SKIP" in capsys.readouterr().err


def test_missing_opengrep_under_ci_fails(monkeypatch, capsys):
    """A gate that skips silently is not a gate — under CI it must fail."""
    monkeypatch.setattr(_mod.shutil, "which", lambda _: None)
    monkeypatch.setenv("CI", "true")
    assert _mod.main([]) == 1
    assert "cannot be skipped under CI" in capsys.readouterr().err


def test_resolve_returns_the_binary_when_present(monkeypatch):
    monkeypatch.setattr(_mod.shutil, "which", lambda _: "/usr/bin/opengrep")
    assert _mod._resolve_opengrep() == ("/usr/bin/opengrep", 0)


# --------------------------------------------------------------------------
# _scan
# --------------------------------------------------------------------------


def test_scan_passes_disable_nosem_only_when_asked(monkeypatch):
    seen = []

    def fake(argv, **kwargs):
        """Record the argv each pass builds, so the flag can be asserted on."""
        seen.append(argv)
        return _result(_scan_json())

    monkeypatch.setattr(_mod.subprocess, "run", fake)
    _mod._scan("opengrep", disable_nosem=False)
    _mod._scan("opengrep", disable_nosem=True)
    assert "--disable-nosem" not in seen[0]
    assert "--disable-nosem" in seen[1]
    assert seen[0][:2] == ["opengrep", "scan"]


@pytest.mark.parametrize(
    ("exc", "fragment"),
    [
        (subprocess.TimeoutExpired(cmd="opengrep", timeout=1), "exceeded"),
        (OSError("boom"), "could not run opengrep"),
    ],
)
def test_scan_turns_process_failures_into_runtime_errors(monkeypatch, exc, fragment):
    def fake(*a, **k):
        """Simulate the process dying rather than returning — timeout or exec failure."""
        raise exc

    monkeypatch.setattr(_mod.subprocess, "run", fake)
    with pytest.raises(RuntimeError, match=fragment):
        _mod._scan("opengrep", disable_nosem=False)


def test_scan_rejects_a_nonzero_exit(monkeypatch):
    monkeypatch.setattr(_mod.subprocess, "run", lambda *a, **k: _result(returncode=3, stderr="bad"))
    with pytest.raises(RuntimeError, match="exited 3"):
        _mod._scan("opengrep", disable_nosem=False)


def test_scan_rejects_a_nonzero_exit_with_only_stdout(monkeypatch):
    monkeypatch.setattr(
        _mod.subprocess, "run", lambda *a, **k: _result(stdout="oops", returncode=3)
    )
    with pytest.raises(RuntimeError, match="oops"):
        _mod._scan("opengrep", disable_nosem=False)


def test_scan_rejects_non_json_output(monkeypatch):
    monkeypatch.setattr(_mod.subprocess, "run", lambda *a, **k: _result(stdout="not json"))
    with pytest.raises(RuntimeError, match="did not emit JSON"):
        _mod._scan("opengrep", disable_nosem=False)


# --------------------------------------------------------------------------
# marker detection
# --------------------------------------------------------------------------


def test_a_marker_inside_a_string_is_not_a_marker(tool, tmp_path):
    """The defect that made the first draft report its own docstring as stale."""
    (tmp_path / "pkg" / "a.py").write_text(
        '"""Prose mentioning # nosemgrep in a docstring."""\n'
        'MESSAGE = "write # nosemgrep above the call"\n'
        "x = 1  # nosemgrep: real-rule\n",
        encoding="utf-8",
    )
    found = tool._markers_in(tool._scanned_sources())
    assert [(m[0], m[1]) for m in found] == [("pkg/a.py", 3)]


@pytest.mark.parametrize("spelling", ["# nosemgrep: r", "# nosem: r", "#nosemgrep"])
def test_both_accepted_spellings_are_recognised(tool, tmp_path, spelling):
    (tmp_path / "pkg" / "a.py").write_text(f"x = 1  {spelling}\n", encoding="utf-8")
    assert len(tool._markers_in(tool._scanned_sources())) == 1


def test_a_file_that_cannot_be_tokenized_is_an_error(tool, tmp_path):
    (tmp_path / "pkg" / "bad.py").write_text('x = """unterminated\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="could not tokenize"):
        tool._markers_in(tool._scanned_sources())


def test_unscanned_sources_skip_the_scan_roots_and_vendored_trees(tool, tmp_path):
    (tmp_path / "pkg" / "inside.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "outside.py").write_text("x = 1  # nosemgrep: r\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "dep.py").write_text("x = 1  # nosemgrep: r\n", encoding="utf-8")

    names = [p.name for p in tool._unscanned_sources()]
    assert names == ["outside.py"]


# --------------------------------------------------------------------------
# reporting helpers
# --------------------------------------------------------------------------


def test_report_errors_is_silent_when_there_are_none(capsys):
    assert _mod._report_errors([{"results": [], "errors": []}]) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("err", "expected"),
    [
        ({"path": "a.py", "message": "Syntax error\nmore"}, "a.py: Syntax error"),
        ({"type": "SomeType"}, "(no path): SomeType"),
        ({"path": "b.py", "message": ""}, "b.py: "),
    ],
)
def test_report_errors_names_the_unscanned_file(err, expected, capsys):
    assert _mod._report_errors([{"errors": [err]}]) == 1
    assert expected in capsys.readouterr().out


def test_report_findings_is_silent_when_clean(capsys):
    assert _mod._report_findings({"results": []}) == 0
    assert capsys.readouterr().out == ""


def test_report_findings_lists_each_with_its_short_rule_name(capsys):
    count = _mod._report_findings({"results": [_finding("a.py", 12), _finding("b.py", 3)]})
    out = capsys.readouterr().out
    assert count == 2
    assert "a.py:12  dangerous-x" in out
    assert "DIRECTLY above" in out


def test_report_stale_is_silent_when_every_marker_is_live(tool, tmp_path, capsys):
    (tmp_path / "pkg" / "a.py").write_text("x = 1  # nosemgrep: r\n", encoding="utf-8")
    assert tool._report_stale({("pkg/a.py", 1)}) == 0
    assert capsys.readouterr().out == ""


def test_a_marker_on_the_line_above_its_finding_counts_as_live(tool, tmp_path):
    (tmp_path / "pkg" / "a.py").write_text("# nosemgrep: r\nx = 1\n", encoding="utf-8")
    assert tool._report_stale({("pkg/a.py", 2)}) == 0


def test_a_marker_two_lines_above_its_finding_is_stale(tool, tmp_path, capsys):
    """The exact placement bug this check exists to catch."""
    (tmp_path / "pkg" / "a.py").write_text("# nosemgrep: r\n\nx = 1\n", encoding="utf-8")
    assert tool._report_stale({("pkg/a.py", 3)}) == 1
    assert "pkg/a.py:1" in capsys.readouterr().out


def test_a_ruleset_matching_nothing_fails_the_gate(tool, tmp_path, capsys):
    """The markers double as this gate's known-positive control — pin that.

    A scanner whose rules never loaded and a codebase with nothing to report
    emit the same thing: zero results, exit 0, a well-formed report. Here the
    live markers are what separates them. Each one is a position a rule is known
    to fire at, so an empty `suppressed` — what both passes return when the
    ruleset matches nothing — makes every marker stale at once and fails the
    gate rather than printing "clean".

    Asserts the property, not a count: the number of markers changes as
    suppressions come and go, and a test pinned to today's total would fail for
    the wrong reason. What must hold is that *all* of them go stale and the
    result is non-zero.

    Not hypothetical. A CodeQL run in this repository reported the tree clean
    across every suite and threat model because one library pack was absent.
    """
    for name, body in (("a.py", "x = 1  # nosemgrep: r\n"), ("b.py", "# nosemgrep: r\ny = 2\n")):
        (tmp_path / "pkg" / name).write_text(body, encoding="utf-8")

    live = len(tool._markers_in(tool._scanned_sources()))
    assert live, "fixture must provide markers, or the control proves nothing"
    assert tool._report_stale(set()) == live
    assert "suppress nothing" in capsys.readouterr().out


# --------------------------------------------------------------------------
# main, end to end
# --------------------------------------------------------------------------


@pytest.fixture
def run_main(tool, monkeypatch, tmp_path):
    """Drive main() with a scripted pair of scans."""

    def go(active_json, revealed_json):
        """Feed the two passes in order: active scan first, --disable-nosem second.

        The order is the contract — main() subtracts the first from the second to
        derive what a marker suppressed, so swapping them inverts every verdict.
        """
        monkeypatch.setattr(tool.shutil, "which", lambda _: "/usr/bin/opengrep")
        calls = iter([_result(active_json), _result(revealed_json)])
        monkeypatch.setattr(tool.subprocess, "run", lambda *a, **k: next(calls))
        return tool.main([])

    return go


def test_a_clean_tree_passes(run_main, tmp_path, capsys):
    (tmp_path / "pkg" / "a.py").write_text("x = 1  # nosemgrep: r\n", encoding="utf-8")
    assert run_main(_scan_json(), _scan_json([_finding("pkg/a.py", 1)])) == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert "1 suppression(s) all still live" in out


def test_a_clean_tree_reports_markers_it_could_not_judge(run_main, tmp_path, capsys):
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "b.py").write_text("y = 2  # nosemgrep: r\n", encoding="utf-8")
    assert run_main(_scan_json(), _scan_json()) == 0
    assert "1 marker(s) outside pkg not judged" in capsys.readouterr().out


def test_an_unsuppressed_finding_fails(run_main, tmp_path, capsys):
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    found = [_finding("pkg/a.py", 1)]
    assert run_main(_scan_json(found), _scan_json(found)) == 1
    assert "Unsuppressed opengrep findings" in capsys.readouterr().out


def test_a_stale_marker_fails(run_main, tmp_path, capsys):
    (tmp_path / "pkg" / "a.py").write_text("x = 1  # nosemgrep: r\n", encoding="utf-8")
    assert run_main(_scan_json(), _scan_json()) == 1
    out = capsys.readouterr().out
    assert "suppress nothing" in out
    assert "1 problem(s)." in out


def test_a_scan_error_fails_before_anything_is_called_clean(run_main, tmp_path, capsys):
    """A file opengrep could not parse is a file it did not scan."""
    (tmp_path / "pkg" / "a.py").write_text("x = 1\n", encoding="utf-8")
    err = _scan_json(errors=[{"path": "pkg/a.py", "message": "Syntax error"}])
    assert run_main(_scan_json(), err) == 1
    out = capsys.readouterr().out
    assert "not a clean bill" in out
    assert "OK" not in out


def test_a_runtime_error_from_the_scan_is_reported(tool, monkeypatch, capsys):
    monkeypatch.setattr(tool.shutil, "which", lambda _: "/usr/bin/opengrep")
    monkeypatch.setattr(tool.subprocess, "run", lambda *a, **k: _result(stdout="not json"))
    assert tool.main([]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_an_untokenizable_file_fails_main(run_main, tmp_path, capsys):
    (tmp_path / "pkg" / "bad.py").write_text('x = """unterminated\n', encoding="utf-8")
    assert run_main(_scan_json(), _scan_json()) == 1
    assert "could not tokenize" in capsys.readouterr().err


# --------------------------------------------------------------------------
# the wiring this gate depends on
# --------------------------------------------------------------------------


def test_make_check_runs_this_gate():
    """`make check` is the single definition of what "checked" means, and CI
    runs exactly that one target — so the gate binds only if it is listed here."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    check_line = next(ln for ln in makefile.splitlines() if ln.startswith("check:"))
    assert " opengrep" in check_line


def test_ci_installs_opengrep_pinned_and_digest_verified():
    """Without the install step the gate fails CI; without the pin it is a
    tag-shaped hole in the authoritative job (.claude/rules/github-actions-security.md)."""
    workflow = (REPO_ROOT / ".github/workflows/validate-skills.yml").read_text(encoding="utf-8")
    assert "OPENGREP_VERSION:" in workflow
    assert "sha256sum -c -" in workflow
    assert len(_sha_pin(workflow)) == 64


def test_module_runs_as_a_script(monkeypatch):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main().

    Invoked with --help so the entry point is exercised without a scan.
    """
    monkeypatch.setattr("sys.argv", ["check-opengrep.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0


def _sha_pin(workflow: str) -> str:
    """The digest the workflow pins, or "" if the line is gone.

    Returns a string rather than raising so the caller's length assertion is what
    reports a missing pin — a KeyError here would name the parser, not the pin.
    """
    for line in workflow.splitlines():
        if "OPENGREP_SHA256:" in line:
            return line.split(":", 1)[1].strip()
    return ""
