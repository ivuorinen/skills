"""Tests for scripts/check-agentlinter.py.

No agentlinter runs here: a real invocation needs npx and the network, which
would make the suite depend on both. `_run` is replaced with a canned report
instead, so every test below exercises the gate's own logic.

Three properties are the reason this file exists, and each was a way the gate
could have passed while doing nothing:

* the tool exits 0 on findings, so the gate must judge the parsed report — a
  version that trusted the exit code would pass unconditionally;
* `--local` must be on every invocation, because the default uploads a report
  that quotes instruction-file contents to a third party;
* the version is pinned, because npx resolves `latest` at run time and this
  package's npm releases are not verifiably built from its repository.
"""

import importlib.util
import json
import runpy
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
_TOOL = REPO_ROOT / "scripts" / "check-agentlinter.py"

_spec = importlib.util.spec_from_file_location("check_agentlinter", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _baseline(tmp_path, accepted, reasons=None, pin=None):
    """Write a baseline, justifying every rule in it unless told otherwise.

    Defaulting the reasons and the pin keeps each test about the thing it names;
    the unjustified and pin-mismatch paths have tests of their own.
    """
    if reasons is None:
        reasons = {e["rule"]: "audited: noise" for e in accepted}
    doc = {"pin": _mod.PIN if pin is None else pin, "reasons": reasons, "accepted": accepted}
    (tmp_path / _mod.BASELINE).write_text(json.dumps(doc), encoding="utf-8")


def _diag(rule: str, file: str = "CLAUDE.md", message: str = "m", severity: str = "warning"):
    return {"rule": rule, "file": file, "message": message, "severity": severity, "line": 1}


def _report(*diags):
    return {"score": 80, "diagnostics": list(diags)}


def _with_report(monkeypatch, report):
    monkeypatch.setattr(_mod, "_run", lambda *_args: report)


def test_invocation_is_pinned_local_and_json():
    """The three flags that make the call safe and the gate meaningful.

    Asserted against the source rather than a mocked call because all three are
    single tokens that a later edit could drop without any test noticing: losing
    `--local` starts uploading the repository's instruction files, losing the
    pin runs whatever npm serves that day, and losing `--json` leaves the gate
    parsing a coloured terminal report.
    """
    src = _TOOL.read_text(encoding="utf-8")
    assert '"--local"' in src
    assert '"--json"' in src
    assert 'f"agentlinter@{PIN}"' in src
    assert _mod.PIN.count(".") == 2, "PIN must be an exact npm version, not a range or tag"


def test_a_new_diagnostic_fails(tmp_path, monkeypatch, capsys):
    """The gate's whole point. agentlinter exits 0 here and every other case."""
    _baseline(tmp_path, [])
    _with_report(monkeypatch, _report(_diag("clarity/escape-hatch-missing")))

    assert _mod.main([str(tmp_path)]) == 1
    assert "1 NEW diagnostic" in capsys.readouterr().err


def test_a_baselined_diagnostic_passes(tmp_path, monkeypatch, capsys):
    accepted = [{"rule": "clarity/escape-hatch-missing", "file": "CLAUDE.md", "message": "m"}]
    _baseline(tmp_path, accepted)
    _with_report(monkeypatch, _report(_diag("clarity/escape-hatch-missing")))

    assert _mod.main([str(tmp_path)]) == 0
    assert "no new agentlinter diagnostics" in capsys.readouterr().out


def test_line_drift_is_not_a_new_diagnostic(tmp_path, monkeypatch):
    """Keying on the line number would report a whole file as new after one
    inserted paragraph, which is the state of every documentation edit here."""
    accepted = [{"rule": "clarity/undefined-term", "file": "AGENTS.md", "message": "m"}]
    _baseline(tmp_path, accepted)
    moved = _diag("clarity/undefined-term", file="AGENTS.md") | {"line": 999}
    _with_report(monkeypatch, _report(moved))

    assert _mod.main([str(tmp_path)]) == 0


def test_a_second_copy_of_a_baselined_diagnostic_is_new(tmp_path, monkeypatch, capsys):
    """Multiplicity, not just membership.

    The key drops the line number deliberately, so two identical offending lines
    in one file collapse to one key. A set difference then reports nothing new
    once the first is baselined — duplicate the bad line and the gate waves it
    through. Counting is what closes that without keying on drifting lines.
    """
    one = {"rule": "clarity/escape-hatch-missing", "file": "CLAUDE.md", "message": "m"}
    _baseline(tmp_path, [one])
    twice = _diag("clarity/escape-hatch-missing")
    _with_report(monkeypatch, _report(twice, dict(twice) | {"line": 42}))

    assert _mod.main([str(tmp_path)]) == 1
    assert "1 NEW diagnostic" in capsys.readouterr().err


def test_losing_one_of_two_identical_diagnostics_reads_as_stale(tmp_path, monkeypatch, capsys):
    """The other direction of the same count: two accepted, one still firing."""
    one = {"rule": "clarity/undefined-term", "file": "AGENTS.md", "message": "m"}
    _baseline(tmp_path, [one, dict(one)])
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term", file="AGENTS.md")))

    assert _mod.main([str(tmp_path)]) == 0
    assert "no longer fire" in capsys.readouterr().out


def test_a_fixed_finding_reports_but_does_not_fail(tmp_path, monkeypatch, capsys):
    """A gate that fails because something was FIXED is one people learn to
    re-run until it passes, which is worse than not having it."""
    accepted = [{"rule": "clarity/compound-instruction", "file": "CLAUDE.md", "message": "m"}]
    _baseline(tmp_path, accepted)
    _with_report(monkeypatch, _report())

    assert _mod.main([str(tmp_path)]) == 0
    assert "no longer fire" in capsys.readouterr().out


def test_update_records_the_current_set(tmp_path, monkeypatch):
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path), "--update"]) == 0
    written = json.loads((tmp_path / _mod.BASELINE).read_text(encoding="utf-8"))
    assert written["pin"] == _mod.PIN
    assert written["accepted"][0]["rule"] == "clarity/undefined-term"


def test_a_missing_baseline_fails_rather_than_passing_empty(tmp_path, monkeypatch, capsys):
    """Treating an absent baseline as "nothing accepted yet" would accept
    everything on the first run of a tree that has never been baselined."""
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path)]) == 1
    assert "--update" in capsys.readouterr().err


def test_an_unusable_report_skips_locally_and_fails_under_ci(tmp_path, monkeypatch):
    """npx absent, the network down, or a future release changing its output.

    Locally that is a skip so an offline clone can still run `make check`; under
    CI it fails, because a gate that skips silently is not a gate.
    """
    _baseline(tmp_path, [])
    _with_report(monkeypatch, None)

    monkeypatch.delenv("CI", raising=False)
    assert _mod.main([str(tmp_path)]) == 0
    monkeypatch.setenv("CI", "true")
    assert _mod.main([str(tmp_path)]) == 1


def test_update_never_skips_when_it_cannot_get_a_report(tmp_path, monkeypatch, capsys):
    """Skipping is right for the gate and wrong for `--update`.

    `_skip_or_fail` used to run before the update branch, so `make
    agentlinter-update` on a host without npx exited 0 having written nothing —
    the contributor believes the diagnostic was accepted while CI keeps failing
    on the unchanged baseline. Locally skippable, never silently un-recorded.
    """
    _baseline(tmp_path, [])
    _with_report(monkeypatch, None)
    monkeypatch.delenv("CI", raising=False)

    assert _mod.main([str(tmp_path), "--update"]) == 1
    assert "nothing to re-record" in capsys.readouterr().err


def test_a_corrupt_baseline_fails_rather_than_being_ignored(tmp_path, monkeypatch, capsys):
    (tmp_path / _mod.BASELINE).write_text("{not json", encoding="utf-8")
    _with_report(monkeypatch, _report())

    assert _mod.main([str(tmp_path)]) == 1
    assert "unreadable" in capsys.readouterr().err


def test_update_repairs_a_corrupt_baseline(tmp_path, monkeypatch, capsys):
    """`--update` is what the read path tells you to run, so it must survive the
    corruption it repairs.

    Regression: `_load_baseline` used to `sys.exit(1)` from inside itself, and
    `_write_baseline` calls it to preserve `reasons` — so `--update` died on a
    corrupt baseline while printing "Regenerate it with … --update" at the user.
    The advice was a loop with no exit.
    """
    (tmp_path / _mod.BASELINE).write_text("{not json", encoding="utf-8")
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path), "--update"]) == 0
    written = json.loads((tmp_path / _mod.BASELINE).read_text(encoding="utf-8"))
    assert written["accepted"][0]["rule"] == "clarity/undefined-term"
    # Unrecoverable reasons are dropped LOUDLY, and the drop is self-correcting:
    # the next gate run fails every rule as unjustified.
    assert written["reasons"] == {}
    assert "reasons not preserved" in capsys.readouterr().err
    assert _mod.main([str(tmp_path)]) == 1


@pytest.mark.parametrize("argv", [["--nope"], ["a", "b"], ["/no/such/dir"]])
def test_usage_errors_exit_2(argv):
    with pytest.raises(SystemExit) as exc:
        _mod.main(argv)
    assert exc.value.code == 2


def _proc(stdout: str = "", stderr: str = "", returncode: int = 0):
    return subprocess.CompletedProcess(
        args=["npx"], returncode=returncode, stdout=stdout, stderr=stderr
    )


def test_run_parses_a_report_and_passes_stderr_through(monkeypatch, capsys):
    """Diagnostics from the tool's own stderr are never discarded: they are how a
    half-working scanner is told apart from a clean tree."""
    monkeypatch.setattr(_mod.shutil, "which", lambda _name: "/usr/bin/npx")
    monkeypatch.setattr(
        _mod.subprocess, "run", lambda *a, **k: _proc(json.dumps(_report(_diag("r"))), "a warning")
    )

    report = _mod._run(Path())
    assert report is not None and report["diagnostics"][0]["rule"] == "r"
    assert "a warning" in capsys.readouterr().err


def test_run_passes_the_pinned_local_json_argv(monkeypatch):
    """The flags asserted textually elsewhere, now as the argv actually built."""
    seen: list[list[str]] = []

    def _capture(argv, **_kwargs):
        seen.append(argv)
        return _proc(json.dumps(_report()))

    monkeypatch.setattr(_mod.shutil, "which", lambda _name: "/usr/bin/npx")
    monkeypatch.setattr(_mod.subprocess, "run", _capture)

    _mod._run(Path("/tmp/x"))
    assert seen[0][:5] == ["/usr/bin/npx", "--yes", f"agentlinter@{_mod.PIN}", "--local", "--json"]


@pytest.mark.parametrize(
    ("which", "run", "expected_err"),
    [
        (lambda _n: None, None, "npx not found"),
        (lambda _n: "/usr/bin/npx", OSError("boom"), "invocation failed"),
        (lambda _n: "/usr/bin/npx", subprocess.TimeoutExpired("npx", 1), "invocation failed"),
        (lambda _n: "/usr/bin/npx", "not json", "was not JSON"),
        (lambda _n: "/usr/bin/npx", '{"score": 1}', "no `diagnostics` list"),
        (lambda _n: "/usr/bin/npx", "[]", "no `diagnostics` list"),
        # `_key` calls .get on each element, so these would raise AttributeError
        # out of main — a traceback instead of the clean skip-or-fail.
        (lambda _n: "/usr/bin/npx", '{"diagnostics": [null]}', "non-object entry"),
        (lambda _n: "/usr/bin/npx", '{"diagnostics": ["a string"]}', "non-object entry"),
    ],
)
def test_run_returns_none_on_every_unusable_outcome(monkeypatch, capsys, which, run, expected_err):
    """Each of these would otherwise read downstream as "the tree is clean"."""
    monkeypatch.setattr(_mod.shutil, "which", which)
    if isinstance(run, BaseException):

        def _raise(*_a, **_k):
            raise run

        monkeypatch.setattr(_mod.subprocess, "run", _raise)
    elif run is not None:
        monkeypatch.setattr(_mod.subprocess, "run", lambda *a, **k: _proc(run))

    assert _mod._run(Path()) is None
    assert expected_err in capsys.readouterr().err


def test_a_new_diagnostic_reports_its_suggested_fix(tmp_path, monkeypatch, capsys):
    """The fix line is the actionable half; a gate that prints only the rule id
    costs a turn to act on."""
    _baseline(tmp_path, [])
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term") | {"fix": "define it"}))

    assert _mod.main([str(tmp_path)]) == 1
    assert "fix: define it" in capsys.readouterr().err


def test_the_module_entry_point_wires_to_main(monkeypatch):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    monkeypatch.setattr("sys.argv", ["check-agentlinter.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0


def test_a_baselined_rule_with_no_reason_fails(tmp_path, monkeypatch, capsys):
    """The risk a baseline carries: it stops being a record of judgements and
    becomes somewhere to put things nobody looked at, and the file cannot tell
    you which it is. Silencing a new rule class has to cost a sentence."""
    accepted = [{"rule": "clarity/undefined-term", "file": "CLAUDE.md", "message": "m"}]
    _baseline(tmp_path, accepted, reasons={})
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "no recorded reason" in err
    assert "clarity/undefined-term" in err


def test_a_baseline_from_another_pin_is_rejected(tmp_path, monkeypatch, capsys):
    """Accepted entries are judgements about one version's rule set.

    Bump PIN without re-recording and the old entries silently vouch for a tool
    that is no longer running. `make check` catches this for the committed
    baseline through its pin test, but the script has to be correct standalone.
    """
    one = {"rule": "clarity/undefined-term", "file": "CLAUDE.md", "message": "m"}
    _baseline(tmp_path, [one], pin="0.0.1-other")
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "recorded by agentlinter@0.0.1-other" in err
    assert _mod.PIN in err


def test_update_rewrites_a_mismatched_pin_and_keeps_reasons(tmp_path, monkeypatch):
    """`--update` is the repair for a pin mismatch, so it must not be blocked by
    one — the same split the corrupt-baseline path makes."""
    one = {"rule": "clarity/undefined-term", "file": "CLAUDE.md", "message": "m"}
    _baseline(tmp_path, [one], reasons={"clarity/undefined-term": "audited: noise"}, pin="0.0.1")
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path), "--update"]) == 0
    written = json.loads((tmp_path / _mod.BASELINE).read_text(encoding="utf-8"))
    assert written["pin"] == _mod.PIN
    assert written["reasons"] == {"clarity/undefined-term": "audited: noise"}
    assert _mod.main([str(tmp_path)]) == 0


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_a_blank_reason_does_not_count_as_a_justification(tmp_path, monkeypatch, capsys, blank):
    """A keys-only membership test lets `{"rule": ""}` stand in for a reason.

    That defeats the whole mechanism: the point is a written justification, and
    an empty string is the absence of one. Treated as absent, so it reaches the
    report that names the rule.
    """
    one = {"rule": "clarity/undefined-term", "file": "CLAUDE.md", "message": "m"}
    _baseline(tmp_path, [one], reasons={"clarity/undefined-term": blank})
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path)]) == 1
    assert "no recorded reason" in capsys.readouterr().err


def test_a_non_string_reason_is_rejected(tmp_path, monkeypatch, capsys):
    """`{"rule": 123}` is malformed data rather than a missing reason, so it
    fails the load instead of being reported as unjustified."""
    one = {"rule": "clarity/undefined-term", "file": "CLAUDE.md", "message": "m"}
    _baseline(tmp_path, [one], reasons={"clarity/undefined-term": 123})
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path)]) == 1
    assert "must be strings" in capsys.readouterr().err


@pytest.mark.parametrize(
    "doc",
    [
        '[{"accepted": []}]',  # top-level array -> .get raises AttributeError
        '{"accepted": [null]}',  # _key(None) raises AttributeError
        '{"accepted": ["a string"]}',
        '{"accepted": "not a list"}',
        '"just a string"',
    ],
)
def test_a_malformed_baseline_reports_instead_of_crashing(tmp_path, monkeypatch, capsys, doc):
    """Valid JSON is not a valid baseline.

    Each of these raised AttributeError past `_load_baseline`'s except clause,
    so the gate showed a traceback and `--update` died before it could rewrite
    the file — the same dead end as the exit-from-a-helper bug, by a different
    route.
    """
    (tmp_path / _mod.BASELINE).write_text(doc, encoding="utf-8")
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term")))

    assert _mod.main([str(tmp_path)]) == 1
    assert "unreadable" in capsys.readouterr().err
    # and the documented repair still works on it
    assert _mod.main([str(tmp_path), "--update"]) == 0


def test_update_preserves_hand_written_reasons(tmp_path, monkeypatch):
    """`--update` regenerates `accepted`. If it regenerated `reasons` too, every
    re-baseline would silently discard the justifications — which would make the
    requirement above theatre rather than a control."""
    accepted = [{"rule": "clarity/undefined-term", "file": "CLAUDE.md", "message": "m"}]
    _baseline(tmp_path, accepted, reasons={"clarity/undefined-term": "audited: ALL-CAPS match"})
    _with_report(monkeypatch, _report(_diag("clarity/undefined-term", message="a different hit")))

    assert _mod.main([str(tmp_path), "--update"]) == 0
    written = json.loads((tmp_path / _mod.BASELINE).read_text(encoding="utf-8"))
    assert written["reasons"] == {"clarity/undefined-term": "audited: ALL-CAPS match"}
    assert written["accepted"][0]["message"] == "a different hit"


def test_a_reason_for_an_unbaselined_rule_is_reported_not_fatal(tmp_path, monkeypatch, capsys):
    """The mirror of a stale entry: a justification that outlived its rule. Worth
    saying so the file does not accumulate defences of findings long gone, but
    not worth failing a build over."""
    _baseline(tmp_path, [], reasons={"clarity/gone": "audited: noise"})
    _with_report(monkeypatch, _report())

    assert _mod.main([str(tmp_path)]) == 0
    assert "clarity/gone" in capsys.readouterr().out


def test_a_non_object_reasons_field_is_rejected(tmp_path, monkeypatch, capsys):
    """A list here would make every `in reasons` check pass on nothing, turning
    the requirement off without changing a line of code."""
    doc = {"pin": "x", "reasons": ["clarity/undefined-term"], "accepted": []}
    (tmp_path / _mod.BASELINE).write_text(json.dumps(doc), encoding="utf-8")
    _with_report(monkeypatch, _report())

    assert _mod.main([str(tmp_path)]) == 1
    assert "unreadable" in capsys.readouterr().err


def test_every_rule_in_the_committed_baseline_is_justified():
    """The real file, not a fixture. This is the assertion that would have caught
    the state this repository was actually in: 32 entries accepted, 0 reasons."""
    data = json.loads((REPO_ROOT / _mod.BASELINE).read_text(encoding="utf-8"))
    baselined = {e["rule"] for e in data["accepted"]}
    missing = baselined - data.get("reasons", {}).keys()
    assert not missing, f"baselined with no recorded reason: {sorted(missing)}"
    for rule, why in data["reasons"].items():
        assert len(why) > 40, f"{rule}: a reason this short is a label, not a justification"


def test_help_is_on_stdout_at_exit_0(capsys):
    assert _mod.main(["--help"]) == 0
    assert "check-agentlinter.py" in capsys.readouterr().out


def test_the_committed_baseline_is_well_formed():
    """The file the gate reads on every `make check`. A hand-edit that breaks its
    shape takes the gate down with it, and the gate is where that would show."""
    data = json.loads((REPO_ROOT / _mod.BASELINE).read_text(encoding="utf-8"))
    assert data["pin"] == _mod.PIN, "baseline was recorded by a different agentlinter version"
    assert data["accepted"], (
        "an empty accepted set accepts nothing — re-run `make agentlinter-update`"
    )
    for entry in data["accepted"]:
        assert {"rule", "file", "message"} <= entry.keys()
