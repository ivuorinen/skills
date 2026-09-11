"""Tests for skills/nitpicker/scripts/check-context-tokens.py.

The contract under test is narrow and deliberate: the tool reports and never
gates. A test suite that only checked the numbers would let a future change add
a threshold exit without failing anything, so the "always exit 0 on a large
number" property is pinned explicitly.
"""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

_TOOL = (
    Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "check-context-tokens.py"
)
_spec = importlib.util.spec_from_file_location("check_context_tokens", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]


def _project(root: Path, *, rules: int = 2, command: str = "audit") -> Path:
    """A minimal project with an always-loaded set and one nitpicker-shaped skill."""
    (root / "CLAUDE.md").write_text("# c\n" + "x" * 100, encoding="utf-8")
    (root / "AGENTS.md").write_text("# a\n" + "y" * 40, encoding="utf-8")
    rules_dir = root / ".claude" / "rules"
    rules_dir.mkdir(parents=True)
    for i in range(rules):
        (rules_dir / f"r{i}.md").write_text(f"# r{i}\n" + "z" * 20, encoding="utf-8")
    commands = root / "skills" / "nitpicker" / "commands"
    commands.mkdir(parents=True)
    (root / "skills" / "nitpicker" / "SKILL.md").write_text("# s\n" + "s" * 200, encoding="utf-8")
    (commands / "_conventions.md").write_text("# conv\n" + "c" * 80, encoding="utf-8")
    (commands / f"{command}.md").write_text("# cmd\n" + "m" * 60, encoding="utf-8")
    return root


def test_estimate_tokens_rounds_up():
    assert _mod.estimate_tokens("") == 0
    assert _mod.estimate_tokens("abcde") == 2


def test_always_loaded_collects_the_named_files_and_every_rule(tmp_path):
    root = _project(tmp_path, rules=3)
    paths = {row["path"] for row in _mod.always_loaded(root)}
    assert paths == {"CLAUDE.md", "AGENTS.md"} | {f".claude/rules/r{i}.md" for i in range(3)}


def test_always_loaded_ignores_a_stray_markdown_file_beside_claude_md(tmp_path):
    """The set is a convention, not a directory listing.

    Globbing the repo root would count a README as always-loaded and report a
    budget nobody actually pays.
    """
    root = _project(tmp_path)
    (root / "README.md").write_text("# not loaded\n", encoding="utf-8")
    assert "README.md" not in {row["path"] for row in _mod.always_loaded(root)}


def test_invocation_counts_router_conventions_and_the_command_only(tmp_path):
    root = _project(tmp_path)
    paths = [row["path"] for row in _mod.invocation(root, "nitpicker", "audit")]
    assert paths == [
        "skills/nitpicker/SKILL.md",
        "skills/nitpicker/commands/_conventions.md",
        "skills/nitpicker/commands/audit.md",
    ]


def test_invocation_excludes_conditional_protocols(tmp_path):
    """A protocol that loads on a trigger is not part of the invocation floor.

    Counting `_committing.md` here would report a cost a run that creates no
    commit never pays, which is the whole point of having split it out.
    """
    root = _project(tmp_path)
    (root / "skills/nitpicker/commands/_committing.md").write_text("# x\n", encoding="utf-8")
    paths = [row["path"] for row in _mod.invocation(root, "nitpicker", "audit")]
    assert "skills/nitpicker/commands/_committing.md" not in paths


def test_invocation_counts_a_protocol_whose_trigger_is_the_command_itself(tmp_path):
    """audit-1722c3a9: `_audit-coverage.md` was excluded as "conditional".

    Its trigger is `audit` at run start, mandatorily — so for the default
    command it is not conditional at all, and omitting it understated that
    command's floor by roughly a fifth while crediting the conventions split
    with a saving it does not take.
    """
    root = _project(tmp_path)
    coverage = root / "skills/nitpicker/commands/_audit-coverage.md"
    coverage.write_text("# cov\n" + "v" * 400, encoding="utf-8")
    paths = [row["path"] for row in _mod.invocation(root, "nitpicker", "audit")]
    assert paths == [
        "skills/nitpicker/SKILL.md",
        "skills/nitpicker/commands/_conventions.md",
        "skills/nitpicker/commands/_audit-coverage.md",
        "skills/nitpicker/commands/audit.md",
    ]


def test_a_per_command_protocol_is_not_counted_for_another_command(tmp_path):
    """`review` never loads the audit coverage checklist, so it must not pay for it."""
    root = _project(tmp_path, command="review")
    (root / "skills/nitpicker/commands/_audit-coverage.md").write_text("# cov\n", encoding="utf-8")
    paths = [row["path"] for row in _mod.invocation(root, "nitpicker", "review")]
    assert "skills/nitpicker/commands/_audit-coverage.md" not in paths


def test_the_per_command_protocol_map_matches_the_conventions_trigger_table(tmp_path):
    """The map is keyed by hand, so this is what stops it drifting from the docs.

    `_conventions.md` states each protocol's trigger in prose; nothing parses
    prose, so the assertion is that the two agree on the one entry the default
    command depends on.
    """
    assert _mod._ALWAYS_FOR["audit"] == ("_audit-coverage.md",)
    conventions = (
        Path(__file__).parent.parent / "skills" / "nitpicker" / "commands" / "_conventions.md"
    ).read_text(encoding="utf-8")
    assert "`_audit-coverage` | `audit` only, at run start" in conventions


def test_invocation_works_without_a_conventions_file(tmp_path):
    root = _project(tmp_path)
    (root / "skills/nitpicker/commands/_conventions.md").unlink()
    assert len(_mod.invocation(root, "nitpicker", "audit")) == 2


def test_invocation_finds_a_skill_under_dot_claude(tmp_path):
    root = _project(tmp_path)
    internal = root / ".claude" / "skills" / "dev"
    (internal / "commands").mkdir(parents=True)
    (internal / "SKILL.md").write_text("# d\n", encoding="utf-8")
    (internal / "commands" / "go.md").write_text("# g\n", encoding="utf-8")
    assert _mod.invocation(root, "dev", "go")[0]["path"] == ".claude/skills/dev/SKILL.md"


def test_unknown_skill_names_the_root(tmp_path):
    with pytest.raises(_mod.UsageError, match=r"no SKILL\.md for skill 'nope'"):
        _mod.invocation(_project(tmp_path), "nope", "audit")


def test_unknown_command_lists_the_known_set(tmp_path):
    with pytest.raises(_mod.UsageError, match="known: _conventions, audit"):
        _mod.invocation(_project(tmp_path), "nitpicker", "nope")


def test_report_totals_each_set_independently(tmp_path):
    data = _mod.report(_project(tmp_path), "nitpicker", "audit")
    for block in data["sets"].values():
        assert block["totals"]["est_tokens"] == sum(r["est_tokens"] for r in block["files"])
    assert "not a gate" in data["unit"]


def test_render_lists_biggest_first(tmp_path, capsys):
    _mod.render(_mod.report(_project(tmp_path), "nitpicker", "audit"))
    lines = [line for line in capsys.readouterr().out.splitlines() if "skills/nitpicker" in line]
    assert lines[0].endswith("SKILL.md")


def test_delta_reports_not_available_when_the_baseline_is_zero():
    assert _mod._delta(10, 0) == "n/a"
    assert _mod._delta(90, 100) == "-10.0%"


def test_render_delta_compares_against_a_previous_run(tmp_path, capsys):
    root = _project(tmp_path)
    data = _mod.report(root, "nitpicker", "audit")
    baseline = json.loads(json.dumps(data))
    baseline["sets"]["invocation"]["totals"]["est_tokens"] *= 2
    _mod.render_delta(data, baseline)
    out = capsys.readouterr().out
    assert "invocation" in out
    assert "-50.0%" in out


def test_render_delta_survives_a_baseline_missing_a_set(tmp_path, capsys):
    data = _mod.report(_project(tmp_path), "nitpicker", "audit")
    _mod.render_delta(data, {})
    assert "n/a" in capsys.readouterr().out


def test_an_undecodable_file_is_measured_rather_than_crashing_the_report(tmp_path):
    """UnicodeDecodeError is a ValueError, so a strict decode escaped the OSError handler.

    One stray byte anywhere in the always-loaded set replaced the whole report
    with a traceback, and the agent reading that output learned nothing about
    the other seventeen files.
    """
    root = _project(tmp_path)
    bad = root / ".claude" / "rules" / "bad.md"
    bad.write_bytes(b"# bad \xff\xfe\n")
    rows = {r["path"]: r for r in _mod.always_loaded(root)}
    assert ".claude/rules/bad.md" in rows
    # Byte count comes from the raw bytes: errors="replace" widens a one-byte
    # sequence into a three-byte replacement char, so a re-encode would overcount.
    assert rows[".claude/rules/bad.md"]["bytes"] == bad.stat().st_size


def test_an_undecodable_file_does_not_change_the_exit_code(tmp_path, capsys):
    root = _project(tmp_path)
    (root / ".claude" / "rules" / "bad.md").write_bytes(b"\xff\xfe\xff\xfe")
    assert _mod.main([str(root)]) == 0
    assert "TOTAL" in capsys.readouterr().out


@pytest.mark.parametrize("payload", ["[]", '"a string"', "null", "123", "true"])
def test_a_baseline_of_the_wrong_json_shape_is_a_usage_error(tmp_path, capsys, payload):
    """Parsing is not enough — `[]` and `null` are valid JSON with no `.get`.

    A truncated redirect or the wrong file produced exactly those, and the
    reporting command answered with an AttributeError.
    """
    root = _project(tmp_path)
    bad = tmp_path / "b.json"
    bad.write_text(payload, encoding="utf-8")
    assert _mod.main([str(root), "--baseline", str(bad)]) == 2
    assert "must be a report object" in capsys.readouterr().err


# ── CLI ──────────────────────────────────────────────────────────────────────


def test_cli_reports_and_exits_zero_however_large_the_payload(tmp_path, capsys):
    """The no-gate property, pinned.

    An estimate that fails a build converts an approximation into a rule and
    then argues with contributors about a number nobody can reproduce.
    """
    root = _project(tmp_path)
    (root / "CLAUDE.md").write_text("x" * 5_000_000, encoding="utf-8")
    assert _mod.main([str(root)]) == 0
    assert "TOTAL" in capsys.readouterr().out


def test_cli_json_is_compact(tmp_path, capsys):
    assert _mod.main([str(_project(tmp_path)), "--json"]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1
    assert json.loads(out)["skill"] == "nitpicker"


def test_cli_baseline_prints_the_delta(tmp_path, capsys):
    root = _project(tmp_path)
    assert _mod.main([str(root), "--json"]) == 0
    saved = tmp_path / "base.json"
    saved.write_text(capsys.readouterr().out, encoding="utf-8")
    assert _mod.main([str(root), "--baseline", str(saved)]) == 0
    assert "+0.0%" in capsys.readouterr().out


def test_cli_rejects_a_non_directory_root(tmp_path, capsys):
    target = tmp_path / "f"
    target.write_text("x", encoding="utf-8")
    assert _mod.main([str(target)]) == 2
    assert "not a directory" in capsys.readouterr().err


def test_cli_rejects_an_unparseable_baseline(tmp_path, capsys):
    root = _project(tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert _mod.main([str(root), "--baseline", str(bad)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_cli_io_error_exits_one(tmp_path, capsys, monkeypatch):
    def boom(*_a, **_k):
        raise OSError("disk gone")

    monkeypatch.setattr(_mod, "report", boom)
    assert _mod.main([str(_project(tmp_path))]) == 1
    assert "disk gone" in capsys.readouterr().err


def test_cli_help_exits_zero_with_usage(capsys):
    with pytest.raises(SystemExit) as exc:
        _mod.main(["--help"])
    assert exc.value.code == 0
    assert "check-context-tokens" in capsys.readouterr().out


def test_module_runs_as_a_script(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check-context-tokens.py", str(_project(tmp_path))])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0
    assert "Context payload" in capsys.readouterr().out
