"""Tests for skills/nitpicker/scripts/check-agent-instructions.py."""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

_TOOL = (
    Path(__file__).parent.parent
    / "skills"
    / "nitpicker"
    / "scripts"
    / "check-agent-instructions.py"
)
_spec = importlib.util.spec_from_file_location("check_agent_instructions", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _workspace(root: Path, claude: str = "", agents: str = "", rules: dict | None = None) -> Path:
    if claude:
        (root / "CLAUDE.md").write_text(claude, encoding="utf-8")
    if agents:
        (root / "AGENTS.md").write_text(agents, encoding="utf-8")
    for name, body in (rules or {}).items():
        d = root / ".claude" / "rules"
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(body, encoding="utf-8")
    return root


class TestInstructionCounting:
    def test_counts_list_items_and_imperatives_only(self, tmp_path):
        """Prose that mentions a rule is not a rule.

        The verb set is closed rather than "any sentence" because an open one
        counts narration, and the budget then measures prose volume instead of
        instruction load.
        """
        text = (
            "# Title\n\n"
            "- A bullet counts.\n"
            "1. A numbered item counts.\n"
            "Never do this — an imperative counts.\n"
            "This sentence merely describes the rule and does not count.\n"
        )
        assert _mod._count_instructions(text) == 3

    def test_fenced_code_tables_and_quotes_are_not_instructions(self, tmp_path):
        """A code sample is full of lines that look imperative and are not.

        Counting them would make any file with examples read as over budget,
        which is backwards: examples are what stop a rule needing more prose.
        """
        text = (
            "# T\n\n"
            "```bash\n- not a bullet\nNever run this\n```\n"
            "| col | col |\n"
            "> quoted line\n"
            "- one real bullet\n"
        )
        assert _mod._count_instructions(text) == 1

    def test_unclosed_fence_swallows_the_rest(self, tmp_path):
        """An unterminated fence must not silently re-enable counting.

        check-rules-anatomy.py flags the unterminated fence itself; here the
        safe reading is to count nothing after it rather than count a code
        sample as instructions.
        """
        text = "# T\n\n- counted\n```\n- inside an unclosed fence\nNever counted\n"
        assert _mod._count_instructions(text) == 1


class TestLoadedFiles:
    def test_finds_root_files_and_rules_without_duplicates(self, tmp_path):
        _workspace(tmp_path, claude="# C\n", agents="# A\n", rules={"a.md": "# R\n"})
        names = [p.name for p in _mod.loaded_files(tmp_path)]
        assert names == ["CLAUDE.md", "AGENTS.md", "a.md"]

    def test_absent_files_are_skipped(self, tmp_path):
        _workspace(tmp_path, claude="# C\n")
        assert [p.name for p in _mod.loaded_files(tmp_path)] == ["CLAUDE.md"]


class TestBudget:
    def test_over_the_limit_blocks(self, tmp_path):
        """The budget is the one finding here graded High, because it is the one
        with a hard number behind it rather than a judgement."""
        body = "# C\n\n" + "".join(f"- Rule {i}.\n" for i in range(160))
        _workspace(tmp_path, claude=body)
        report, blocking = _mod.check(tmp_path)

        assert blocking is True
        f = next(x for x in report["findings"] if x["code"] == "instruction_budget")
        assert f["severity"] == "High"
        assert report["total_instructions"] == 160

    def test_warn_band_reports_without_blocking(self, tmp_path):
        body = "# C\n\n" + "".join(f"- Rule {i}.\n" for i in range(120))
        _workspace(tmp_path, claude=body)
        report, blocking = _mod.check(tmp_path)

        assert blocking is False
        f = next(x for x in report["findings"] if x["code"] == "instruction_budget")
        assert f["severity"] == "Low"

    def test_under_the_warn_band_is_silent(self, tmp_path):
        _workspace(tmp_path, claude="# C\n\n- One rule.\n")
        report, _ = _mod.check(tmp_path)
        assert not [x for x in report["findings"] if x["code"] == "instruction_budget"]


class TestPositionRisk:
    def test_catches_a_plain_bullet_rule_mid_file(self, tmp_path):
        """AGENTS.md states every rule as a plain bullet.

        An earlier cut required a heading or a bolded lead-in, which made that
        file structurally exempt from the check written for it — position is
        about where a rule sits, and decoration is only how a file spells it.
        """
        filler = ["Filler line of ordinary prose."] * 30
        body = "\n".join(["# A", "", *filler, "- Never read the agents directory.", *filler])
        _workspace(tmp_path, agents=body + "\n")
        report, _ = _mod.check(tmp_path)

        hits = [x for x in report["findings"] if x["code"] == "position_risk"]
        assert len(hits) == 1
        assert "Never read the agents directory" in hits[0]["detail"]

    def test_ignores_short_files_and_the_edges(self, tmp_path):
        _workspace(tmp_path, agents="# A\n\n- Never do it.\n\nBody.\n")
        report, _ = _mod.check(tmp_path)
        assert not [x for x in report["findings"] if x["code"] == "position_risk"]

        filler = ["Filler."] * 60
        _workspace(tmp_path, agents="\n".join(["- Never do it.", "", *filler]) + "\n")
        report, _ = _mod.check(tmp_path)
        assert not [x for x in report["findings"] if x["code"] == "position_risk"], (
            "a rule at the very top is not buried"
        )

    def test_rules_directory_is_left_to_the_other_tool(self, tmp_path):
        """Two tools scoring one file under different definitions would disagree,
        and the author would have no way to tell which answer was the contract."""
        filler = ["Filler line of ordinary prose."] * 30
        body = "\n".join(["# R", "", *filler, "- Never do the thing.", *filler]) + "\n"
        _workspace(tmp_path, claude="# C\n", rules={"long.md": body})
        report, _ = _mod.check(tmp_path)

        assert not [x for x in report["findings"] if x["code"] == "position_risk"]

    def test_prose_mentioning_a_directive_is_not_a_rule_statement(self, tmp_path):
        assert _mod._is_rule_statement("- Never do it.")
        assert _mod._is_rule_statement("## Never do it")
        assert _mod._is_rule_statement("- **Never** do it.")
        assert not _mod._is_rule_statement("The rule says you should never do it.")


class TestCrossFileDuplicate:
    def test_same_line_in_two_files_is_reported(self, tmp_path):
        dup = "Never hand-edit the ledger because it is append-only and permanent.\n"
        _workspace(tmp_path, claude="# C\n\n" + dup, agents="# A\n\n" + dup)
        report, _ = _mod.check(tmp_path)

        hits = [x for x in report["findings"] if x["code"] == "cross_file_duplicate"]
        assert len(hits) == 1
        assert hits[0]["severity"] == "Medium"
        assert "CLAUDE.md" in hits[0]["detail"]

    def test_repeat_within_one_file_is_not_this_checks_business(self, tmp_path):
        """check-rules-anatomy.py owns the within-file case as `duplicate_line`."""
        dup = "Never hand-edit the ledger because it is append-only and permanent.\n"
        _workspace(tmp_path, claude="# C\n\n" + dup + dup)
        report, _ = _mod.check(tmp_path)
        assert not [x for x in report["findings"] if x["code"] == "cross_file_duplicate"]

    def test_short_lines_do_not_count(self, tmp_path):
        _workspace(tmp_path, claude="# C\n\nBe brief.\n", agents="# A\n\nBe brief.\n")
        report, _ = _mod.check(tmp_path)
        assert not [x for x in report["findings"] if x["code"] == "cross_file_duplicate"]


class TestCli:
    def test_help_prints_usage_before_resolving_a_path(self, capsys, monkeypatch):
        """--help must answer even where the positional would fail to resolve."""
        monkeypatch.setattr(sys, "argv", ["check-agent-instructions.py", "--help"])
        _mod.main()
        assert "check-agent-instructions.py" in capsys.readouterr().out

    def test_too_many_arguments_is_a_usage_error(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["x", "a", "b"])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 2
        assert "Usage:" in capsys.readouterr().err

    def test_a_root_with_no_agent_files_fails_loudly(self, tmp_path, capsys, monkeypatch):
        """Returning an empty clean report would present "nothing to check" as
        "nothing wrong" — the defect family this repo keeps finding."""
        monkeypatch.setattr(sys, "argv", ["x", str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        assert "not an agent workspace" in capsys.readouterr().err

    def test_unreadable_file_exits_one_rather_than_tracebacking(
        self, tmp_path, capsys, monkeypatch
    ):
        _workspace(tmp_path, claude="# C\n")
        monkeypatch.setattr(sys, "argv", ["x", str(tmp_path)])

        def _boom(self, *a, **k):
            """Simulate a file that exists at scan time and cannot be read at use."""
            raise OSError("denied")

        monkeypatch.setattr(Path, "read_text", _boom)
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        assert "cannot read" in capsys.readouterr().err

    def test_clean_workspace_exits_zero_with_json(self, tmp_path, capsys, monkeypatch):
        _workspace(tmp_path, claude="# C\n\n- One rule.\n")
        monkeypatch.setattr(sys, "argv", ["x", str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 0
        assert json.loads(capsys.readouterr().out)["total_instructions"] == 1

    def test_blocking_workspace_exits_one(self, tmp_path, capsys, monkeypatch):
        _workspace(tmp_path, claude="# C\n\n" + "".join(f"- Rule {i}.\n" for i in range(160)))
        monkeypatch.setattr(sys, "argv", ["x", str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        assert json.loads(capsys.readouterr().out)["summary"]["blocking"] is True

    def test_runs_as_a_script(self, tmp_path, capsys, monkeypatch):
        """`python3 check-agent-instructions.py` is the documented invocation."""
        _workspace(tmp_path, claude="# C\n\n- One rule.\n")
        monkeypatch.setattr(sys, "argv", ["check-agent-instructions.py", str(tmp_path)])
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(_TOOL), run_name="__main__")
        assert exc.value.code == 0
        assert "total_instructions" in capsys.readouterr().out
