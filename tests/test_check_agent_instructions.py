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
        assert sorted(names) == ["AGENTS.md", "CLAUDE.md", "a.md"]

    def test_absent_files_are_skipped(self, tmp_path):
        _workspace(tmp_path, claude="# C\n")
        assert [p.name for p in _mod.loaded_files(tmp_path)] == ["CLAUDE.md"]

    def test_one_file_matched_by_two_patterns_is_counted_once(self, tmp_path, monkeypatch):
        """No shipped pattern pair overlaps today, so this pins the contract
        rather than a current behaviour: the next entry added to _HARNESSES must
        not be able to double a file's instructions into the shared budget.
        """
        monkeypatch.setattr(_mod, "_HARNESSES", {"A": ("R.md", "*.md"), "B": ("R.md",)})
        (tmp_path / "R.md").write_text("# R\n\n- Never do the bad thing.\n", encoding="utf-8")

        assert [p.name for p in _mod.loaded_files(tmp_path)] == ["R.md"]
        assert _mod.check(tmp_path)[0]["total_instructions"] == 1


class TestHarnessCoverage:
    """This tool audits somebody else's repo, so it may not assume their agent.

    A file set hardcoded to Claude Code answered "not an agent workspace" for
    every one of the harnesses below — telling a user their agent config was not
    agent config, which is the one answer that is never useful.
    """

    @pytest.mark.parametrize(
        ("harness", "rel"),
        [
            ("Claude Code", "CLAUDE.md"),
            ("Claude Code", ".claude/rules/a.md"),
            ("Cursor", ".cursorrules"),
            ("Cursor", ".cursor/rules/main.mdc"),
            ("GitHub Copilot", ".github/copilot-instructions.md"),
            ("GitHub Copilot", ".github/instructions/py.instructions.md"),
            ("Gemini CLI", "GEMINI.md"),
            ("Windsurf", ".windsurfrules"),
            ("Cline", ".clinerules"),
            ("Zed", ".rules"),
            ("Aider", "CONVENTIONS.md"),
            ("Continue", ".continuerules"),
            ("cross-agent", "AGENTS.md"),
        ],
    )
    def test_each_harness_is_audited_from_its_own_file(self, tmp_path, harness, rel):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("# R\n\n- Never do the bad thing.\n", encoding="utf-8")

        report, _ = _mod.check(tmp_path)
        assert report["harnesses"] == [harness]
        assert report["total_instructions"] == 1

    def test_a_repo_serving_several_agents_counts_one_shared_budget(self, tmp_path):
        """Files for different agents still compete for one window, so the
        budget is the union rather than a per-harness tally."""
        for rel in ("CLAUDE.md", "AGENTS.md", ".cursorrules"):
            (tmp_path / rel).write_text("# R\n\n- Never do the bad thing.\n", encoding="utf-8")

        report, _ = _mod.check(tmp_path)
        assert report["harnesses"] == ["Claude Code", "Cursor", "cross-agent"]
        assert report["total_instructions"] == 3

    def test_a_directory_named_like_an_instruction_file_is_not_one(self, tmp_path):
        """`.rules/` as a directory is not Zed's `.rules` file. Globbing without
        the is_file() test would hand a directory to read_text()."""
        (tmp_path / ".rules").mkdir()
        (tmp_path / "CLAUDE.md").write_text("# C\n", encoding="utf-8")

        assert _mod.check(tmp_path)[0]["harnesses"] == ["Claude Code"]


class TestDuplicateGrading:
    """A duplicate is graded by whether one session ever holds both copies."""

    def test_two_files_of_one_harness_contradict_each_other(self, tmp_path):
        line = "- Never commit a credential to this repository, ever.\n"
        _workspace(tmp_path, claude="# C\n\n" + line, rules={"a.md": "# R\n\n" + line})

        f = next(
            x for x in _mod.check(tmp_path)[0]["findings"] if x["code"] == "cross_file_duplicate"
        )
        assert f["severity"] == "Medium"
        assert "single session" in f["detail"]

    def test_a_mirror_for_another_agent_is_drift_not_contradiction(self, tmp_path):
        """.github/copilot-instructions.md exists *because* Copilot does not read
        CLAUDE.md. Calling that one window holding two competing rules states
        something false about a duplication that is deliberate."""
        line = "- Never commit a credential to this repository, ever.\n"
        (tmp_path / "CLAUDE.md").write_text("# C\n\n" + line, encoding="utf-8")
        copilot = tmp_path / ".github" / "copilot-instructions.md"
        copilot.parent.mkdir(parents=True)
        copilot.write_text("# C\n\n" + line, encoding="utf-8")

        f = next(
            x for x in _mod.check(tmp_path)[0]["findings"] if x["code"] == "cross_file_duplicate"
        )
        assert f["severity"] == "Low"
        assert "no session holds both" in f["detail"]

    def test_agents_md_co_loads_with_every_harness(self, tmp_path):
        """The exception in the other direction: near enough every agent reads
        AGENTS.md, so a duplicate against it is a real same-session conflict."""
        line = "- Never commit a credential to this repository, ever.\n"
        (tmp_path / "AGENTS.md").write_text("# A\n\n" + line, encoding="utf-8")
        (tmp_path / ".cursorrules").write_text("# C\n\n" + line, encoding="utf-8")

        f = next(
            x for x in _mod.check(tmp_path)[0]["findings"] if x["code"] == "cross_file_duplicate"
        )
        assert f["severity"] == "Medium"


class TestImports:
    """`@path.md` imports are pulled in as though pasted at that point, and a
    target that does not resolve is skipped in silence — the author sees the rule
    referenced in their own file and never learns it was never loaded."""

    def _codes(self, tmp_path):
        return [f["code"] for f in _mod.check(tmp_path)[0]["findings"] if "import" in f["code"]]

    def test_a_missing_target_blocks(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text(
            "# C\n\nSee @docs/missing.md for the rest.\n", encoding="utf-8"
        )
        report, blocking = _mod.check(tmp_path)

        f = next(x for x in report["findings"] if x["code"] == "dangling_import")
        assert f["severity"] == "High"
        assert blocking is True, "a rule that silently never loads is not a warning"

    def test_a_resolving_import_is_not_a_finding(self, tmp_path):
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "extra.md").write_text(
            "# E\n\n- Always run tests.\n", encoding="utf-8"
        )
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@docs/extra.md\n", encoding="utf-8")

        assert self._codes(tmp_path) == []

    def test_an_import_inside_an_imported_file_is_followed(self, tmp_path):
        """The defect one level down is the same defect, and the file holding it
        is not in the always-loaded set — nothing else would ever read it."""
        (tmp_path / "a.md").write_text("# A\n\n@missing.md\n", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@a.md\n", encoding="utf-8")

        f = next(x for x in _mod.check(tmp_path)[0]["findings"] if x["code"] == "dangling_import")
        assert f["file"] == "a.md"

    def test_a_cycle_is_reported_once_at_the_closing_edge(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@a.md\n", encoding="utf-8")
        (tmp_path / "a.md").write_text("# A\n\n@b.md\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n\n@a.md\n", encoding="utf-8")

        assert self._codes(tmp_path) == ["circular_import"]

    def test_one_cycle_named_twice_is_reported_once(self, tmp_path):
        """Repeating the same import on two lines is one cycle, not two. Keyed on
        the line instead of the edge, a file that references its partner several
        times would report the same loop once per mention."""
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@a.md\n", encoding="utf-8")
        (tmp_path / "a.md").write_text("# A\n\n@b.md\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n\n@a.md\n\nand again @a.md\n", encoding="utf-8")

        assert self._codes(tmp_path) == ["circular_import"]

    def test_a_diamond_is_not_a_cycle(self, tmp_path):
        """Two files importing one third is ordinary sharing. Reporting it would
        make the check unusable on any repo that factors its rules out."""
        (tmp_path / "shared.md").write_text("# S\n\n- Never skip the gate.\n", encoding="utf-8")
        for name in ("a.md", "b.md"):
            (tmp_path / name).write_text(f"# {name}\n\n@shared.md\n", encoding="utf-8")
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@a.md\n\n@b.md\n", encoding="utf-8")

        assert self._codes(tmp_path) == []

    def _chain(self, tmp_path, length):
        """CLAUDE.md -> l1 -> ... -> l<length>, each importing the next."""
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@l1.md\n", encoding="utf-8")
        for i in range(1, length):
            (tmp_path / f"l{i}.md").write_text(f"# L{i}\n\n@l{i + 1}.md\n", encoding="utf-8")
        (tmp_path / f"l{length}.md").write_text("# L\n\n- Never do it.\n", encoding="utf-8")

    def test_a_chain_past_the_harness_limit_is_reported(self, tmp_path):
        """The sixth file is not reported as skipped by the harness — it simply
        never arrives, the same silence as a dangling target one hop further."""
        self._chain(tmp_path, 6)

        f = next(x for x in _mod.check(tmp_path)[0]["findings"] if x["code"] == "import_too_deep")
        assert f["file"] == "l6.md"
        assert "CLAUDE.md → l1.md" in f["detail"], "the chain must name how it got there"

    def test_a_chain_at_the_limit_is_not_reported(self, tmp_path):
        self._chain(tmp_path, 5)
        assert "import_too_deep" not in self._codes(tmp_path)

    def test_depth_does_not_double_report_a_shared_deep_file(self, tmp_path):
        """Two chains reaching the same too-deep file are one problem with that
        file, not two."""
        self._chain(tmp_path, 6)
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@l1.md\n\n@alt.md\n", encoding="utf-8")
        (tmp_path / "alt.md").write_text("# A\n\n@l2.md\n", encoding="utf-8")

        assert self._codes(tmp_path).count("import_too_deep") == 1

    def test_a_cycle_is_not_also_reported_as_too_deep(self, tmp_path):
        """Walking a cycle would recurse until the depth limit tripped, turning
        one circular_import into a depth finding as well."""
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@a.md\n", encoding="utf-8")
        (tmp_path / "a.md").write_text("# A\n\n@b.md\n", encoding="utf-8")
        (tmp_path / "b.md").write_text("# B\n\n@a.md\n", encoding="utf-8")

        assert self._codes(tmp_path) == ["circular_import"]

    def test_a_home_relative_import_is_left_alone(self, tmp_path):
        """`@~/rules.md` points outside the repository at whichever machine runs
        the agent, so its absence here says nothing about whether it resolves
        there — reporting it would be a guess dressed as a finding."""
        (tmp_path / "CLAUDE.md").write_text("# C\n\n@~/personal/rules.md\n", encoding="utf-8")
        assert self._codes(tmp_path) == []

    def test_an_import_outside_the_project_keeps_its_absolute_path(self, tmp_path):
        """A target above the root has no project-relative spelling, and inventing
        one with `..` would name a file the reader cannot locate."""
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "shared.md").write_text("# S\n\n@nope.md\n", encoding="utf-8")
        root = tmp_path / "repo"
        root.mkdir()
        (root / "CLAUDE.md").write_text("# C\n\n@../outside/shared.md\n", encoding="utf-8")

        f = next(x for x in _mod.check(root)[0]["findings"] if x["code"] == "dangling_import")
        assert f["file"] == str(outside / "shared.md")

    @pytest.mark.parametrize(
        "line",
        [
            "- Contact me@example.com about it.",
            "- Ask @ivuorinen for the token.",
            "- Install @types/node and @scope/pkg first.",
            "- The import syntax is `@some-rule.md` here.",
        ],
    )
    def test_an_at_sign_that_is_not_an_import_is_ignored(self, tmp_path, line):
        """Requiring the `.md` suffix, and stripping code spans, is what keeps
        this off ordinary prose — every line here carries an `@`."""
        (tmp_path / "CLAUDE.md").write_text(f"# C\n\n{line}\n", encoding="utf-8")
        assert self._codes(tmp_path) == []

    def test_a_fenced_import_is_a_code_sample(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# C\n\n```bash\n@fenced.md\n```\n", encoding="utf-8")
        assert self._codes(tmp_path) == []


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
        assert "no agent instruction file for any known harness" in capsys.readouterr().err

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
