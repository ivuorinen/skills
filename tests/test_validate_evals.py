"""Tests for scripts/validate-evals.py."""

import importlib.util
import json
import re
import runpy
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "validate-evals.py"
_spec = importlib.util.spec_from_file_location("validate_evals", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _has(errors: list[str], fragment: str) -> bool:
    return any(fragment in e for e in errors)


def _skill(tmp_path: Path, name: str = "my-skill") -> Path:
    d = tmp_path / name
    (d / "evals").mkdir(parents=True, exist_ok=True)
    return d


def _write(skill_dir: Path, filename: str, data) -> Path:
    path = skill_dir / "evals" / filename
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


VALID_CASE = {
    "id": 1,
    "prompt": "audit this repo",
    "expected_output": "findings filed with severities",
    "assertions": ["a finding names a file and line"],
}

VALID_QUERIES = [
    {"query": "audit this repo", "should_trigger": True, "split": "train"},
    {"query": "write me a poem", "should_trigger": False, "split": "train"},
    {"query": "find every bug in here", "should_trigger": True, "split": "validation"},
    {"query": "what is a mutex", "should_trigger": False, "split": "validation"},
]


def _evals(tmp_path: Path, data, name: str = "my-skill") -> list[str]:
    skill = _skill(tmp_path, name)
    path = _write(skill, "evals.json", data)
    errors: list[str] = []
    _mod.validate_evals(path, name, errors)
    return errors


def _triggers(tmp_path: Path, data, name: str = "my-skill") -> list[str]:
    skill = _skill(tmp_path, name)
    path = _write(skill, "trigger-queries.json", data)
    errors: list[str] = []
    _mod.validate_trigger_queries(path, name, errors)
    return errors


class TestLoad:
    def test_unreadable_file_errors(self, tmp_path):
        errors: list[str] = []
        assert _mod._load(tmp_path / "missing.json", errors) is None
        assert errors

    def test_malformed_json_errors(self, tmp_path):
        skill = _skill(tmp_path)
        path = _write(skill, "evals.json", "{not json")
        errors: list[str] = []
        assert _mod._load(path, errors) is None
        assert errors

    def test_non_object_top_level_errors(self, tmp_path):
        skill = _skill(tmp_path)
        path = _write(skill, "evals.json", [1, 2])
        errors: list[str] = []
        assert _mod._load(path, errors) is None
        assert _has(errors, "must be a JSON object")


class TestValidateEvals:
    def test_valid_set_has_no_errors(self, tmp_path):
        assert _evals(tmp_path, {"skill_name": "my-skill", "evals": [VALID_CASE]}) == []

    def test_unreadable_file_short_circuits(self, tmp_path):
        errors: list[str] = []
        _mod.validate_evals(tmp_path / "nope.json", "my-skill", errors)
        assert errors

    def test_skill_name_mismatch_errors(self, tmp_path):
        errors = _evals(tmp_path, {"skill_name": "other", "evals": [VALID_CASE]})
        assert _has(errors, "must be 'my-skill'")

    def test_empty_evals_list_errors(self, tmp_path):
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": []})
        assert _has(errors, "non-empty list")

    def test_non_object_case_errors(self, tmp_path):
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": ["nope"]})
        assert _has(errors, "must be an object")

    def test_missing_id_errors(self, tmp_path):
        case = {k: v for k, v in VALID_CASE.items() if k != "id"}
        assert _has(_evals(tmp_path, {"skill_name": "my-skill", "evals": [case]}), "missing 'id'")

    def test_duplicate_id_errors(self, tmp_path):
        data = {"skill_name": "my-skill", "evals": [VALID_CASE, dict(VALID_CASE)]}
        assert _has(_evals(tmp_path, data), "duplicate eval id")

    def test_non_scalar_id_reports_a_diagnostic_not_a_traceback(self, tmp_path):
        # An unhashable id used to raise TypeError on the set membership test,
        # replacing every remaining diagnostic with a stack trace.
        case = {**VALID_CASE, "id": [1, 2]}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, "id must be a string or integer; got list")

    def test_boolean_id_rejected(self, tmp_path):
        # bool subclasses int, so True would otherwise pass as a valid id.
        case = {**VALID_CASE, "id": True}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, "id must be a string or integer; got bool")

    @pytest.mark.parametrize("field", ["prompt", "expected_output"])
    def test_empty_required_field_errors(self, tmp_path, field):
        case = {**VALID_CASE, field: "   "}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, f"empty '{field}'")

    def test_missing_assertions_errors(self, tmp_path):
        case = {k: v for k, v in VALID_CASE.items() if k != "assertions"}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, "at least one assertion")

    def test_empty_assertion_string_errors(self, tmp_path):
        case = {**VALID_CASE, "assertions": [" "]}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, "empty assertion")

    @pytest.mark.parametrize("bad", [None, 3, "notalist", {"a": 1}])
    def test_non_list_files_reports_a_diagnostic_not_a_traceback(self, tmp_path, bad):
        case = {**VALID_CASE, "files": bad}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, "'files' must be a list")

    @pytest.mark.parametrize("bad", [1, None, "   ", ["nested"]])
    def test_non_string_file_reference_errors(self, tmp_path, bad):
        case = {**VALID_CASE, "files": [bad]}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, "not a non-empty string")

    def test_missing_input_file_errors(self, tmp_path):
        case = {**VALID_CASE, "files": ["evals/files/absent.csv"]}
        errors = _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]})
        assert _has(errors, "missing input file")

    def test_present_input_file_passes(self, tmp_path):
        skill = _skill(tmp_path)
        (skill / "evals" / "sample.csv").write_text("a,b\n", encoding="utf-8")
        case = {**VALID_CASE, "files": ["evals/sample.csv"]}
        assert _evals(tmp_path, {"skill_name": "my-skill", "evals": [case]}) == []


class TestValidateTriggerQueries:
    def test_valid_set_has_no_errors(self, tmp_path):
        assert _triggers(tmp_path, {"skill_name": "my-skill", "queries": VALID_QUERIES}) == []

    def test_unreadable_file_short_circuits(self, tmp_path):
        errors: list[str] = []
        _mod.validate_trigger_queries(tmp_path / "nope.json", "my-skill", errors)
        assert errors

    def test_skill_name_mismatch_errors(self, tmp_path):
        errors = _triggers(tmp_path, {"skill_name": "other", "queries": VALID_QUERIES})
        assert _has(errors, "must be 'my-skill'")

    @pytest.mark.parametrize("bad", [0, 1, 1.5, "half"])
    def test_threshold_outside_range_errors(self, tmp_path, bad):
        data = {"skill_name": "my-skill", "threshold": bad, "queries": VALID_QUERIES}
        assert _has(_triggers(tmp_path, data), "threshold must be between 0 and 1")

    def test_empty_queries_errors(self, tmp_path):
        errors = _triggers(tmp_path, {"skill_name": "my-skill", "queries": []})
        assert _has(errors, "non-empty list")

    def test_non_object_query_errors(self, tmp_path):
        data = {"skill_name": "my-skill", "queries": [*VALID_QUERIES, "nope"]}
        assert _has(_triggers(tmp_path, data), "must be an object")

    def test_empty_query_text_errors(self, tmp_path):
        bad = {"query": "  ", "should_trigger": True, "split": "train"}
        data = {"skill_name": "my-skill", "queries": [*VALID_QUERIES, bad]}
        assert _has(_triggers(tmp_path, data), "empty 'query'")

    def test_non_boolean_label_errors(self, tmp_path):
        bad = {"query": "x", "should_trigger": "yes", "split": "train"}
        data = {"skill_name": "my-skill", "queries": [*VALID_QUERIES, bad]}
        assert _has(_triggers(tmp_path, data), "boolean 'should_trigger'")

    def test_unknown_split_errors(self, tmp_path):
        bad = {"query": "x", "should_trigger": True, "split": "holdout"}
        data = {"skill_name": "my-skill", "queries": [*VALID_QUERIES, bad]}
        assert _has(_triggers(tmp_path, data), "split must be one of")

    def test_split_with_only_positives_errors(self, tmp_path):
        # A split holding one label cannot measure both failure modes.
        queries = [q for q in VALID_QUERIES if q["should_trigger"] or q["split"] == "validation"]
        data = {"skill_name": "my-skill", "queries": queries}
        assert _has(_triggers(tmp_path, data), "both should_trigger true and false")


class TestValidateSkillEvals:
    def test_skill_without_evals_dir_checks_nothing(self, tmp_path):
        errors: list[str] = []
        assert _mod.validate_skill_evals(tmp_path / "bare", errors) is False
        assert errors == []

    def test_both_files_are_checked(self, tmp_path):
        skill = _skill(tmp_path)
        _write(skill, "evals.json", {"skill_name": "my-skill", "evals": [VALID_CASE]})
        _write(skill, "trigger-queries.json", {"skill_name": "my-skill", "queries": VALID_QUERIES})
        errors: list[str] = []
        assert _mod.validate_skill_evals(skill, errors) is True
        assert errors == []


class TestMain:
    @pytest.mark.parametrize("flag", ["--help", "-h"])
    def test_help_prints_usage(self, flag, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["prog", flag])
        _mod.main()
        assert "Usage:" in capsys.readouterr().out

    def test_explicit_dir_valid_exits_zero(self, tmp_path, monkeypatch, capsys):
        skill = _skill(tmp_path)
        _write(skill, "evals.json", {"skill_name": "my-skill", "evals": [VALID_CASE]})
        monkeypatch.setattr(sys, "argv", ["prog", str(skill)])
        _mod.main()
        assert "OK  1 eval set(s) validated." in capsys.readouterr().out

    def test_explicit_dir_invalid_exits_one(self, tmp_path, monkeypatch, capsys):
        skill = _skill(tmp_path)
        _write(skill, "evals.json", {"skill_name": "my-skill", "evals": []})
        monkeypatch.setattr(sys, "argv", ["prog", str(skill)])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        assert "Fix before committing." in capsys.readouterr().out

    def test_no_args_discovers_the_repo_eval_sets(self, monkeypatch, capsys):
        # Assert a positive count: the success line contains the same substring
        # for zero sets, so a bare substring check passes when discovery breaks.
        monkeypatch.setattr(sys, "argv", ["prog"])
        _mod.main()
        out = capsys.readouterr().out
        m = re.match(r"OK  (\d+) eval set\(s\) validated\.", out.strip())
        assert m, out
        assert int(m.group(1)) >= 1, "no eval sets discovered in the repo"

    def test_explicit_path_without_evals_exits_one(self, tmp_path, monkeypatch, capsys):
        # A typo'd or moved path must fail loudly, not report a clean zero.
        (tmp_path / "bare").mkdir()
        monkeypatch.setattr(sys, "argv", ["prog", str(tmp_path / "bare")])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        assert "must be a skill directory" in capsys.readouterr().err

    def test_one_valid_and_one_missing_path_still_exits_one(self, tmp_path, monkeypatch, capsys):
        # Summing the per-path results would hide the typo'd path behind the
        # valid one and exit 0 on a non-zero total.
        good = _skill(tmp_path, "my-skill")
        _write(good, "evals.json", {"skill_name": "my-skill", "evals": [VALID_CASE]})
        (tmp_path / "bare").mkdir()
        monkeypatch.setattr(sys, "argv", ["prog", str(good), str(tmp_path / "bare")])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "bare" in err and "must be a skill directory" in err

    def test_no_args_with_no_eval_sets_stays_zero(self, monkeypatch, capsys):
        # The no-argument sweep is allowed to find nothing.
        monkeypatch.setattr(sys, "argv", ["prog"])
        monkeypatch.setattr(_mod.Path, "glob", lambda self, pat: iter(()))
        _mod.main()
        assert "OK  0 eval set(s) validated." in capsys.readouterr().out

    def test_module_entrypoint(self, monkeypatch, capsys):
        """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
        monkeypatch.setattr(sys, "argv", ["prog", "--help"])
        runpy.run_path(str(_TOOL), run_name="__main__")
        assert "Usage:" in capsys.readouterr().out
