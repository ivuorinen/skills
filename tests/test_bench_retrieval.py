"""Tests for scripts/bench-retrieval.py.

The harness exists to stop a retrieval regression sliding through. So the tests
that matter are the ones proving it still *fails* — a benchmark that cannot go
red is a benchmark nobody has to satisfy.
"""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "bench-retrieval.py"
_spec = importlib.util.spec_from_file_location("bench_retrieval", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _row(**over) -> dict:
    base = {
        "id": "c",
        "lens": "security",
        "class": "x",
        "known_limitation": "",
        "hit": True,
        "rank": 1,
        "candidates": 3,
        "noise_tokens": 0,
        "packed_tokens": 100,
        "precision": 0.5,
        "reciprocal_rank": 1.0,
    }
    return base | over


# ── corpus integrity ─────────────────────────────────────────────────────────


def test_the_shipped_corpus_loads_and_every_range_is_real():
    """Three of the first six expected ranges were wrong when hand-written.

    `load_cases` re-derives nothing — it validates. A range outside its own file
    would score retrieval against lines that do not exist while the run still
    looked healthy.
    """
    cases = _mod.load_cases()
    assert len(cases) >= 6
    for case in cases:
        start, end = case["lines"]
        total = len((case["dir"] / case["file"]).read_text(encoding="utf-8").splitlines())
        assert 1 <= start <= end <= total, case["id"]


def test_every_shipped_case_declares_the_fields_the_harness_reads():
    for case in _mod.load_cases():
        for field in ("id", "lens", "class", "severity_floor", "goal", "file", "lines", "note"):
            assert case.get(field), f"{case['id']} is missing {field}"


def test_an_unknown_case_id_lists_the_known_set():
    with pytest.raises(_mod.BenchError, match="unknown case 'nope'"):
        _mod.load_cases("nope")


def test_a_range_outside_the_file_is_rejected(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    (corpus / "bad").mkdir(parents=True)
    (corpus / "bad" / "a.py").write_text("one\ntwo\n", encoding="utf-8")
    (corpus / "bad" / "expected.json").write_text(
        json.dumps(
            {
                "id": "bad",
                "lens": "x",
                "class": "y",
                "goal": "one two",
                "file": "a.py",
                "lines": [1, 99],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_mod, "CORPUS", corpus)
    with pytest.raises(_mod.BenchError, match=r"outside a\.py"):
        _mod.load_cases()


def test_a_missing_expected_file_is_rejected(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    (corpus / "bad").mkdir(parents=True)
    (corpus / "bad" / "expected.json").write_text(
        json.dumps(
            {
                "id": "bad",
                "lens": "x",
                "class": "y",
                "goal": "g",
                "file": "gone.py",
                "lines": [1, 1],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(_mod, "CORPUS", corpus)
    with pytest.raises(_mod.BenchError, match="does not exist"):
        _mod.load_cases()


# ── the honesty guard ────────────────────────────────────────────────────────


def _one_case(
    tmp_path, monkeypatch, source: str, goal: str, lines: list[int], known_limitation: str = ""
) -> Path:
    corpus = tmp_path / "corpus"
    (corpus / "c").mkdir(parents=True)
    (corpus / "c" / "a.py").write_text(source, encoding="utf-8")
    meta = {"id": "c", "lens": "x", "class": "y", "goal": goal, "file": "a.py", "lines": lines}
    if known_limitation:
        meta["known_limitation"] = known_limitation
    (corpus / "c" / "expected.json").write_text(json.dumps(meta), encoding="utf-8")
    monkeypatch.setattr(_mod, "CORPUS", corpus)
    return corpus


SOURCE = "alpha = 1\nbeta = 2\nUNIQUEWORD = 3\ngamma = 4\n"


def test_a_goal_cribbed_from_the_answer_is_refused(tmp_path, monkeypatch):
    """A goal whose only matching terms sit inside the answer scores a perfect
    rank while measuring nothing at all."""
    _one_case(tmp_path, monkeypatch, SOURCE, "uniqueword", [3, 3])
    with pytest.raises(_mod.BenchError, match="written from the answer"):
        _mod.load_cases()


def test_a_goal_matching_outside_the_answer_is_accepted(tmp_path, monkeypatch):
    _one_case(tmp_path, monkeypatch, SOURCE, "alpha uniqueword", [3, 3])
    assert len(_mod.load_cases()) == 1


def test_a_goal_matching_nowhere_is_accepted_as_a_hard_case(tmp_path, monkeypatch):
    """Terms that appear nowhere are a defect class with no lexical signature.

    That is a real property of the retriever, not a dishonest goal. The
    ts-type-escape goal is exactly that shape — none of "unchecked cast any
    assertion" appears in `api.ts` — and it is now reached by construct matching
    rather than by any term, so a goal whose words match nothing is a case the
    loader must keep accepting.
    """
    _one_case(tmp_path, monkeypatch, SOURCE, "nonexistent vocabulary entirely", [3, 3])
    assert len(_mod.load_cases()) == 1


# ── scoring ──────────────────────────────────────────────────────────────────


def test_scoring_the_shipped_corpus_finds_every_gated_defect():
    rows = [_mod.score_case(c, 4000) for c in _mod.load_cases()]
    missed = [r["id"] for r in rows if not r["hit"] and not r["known_limitation"]]
    assert missed == []


def test_aggregate_excludes_known_limitations_from_the_score():
    """Averaging an expected miss into the score drags every floor down to meet it."""
    rows = [
        _row(),
        _row(
            id="k",
            known_limitation="no lexical signature",
            hit=False,
            rank=0,
            reciprocal_rank=0.0,
            precision=0.0,
        ),
    ]
    totals = _mod.aggregate(rows)
    assert totals["cases"] == 2
    assert totals["gated"] == 1
    assert totals["known_limitations"] == 1
    assert totals["recall_at_5"] == 1.0
    assert totals["mrr"] == 1.0


def test_a_known_limitation_that_starts_hitting_fails_the_gate():
    """Strict-xfail semantics: the exemption must not outlive the limitation."""
    rows = [_row(id="k", known_limitation="no lexical signature", hit=True, rank=1)]
    breaches = _mod.failures(_mod.aggregate(rows), rows)
    assert any("remove the marker" in b for b in breaches)


def test_a_dropped_recall_fails_the_gate():
    rows = [_row(), _row(id="b", hit=False, rank=0, reciprocal_rank=0.0, precision=0.0)]
    breaches = _mod.failures(_mod.aggregate(rows), rows)
    assert any(b.startswith("recall_at_5") for b in breaches)


def test_a_worsened_rank_fails_the_gate():
    rows = [_row(rank=40, reciprocal_rank=0.025)]
    breaches = _mod.failures(_mod.aggregate(rows), rows)
    assert any(b.startswith("mrr") for b in breaches)


def test_noise_before_a_hit_is_counted():
    """Rank alone hides cost: a hit at rank 2 behind a 900-token candidate is expensive."""
    corpus_case = next(c for c in _mod.load_cases() if c["id"] == "adversarial-sql-injection")
    row = _mod.score_case(corpus_case, 4000)
    assert row["rank"] > 1
    assert row["noise_tokens"] > 0


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_passes_on_the_shipped_corpus(capsys):
    assert _mod.main([]) == 0
    assert "recall@5=" in capsys.readouterr().out


def test_cli_json_is_compact_and_carries_both_halves(capsys):
    assert _mod.main(["--json"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    data = json.loads(out)
    assert data["totals"]["gated"] >= 5
    assert {r["id"] for r in data["cases"]} == {c["id"] for c in _mod.load_cases()}


def test_cli_single_case_reports_without_gating(capsys):
    """One case cannot meet an aggregate floor; scoring it in isolation must not fail."""
    assert _mod.main(["--case", "ts-type-escape"]) == 0
    assert "cases=1" in capsys.readouterr().out


def test_cli_unknown_case_exits_one(capsys):
    assert _mod.main(["--case", "nope"]) == 1
    assert "unknown case" in capsys.readouterr().err


def test_cli_reports_a_pack_error_rather_than_crashing(capsys, monkeypatch):
    def boom(**_kw):
        raise _mod.context_pack.PackError("no searchable term")

    monkeypatch.setattr(_mod.context_pack, "build", boom)
    assert _mod.main([]) == 1
    assert "context_pack refused a case" in capsys.readouterr().err


def test_an_empty_corpus_is_an_error_not_a_clean_run(tmp_path, monkeypatch):
    """Zero cases scoring zero breaches would report a passing gate over nothing."""
    empty = tmp_path / "corpus"
    empty.mkdir()
    monkeypatch.setattr(_mod, "CORPUS", empty)
    with pytest.raises(_mod.BenchError, match="no cases under"):
        _mod.load_cases()


def test_cli_exits_one_and_names_the_misses_when_a_threshold_breaks(capsys, monkeypatch):
    """The red path, exercised — a benchmark that cannot go red gates nothing."""
    real = _mod.score_case
    monkeypatch.setattr(
        _mod,
        "score_case",
        lambda case, budget: (
            real(case, budget) | {"hit": False, "rank": 0, "reciprocal_rank": 0.0, "precision": 0.0}
        ),
    )
    assert _mod.main([]) == 1
    err = capsys.readouterr().err
    assert "FAIL" in err
    assert "recall_at_5" in err
    assert "missed: python-command-injection" in err
    # Every corpus case is gated, so a forced miss names all of them. The
    # known-limitation exemption is exercised on synthetic rows in
    # `test_aggregate_excludes_known_limitations_from_the_score` — asserting it
    # here would re-couple this test to whichever corpus case happens to be the
    # hard one, which is what broke when construct matching reached
    # `ts-type-escape` and its marker came off.
    assert "missed: ts-type-escape" in err


# A goal matching a line OUTSIDE the expected range: the scan runs to the end of
# the candidate list without ever overlapping. Distinct from a goal matching
# nothing at all, which produces no candidates and never enters the loop.
#
# Long enough that the match and the answer cannot land in one candidate. With
# no enclosing symbol, `_range_for` falls back to a window of the matched line
# +/-8, so a four-line fixture put line 1 and line 3 in the same range and
# scored a hit — the fixture, not the scan, was doing the overlapping.
_MISS_SOURCE = (
    "alpha = 1\n" + "".join(f"filler_{n} = {n}\n" for n in range(2, 25)) + "TARGET = 25\n"
)


def test_a_case_whose_candidates_never_overlap_scores_as_a_miss(tmp_path, monkeypatch):
    """The scan must fall out of the loop, not off the end of the first candidate.

    Every shipped corpus case hits, so this path is unreachable from the real
    corpus — and it was, until `ts-type-escape` stopped being the exception.
    A benchmark whose miss path is never exercised cannot be trusted to report
    one.
    """
    _one_case(tmp_path, monkeypatch, _MISS_SOURCE, "alpha", [25, 25])
    row = _mod.score_case(_mod.load_cases()[0], 4000)
    assert row["hit"] is False
    assert row["rank"] == 0
    assert row["noise_tokens"] > 0, "the non-overlapping candidate should still count as noise"


def test_a_known_limitation_miss_is_named_nowhere_in_the_failure_report(
    tmp_path, monkeypatch, capsys
):
    """A marked case is excluded from the score AND from the miss list.

    Both halves matter and they are separate code. Excluding it from the score
    but still printing `missed:` would report a failure the run deliberately
    accepted; printing nothing while averaging it in would drag every floor
    down to meet it.

    The run still goes red here — a corpus of one marked case leaves nothing
    gated, so the aggregate breaches. That is the point: the report must go red
    without naming a case that was never expected to hit.
    """
    _one_case(
        tmp_path, monkeypatch, _MISS_SOURCE, "alpha", [25, 25], known_limitation="no signature"
    )
    assert _mod.main([]) == 1
    err = capsys.readouterr().err
    assert "FAIL" in err
    assert "missed:" not in err


def test_cli_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        _mod.main(["--help"])
    assert exc.value.code == 0
    assert "bench-retrieval" in capsys.readouterr().out


def test_module_runs_as_a_script(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bench-retrieval.py"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0
    assert "recall@5=" in capsys.readouterr().out
