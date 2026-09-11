"""Tests for scripts/bench-recall.py.

Only the grading half is testable and that is the point of the split: grading is
pure, running needs an agent and credentials. So these tests drive `--grade`
against synthetic audited directories, and the runner is covered only where it
fails without invoking anything.

The property under test throughout: a lens is credited for finding the seeded
defect only when it pointed at the right LINES. Crediting it for filing
something — anything — is how a recall benchmark becomes a participation prize.
"""

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "bench-recall.py"
_spec = importlib.util.spec_from_file_location("bench_recall", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"))
import findings  # noqa: E402

_BODY = "## Problem\n\nx\n\n## Evidence\n\nx\n\n## Impact\n\nx\n\n## Fix\n\nx\n"
_BODY_NO_CLASS_WORDS = (
    "## Problem\n\nno class words\n\n## Evidence\n\nx\n\n## Impact\n\nx\n\n## Fix\n\nx\n"
)

CASE = {
    "id": "c",
    "lens": "security",
    "class": "sql-injection",
    "severity_floor": "high",
    "goal": "g",
    "file": "app.py",
    "lines": [10, 12],
    "dir": Path("/nonexistent"),
}


def _audited(tmp_path: Path, *filed: dict) -> Path:
    """A case directory holding a findings store with `filed` in it.

    Written through `findings.new_finding` rather than by hand: grading reads
    the store through the same module, so a fixture that hand-rolled the format
    would be testing agreement between two of my own guesses.
    """
    root = tmp_path / "c"
    store = root / findings.DEFAULT_ROOT
    store.mkdir(parents=True)
    for spec in filed:
        findings.new_finding(
            root=store,
            auditor=spec.get("auditor", "security"),
            severity=spec.get("severity", "high"),
            category="security",
            area="app.py",
            title=spec.get("title", "Unparameterised query"),
            body=spec.get(
                "body", "## Problem\n\nx\n\n## Evidence\n\nx\n\n## Impact\n\nx\n\n## Fix\n\nx\n"
            ),
            location=spec.get("location", "app.py:10-12"),
        )
    return root


# ── the evidence check ───────────────────────────────────────────────────────


def test_a_finding_on_the_expected_range_counts_as_found(tmp_path):
    _audited(tmp_path, {})
    row = _mod.grade_case(CASE, tmp_path / "c")
    assert row["found"] is True
    assert row["severity_ok"] is True
    assert row["findings_on_target"] == 1


def test_a_finding_on_the_wrong_lines_is_not_credited(tmp_path):
    """The lens filed something, just not about this.

    Crediting any finding in the file would score a lens that reported the
    import block as having found a SQL injection forty lines below it.
    """
    _audited(tmp_path, {"location": "app.py:40-44"})
    row = _mod.grade_case(CASE, tmp_path / "c")
    assert row["found"] is False
    assert row["findings_filed"] == 1, "it did file something; it just missed"


def test_a_finding_with_no_location_is_not_credited(tmp_path):
    """A finding that pointed nowhere has not shown its evidence.

    `--location` is optional in the store, so this is a real shape and not a
    hypothetical one.
    """
    _audited(tmp_path, {"location": None})
    row = _mod.grade_case(CASE, tmp_path / "c")
    assert row["found"] is False


def test_a_finding_in_a_different_file_is_not_credited(tmp_path):
    _audited(tmp_path, {"location": "other.py:10-12"})
    row = _mod.grade_case(CASE, tmp_path / "c")
    assert row["found"] is False


@pytest.mark.parametrize(
    "start_end,overlaps",
    [
        ("app.py:10-12", True),  # exact
        ("app.py:1-10", True),  # touches the first line
        ("app.py:12-30", True),  # touches the last line
        ("app.py:1-40", True),  # encloses
        ("app.py:11", True),  # a single line inside
        ("app.py:1-9", False),  # ends just before
        ("app.py:13-20", False),  # starts just after
    ],
)
def test_overlap_is_inclusive_at_both_edges(tmp_path, start_end, overlaps):
    """Off-by-one here silently changes what the benchmark measures."""
    _audited(tmp_path, {"location": start_end})
    assert _mod.grade_case(CASE, tmp_path / "c")["found"] is overlaps


# ── severity ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "severity,ok",
    [("critical", True), ("high", True), ("medium", False), ("low", False), ("advisory", False)],
)
def test_severity_floor_is_at_or_above_not_equal(tmp_path, severity, ok):
    """`severity_floor` is a floor. Filing higher is not a miss."""
    _audited(tmp_path, {"severity": severity})
    row = _mod.grade_case(CASE, tmp_path / "c")
    assert row["found"] is True, "the range matched regardless of severity"
    assert row["severity_ok"] is ok


def test_an_unknown_severity_fails_rather_than_passing():
    """A typo in a floor must not silently satisfy itself."""
    assert _mod._severity_meets("high", "high")
    assert not _mod._severity_meets("high", "nonsense")
    assert not _mod._severity_meets("nonsense", "high")


def test_the_best_match_decides_not_the_first(tmp_path):
    """Two findings can land on one range, and the strongest one decides.

    Realistic rather than contrived: a lens that files "unparameterised query"
    at low and "user input reaches the database unchecked" at critical, both
    anchored to the same lines, has recognised the defect. Taking the first
    would score the store's ordering — and the store orders by content hash, so
    that is effectively random.

    Distinct titles because ids are content-hashed from (auditor, area, title):
    the same title twice is one finding, not two.
    """
    _audited(
        tmp_path,
        {"severity": "low", "title": "Unparameterised query"},
        {"severity": "critical", "title": "User input reaches the database unchecked"},
    )
    row = _mod.grade_case(CASE, tmp_path / "c")
    assert row["findings_on_target"] == 2
    assert row["severity_ok"] is True


# ── class signal (advisory) ──────────────────────────────────────────────────


def test_class_signal_is_reported_but_does_not_decide_found(tmp_path):
    """Vocabulary is not the test. Right lines at the right severity is."""
    _audited(
        tmp_path,
        {
            "title": "Query built by concatenation",
            "body": _BODY_NO_CLASS_WORDS,
        },
    )
    row = _mod.grade_case(CASE, tmp_path / "c")
    assert row["found"] is True
    assert row["severity_ok"] is True
    assert row["class_signal"] is False


def test_class_signal_fires_on_the_class_tokens(tmp_path):
    _audited(tmp_path, {"title": "SQL injection in the user lookup"})
    assert _mod.grade_case(CASE, tmp_path / "c")["class_signal"] is True


# ── failure modes ────────────────────────────────────────────────────────────


def test_a_missing_store_is_an_error_not_a_zero_score(tmp_path):
    """ "The agent filed nothing" and "the agent wrote somewhere else" are
    different problems, and scoring both as recall 0 hides the second."""
    (tmp_path / "c").mkdir()
    with pytest.raises(_mod.RecallError, match="no findings store"):
        _mod.grade_case(CASE, tmp_path / "c")


def test_grading_a_directory_with_no_audited_copy_names_the_case(tmp_path):
    with pytest.raises(_mod.RecallError, match="no audited copy"):
        _mod._grade_dir([CASE], tmp_path)


def test_aggregate_refuses_an_empty_run(tmp_path):
    """Zero cases averaging to nothing would report a passing harness over nothing."""
    with pytest.raises(_mod.RecallError, match="no cases scored"):
        _mod.aggregate([])


def test_run_case_copies_the_case_and_returns_the_copy(tmp_path):
    """The success path, driven with `true` standing in for the agent.

    Copying matters on its own: the agent writes a findings store, and auditing
    in place would leave one inside `benchmarks/corpus/`, where the retrieval
    bench would then pack it as repository content and score against the answer
    key it just generated.
    """
    src = tmp_path / "src"
    (src / "nested").mkdir(parents=True)
    (src / "nested" / "app.py").write_text("x = 1\n", encoding="utf-8")
    case = CASE | {"dir": src}

    target = _mod.run_case(case, "true", tmp_path / "work")

    assert target == tmp_path / "work" / "c"
    assert (target / "nested" / "app.py").read_text(encoding="utf-8") == "x = 1\n"
    assert (src / "nested" / "app.py").exists(), "the corpus case must be left alone"


def test_run_case_reports_a_failed_agent_command(tmp_path):
    """A non-zero agent exit must not be graded as "filed nothing"."""
    case = CASE | {"dir": tmp_path / "src"}
    (tmp_path / "src").mkdir()
    with pytest.raises(_mod.RecallError, match="exited"):
        _mod.run_case(case, "false", tmp_path / "work")


def test_run_case_does_not_hand_the_template_to_a_shell(tmp_path):
    """The command is split, not shelled — so shell syntax is argv, not syntax.

    With `shell=True` this template would create the file. Asserting the
    absence proves the substituted values (a lens name, a goal sentence out of
    expected.json) have nothing to escape into.
    """
    case = CASE | {"dir": tmp_path / "src"}
    (tmp_path / "src").mkdir()
    marker = tmp_path / "pwned"
    with pytest.raises(_mod.RecallError):
        _mod.run_case(case, f"true; touch {marker}", tmp_path / "work")
    assert not marker.exists()


def test_run_case_rejects_an_empty_template(tmp_path):
    case = CASE | {"dir": tmp_path / "src"}
    (tmp_path / "src").mkdir()
    with pytest.raises(_mod.RecallError, match="empty after substitution"):
        _mod.run_case(case, "   ", tmp_path / "work")


def test_run_case_names_the_case_when_substitution_breaks_the_quoting(tmp_path):
    """A goal with an apostrophe leaves an unbalanced quote for `shlex.split`.

    Goals come out of a corpus `expected.json` and are substituted before the
    split, so this is ordinary corpus prose, not a malformed template. Unmapped,
    `ValueError` escapes `run_case`, `_run_all` and `main`'s except clause, and
    the run ends in a traceback naming no case.
    """
    case = CASE | {"dir": tmp_path / "src", "goal": "the retry isn't idempotent"}
    (tmp_path / "src").mkdir()
    with pytest.raises(_mod.RecallError, match="not parseable after substitution"):
        _mod.run_case(case, "agent -p '{goal}'", tmp_path / "work")


def test_run_case_reports_a_command_that_cannot_start(tmp_path, monkeypatch):
    case = CASE | {"dir": tmp_path / "src"}
    (tmp_path / "src").mkdir()

    def boom(*_a, **_k):
        raise OSError("no shell")

    monkeypatch.setattr(_mod.subprocess, "run", boom)
    with pytest.raises(_mod.RecallError, match="failed to run"):
        _mod.run_case(case, "true", tmp_path / "work")


# ── aggregation and CLI ──────────────────────────────────────────────────────


def test_aggregate_averages_each_axis_separately():
    rows = [
        {"found": True, "severity_ok": True, "class_signal": True, "findings_filed": 2},
        {"found": True, "severity_ok": False, "class_signal": False, "findings_filed": 1},
        {"found": False, "severity_ok": False, "class_signal": False, "findings_filed": 0},
    ]
    totals = _mod.aggregate(rows)
    assert totals == {
        "cases": 3,
        "recall": 0.6667,
        "severity_accuracy": 0.3333,
        "class_signal": 0.3333,
        "total_filed": 3,
    }


def test_cli_grades_a_directory_and_reports(tmp_path, monkeypatch, capsys):
    _audited(tmp_path, {})
    monkeypatch.setattr(_mod._retrieval, "load_cases", lambda case="": [CASE])
    assert _mod.main(["--grade", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "recall=1.0" in out
    assert "severity_accuracy=1.0" in out


def test_cli_json_is_machine_readable(tmp_path, monkeypatch, capsys):
    _audited(tmp_path, {})
    monkeypatch.setattr(_mod._retrieval, "load_cases", lambda case="": [CASE])
    assert _mod.main(["--grade", str(tmp_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["totals"]["recall"] == 1.0
    assert payload["cases"][0]["id"] == "c"


def test_cli_reports_a_grading_error_at_exit_one(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(_mod._retrieval, "load_cases", lambda case="": [CASE])
    assert _mod.main(["--grade", str(tmp_path)]) == 1
    assert "no audited copy" in capsys.readouterr().err


def test_cli_requires_a_mode(capsys):
    """`--grade` and `--run` are the whole interface; neither is a default."""
    with pytest.raises(SystemExit) as exc:
        _mod.main([])
    assert exc.value.code == 2


def test_cli_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        _mod.main(["--help"])
    assert exc.value.code == 0
    assert "bench-recall" in capsys.readouterr().out


def test_a_recall_floor_gates_when_one_is_set(tmp_path, monkeypatch, capsys):
    """MIN_RECALL ships as None because no run has produced a distribution yet.

    Pinned so the gating path is live the day a floor is written, rather than
    being discovered broken by the first person to set one.
    """
    _audited(tmp_path, {"location": "app.py:40-44"})
    monkeypatch.setattr(_mod._retrieval, "load_cases", lambda case="": [CASE])
    monkeypatch.setattr(_mod, "MIN_RECALL", 0.5)
    assert _mod.main(["--grade", str(tmp_path)]) == 1
    assert "recall 0.0 < 0.5" in capsys.readouterr().err


def test_run_all_grades_each_case_and_cleans_up(tmp_path, monkeypatch):
    """The audited copies are scratch, and scratch that survives a run accumulates.

    `run_case` is stubbed because invoking an agent is the one thing these tests
    cannot do; the tempdir lifecycle around it is ordinary code and is not
    exempt from being covered.
    """
    audited = _audited(tmp_path, {})
    seen: list[Path] = []

    def fake_run(case, agent_cmd, workdir):
        seen.append(workdir)
        return audited

    monkeypatch.setattr(_mod, "run_case", fake_run)
    rows = _mod._run_all([CASE], "agent", keep=False)
    assert [r["found"] for r in rows] == [True]
    assert seen and not seen[0].exists(), "the scratch workdir outlived the run"


def test_run_all_keeps_the_copies_and_says_where_when_asked(tmp_path, monkeypatch, capsys):
    """`--keep` exists to make a bad run inspectable, so it must name the path."""
    audited = _audited(tmp_path, {})
    seen: list[Path] = []

    def fake_run(case, agent_cmd, workdir):
        seen.append(workdir)
        return audited

    monkeypatch.setattr(_mod, "run_case", fake_run)
    _mod._run_all([CASE], "agent", keep=True)
    assert seen[0].exists()
    assert str(seen[0]) in capsys.readouterr().err
    shutil.rmtree(seen[0], ignore_errors=True)


def test_run_all_cleans_up_even_when_a_case_raises(tmp_path, monkeypatch):
    """The cleanup is in a `finally` for a reason: a failing run is the common one."""
    seen: list[Path] = []

    def boom(case, agent_cmd, workdir):
        seen.append(workdir)
        raise _mod.RecallError("agent died")

    monkeypatch.setattr(_mod, "run_case", boom)
    with pytest.raises(_mod.RecallError):
        _mod._run_all([CASE], "agent", keep=False)
    assert seen and not seen[0].exists()


def test_cli_run_mode_dispatches_to_the_runner(tmp_path, monkeypatch, capsys):
    audited = _audited(tmp_path, {})
    monkeypatch.setattr(_mod._retrieval, "load_cases", lambda case="": [CASE])
    monkeypatch.setattr(_mod, "run_case", lambda case, cmd, wd: audited)
    assert _mod.main(["--run"]) == 0
    assert "recall=1.0" in capsys.readouterr().out


def test_module_runs_as_a_script(monkeypatch, capsys):
    import runpy

    monkeypatch.setattr(sys, "argv", ["bench-recall.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0
    assert "bench-recall" in capsys.readouterr().out
