"""Tests for the PostToolUse / Stop hooks in scripts/hooks/.

Focus: the protocol contract (failures reach the agent only via exit 2 + stderr)
and the gating branches (empty stdin, non-dict payload, irrelevant paths) that
must be silent no-ops. These hooks had no coverage before.
"""

import importlib.util
import io
import json
import shutil
import sys
from pathlib import Path

import pytest

HOOKS_DIR = Path(__file__).parent.parent / "scripts" / "hooks"
SCRIPTS_DIR = HOOKS_DIR.parent
HOOK_NAMES = [
    "validate-json-hook",
    "validate-skill-hook",
    "check-version-sync-hook",
    "ruff-hook",
    "stop-reminder",
]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HOOKS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _run(mod, stdin_text: str, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    mod.main()


# ── shared contract across the four stdin-driven PostToolUse hooks ─────────────

STDIN_HOOKS = ["validate-json-hook", "validate-skill-hook", "check-version-sync-hook", "ruff-hook"]


@pytest.mark.parametrize("name", STDIN_HOOKS)
def test_empty_stdin_is_silent_noop(name, monkeypatch, capsys):
    _run(_load(name), "", monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize("name", STDIN_HOOKS)
def test_non_dict_payload_is_silent_noop(name, monkeypatch, capsys):
    # A JSON `null` / list payload must not crash on data.get(...).
    _run(_load(name), "null", monkeypatch)
    _run(_load(name), "[]", monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize("name", STDIN_HOOKS)
def test_irrelevant_path_is_silent_noop(name, monkeypatch, tmp_path, capsys):
    mod = _load(name)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    target = tmp_path / "notes.txt"
    target.write_text("hello", encoding="utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(target)}}
    _run(mod, json.dumps(payload), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── validate-json-hook: the self-contained one, tested end to end ─────────────


def test_validate_json_valid_file_passes(monkeypatch, tmp_path, capsys):
    mod = _load("validate-json-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    f = tmp_path / "good.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    payload = {"tool_input": {"file_path": str(f)}}
    _run(mod, json.dumps(payload), monkeypatch)
    assert capsys.readouterr().err == ""


def test_validate_json_invalid_file_exits_2_with_stderr(monkeypatch, tmp_path, capsys):
    mod = _load("validate-json-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    f = tmp_path / "bad.json"
    f.write_text('{"a": 1,}', encoding="utf-8")  # trailing comma
    payload = {"tool_input": {"file_path": str(f)}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "INVALID JSON" in capsys.readouterr().err


def test_validate_json_unreadable_path_fails_open(monkeypatch, tmp_path, capsys):
    # A directory named like a .json file: path.exists() passes but read_text raises
    # OSError (IsADirectoryError). The hook must fail open — no SystemExit, no output.
    mod = _load("validate-json-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "config.json").mkdir()
    payload = {"tool_input": {"file_path": str(tmp_path / "config.json")}}
    _run(mod, json.dumps(payload), monkeypatch)  # must return cleanly, no SystemExit
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── the three subprocess-driven hooks: a genuinely bad input must reach exit 2 ─
# Each builds a tmp REPO_ROOT holding the validator/checker the hook shells out to
# (copied from scripts/), so replacing the hook's detection body with `pass` fails.


def test_validate_skill_bad_structure_exits_2(monkeypatch, tmp_path, capsys):
    mod = _load("validate-skill-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(SCRIPTS_DIR / "validate-skill.py", scripts / "validate-skill.py")
    shutil.copy(SCRIPTS_DIR / "common.py", scripts / "common.py")

    skill = tmp_path / "skills" / "foo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("no frontmatter here\n\n# not a skill title\n", encoding="utf-8")

    payload = {"tool_name": "Write", "tool_input": {"file_path": str(skill)}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "missing YAML frontmatter" in capsys.readouterr().err


def test_version_sync_mismatch_exits_2(monkeypatch, tmp_path, capsys):
    mod = _load("check-version-sync-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    # check-version-sync.py resolves its own repo via __file__.parent.parent, so a
    # copy under tmp/scripts reads the tmp manifests below — not the real repo.
    shutil.copy(SCRIPTS_DIR / "check-version-sync.py", scripts / "check-version-sync.py")

    (tmp_path / "package.json").write_text('{"version": "1.0.0"}', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (tmp_path / ".release-please-manifest.json").write_text('{".": "1.0.0"}', encoding="utf-8")
    plugin_dir = tmp_path / ".claude-plugin"
    plugin_dir.mkdir()
    plugin_dir.joinpath("marketplace.json").write_text(
        '{"plugins": [{"version": "1.0.0"}]}', encoding="utf-8"
    )
    # The one deliberate desync — this is also the file whose edit triggers the hook.
    manifest = plugin_dir / "plugin.json"
    manifest.write_text('{"version": "9.9.9"}', encoding="utf-8")

    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(manifest)}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "MISMATCH" in capsys.readouterr().err


def test_ruff_hook_lint_error_exits_2(monkeypatch, tmp_path, capsys):
    mod = _load("ruff-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    # F821 undefined name: ruff flags it and --fix cannot remove it, so the hook's
    # post-fix `ruff check` still fails (an autofixable F401 would be silently fixed).
    f = tmp_path / "bad.py"
    f.write_text("x = undefined_name\n", encoding="utf-8")

    payload = {"tool_name": "Write", "tool_input": {"file_path": str(f)}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "F821" in capsys.readouterr().err


# ── stop-reminder: gate on git porcelain output ───────────────────────────────


def _fake_staged(monkeypatch, mod, staged_paths):
    """Stub `git diff --cached --name-only -z` output (NUL-separated paths)."""

    class _Result:
        returncode = 0
        stdout = "\0".join([*staged_paths, ""])

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result())


def test_stop_reminder_flags_staged_skill(monkeypatch, capsys):
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, ["skills/nitpicker/SKILL.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "Staged skill changes detected" in err
    assert "skills/nitpicker/SKILL.md" in err


def test_stop_reminder_flags_staged_command_file(monkeypatch, capsys):
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, ["skills/nitpicker/commands/audit.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "skills/nitpicker/commands/audit.md" in capsys.readouterr().err


def test_stop_reminder_silent_when_no_staged_skill(monkeypatch, capsys):
    mod = _load("stop-reminder")
    # A skill edit in the working tree but NOT staged must stay quiet now.
    _fake_staged(monkeypatch, mod, ["README.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    mod.main()
    assert capsys.readouterr().err == ""


def test_stop_reminder_silent_when_nothing_staged(monkeypatch, capsys):
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, [])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    mod.main()
    assert capsys.readouterr().err == ""


def test_stop_reminder_does_not_loop_when_active(monkeypatch, capsys):
    """stop_hook_active means we are already on a forced continuation — must not re-block."""
    mod = _load("stop-reminder")

    def _boom(*a, **k):
        raise AssertionError("git must not run once stop_hook_active is set")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"stop_hook_active": True})))
    mod.main()  # returns cleanly, no SystemExit
    assert capsys.readouterr().err == ""
