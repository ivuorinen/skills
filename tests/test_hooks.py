"""Tests for the PostToolUse / Stop hooks in scripts/hooks/.

Focus: the protocol contract (failures reach the agent only via exit 2 + stderr)
and the gating branches (empty stdin, non-dict payload, irrelevant paths) that
must be silent no-ops. These hooks had no coverage before.
"""

import ast
import fnmatch
import importlib.util
import io
import json
import re
import runpy
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

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
    """Import a hook module by its hyphenated filename."""
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), HOOKS_DIR / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _run(mod, stdin_text: str, monkeypatch):
    """Drive a hook's main() with `stdin_text` as its event payload."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin_text))
    mod.main()


# ── shared contract across the four stdin-driven PostToolUse hooks ─────────────

STDIN_HOOKS = [
    "validate-json-hook",
    "validate-skill-hook",
    "check-version-sync-hook",
    "ruff-hook",
    "validate-rules-hook",
    "validate-evals-hook",
]


@pytest.mark.parametrize("name", STDIN_HOOKS)
def test_empty_stdin_is_silent_noop(name, monkeypatch, capsys):
    """No event means nothing to judge: the hook returns without output."""
    _run(_load(name), "", monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize("name", STDIN_HOOKS)
def test_non_dict_payload_is_silent_noop(name, monkeypatch, capsys):
    # A JSON `null` / list payload must not crash on data.get(...).
    """A JSON `null` or list payload must not crash on data.get(...)."""
    _run(_load(name), "null", monkeypatch)
    _run(_load(name), "[]", monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize("name", STDIN_HOOKS)
def test_irrelevant_path_is_silent_noop(name, monkeypatch, tmp_path, capsys):
    """A hook that fires on every edit must stay quiet for files it does not own."""
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
    """Well-formed JSON produces no output."""
    mod = _load("validate-json-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    f = tmp_path / "good.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    payload = {"tool_input": {"file_path": str(f)}}
    _run(mod, json.dumps(payload), monkeypatch)
    assert capsys.readouterr().err == ""


def test_validate_json_invalid_file_exits_2_with_stderr(monkeypatch, tmp_path, capsys):
    """Exit 2 plus stderr is the only channel a PostToolUse hook has back to the agent."""
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
    """An unreadable path is not this hook's defect, so it must not block the edit."""
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
    """A malformed SKILL.md must be reported at the edit, not left for CI."""
    mod = _load("validate-skill-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(SCRIPTS_DIR / "validate-skill.py", scripts / "validate-skill.py")
    shutil.copy(SCRIPTS_DIR / "common.py", scripts / "common.py")
    # common.py path-loads the shipped parser, so the fake repo needs it too.
    shipped = tmp_path / "skills" / "nitpicker" / "scripts"
    shipped.mkdir(parents=True)
    # findings.py imports its sibling md_fences, so both travel or neither works.
    for _name in ("findings.py", "md_fences.py"):
        shutil.copy(
            SCRIPTS_DIR.parent / "skills" / "nitpicker" / "scripts" / _name,
            shipped / _name,
        )

    skill = tmp_path / "skills" / "foo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("no frontmatter here\n\n# not a skill title\n", encoding="utf-8")

    payload = {"tool_name": "Write", "tool_input": {"file_path": str(skill)}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "missing YAML frontmatter" in capsys.readouterr().err


def test_version_sync_mismatch_exits_2(monkeypatch, tmp_path, capsys):
    """The five manifests drift silently; only this hook reads them together at edit time."""
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
    """A lint error --fix cannot remove has to surface rather than pass quietly."""
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


def test_ruff_hook_missing_binary_is_silent_noop(monkeypatch, tmp_path, capsys):
    """No ruff on PATH: fail open like every sibling, not a FileNotFoundError traceback."""
    mod = _load("ruff-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)

    def _boom(*a, **k):
        """Fail the test if ruff is invoked when the binary is absent."""
        raise AssertionError("ruff must not be invoked when the binary is absent")

    monkeypatch.setattr(mod.subprocess, "run", _boom)

    f = tmp_path / "bad.py"
    f.write_text("x = undefined_name\n", encoding="utf-8")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(f)}}
    _run(mod, json.dumps(payload), monkeypatch)  # returns cleanly, no SystemExit
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── _hooklib.repo_root: empty env vars must not win the fallback chain ────────


def _hooklib():
    """Load _hooklib fresh, so env changes are read at import time."""
    return _load("_hooklib")


def _fake_checkout(root):
    """A tree repo_root() will accept — it probes for scripts/hooks/_hooklib.py."""
    (root / "scripts" / "hooks").mkdir(parents=True)
    (root / "scripts" / "hooks" / "_hooklib.py").touch()
    return root


def test_repo_root_empty_claude_project_dir_falls_through(monkeypatch, tmp_path):
    """An empty env value counts as absent: Path('') is Path('.'), which would silently move every
    hook's containment boundary to the working directory.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "")
    monkeypatch.setenv("REPO_ROOT", str(_fake_checkout(tmp_path)))
    assert _hooklib().repo_root() == tmp_path


def test_repo_root_ignores_env_dir_that_is_not_this_checkout(monkeypatch, tmp_path):
    """CLAUDE_PROJECT_DIR is the session launch dir — a parent dir must not win.

    Accepting it aims every gate at a tree with no scripts in it, so each gate is
    skipped and the hook exits 0 having validated nothing.
    """
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("REPO_ROOT", raising=False)
    assert _hooklib().repo_root() == HOOKS_DIR.parent.parent


def test_repo_root_both_empty_falls_back_to_parents(monkeypatch):
    """With neither variable usable, the computed parent of scripts/hooks/ is the root."""
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "")
    monkeypatch.setenv("REPO_ROOT", "")
    assert _hooklib().repo_root() == HOOKS_DIR.parent.parent


# ── stop-reminder: gate on git porcelain output ───────────────────────────────


def _fake_staged(monkeypatch, mod, staged_paths, worktree_paths=()):
    """Stub the two `git diff --name-only -z` calls (staged, then working tree)."""

    def _run(argv, *a, **k):
        """Return staged or worktree paths depending on the git argv."""
        paths = staged_paths if "--cached" in argv else worktree_paths

        class _Result:
            """Stand-in for CompletedProcess with NUL-separated stdout."""

            returncode = 0
            stdout = "\0".join([*paths, ""])

        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", _run)


def test_stop_reminder_flags_staged_skill(monkeypatch, capsys):
    """A staged SKILL.md is the case the reminder exists for."""
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, ["skills/nitpicker/SKILL.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "Pending skill changes detected" in err
    assert "skills/nitpicker/SKILL.md" in err


def test_stop_reminder_flags_unstaged_skill(monkeypatch, capsys):
    """`git commit -am` stages and commits in one call, so nothing is ever seen
    staged at stop time — the working-tree scope is what catches it."""
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, [], worktree_paths=["skills/nitpicker/SKILL.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "skills/nitpicker/SKILL.md" in capsys.readouterr().err


def test_stop_reminder_dedupes_across_scopes(monkeypatch, capsys):
    """A path dirty in both index and working tree must be listed once."""
    mod = _load("stop-reminder")
    p = "skills/nitpicker/SKILL.md"
    _fake_staged(monkeypatch, mod, [p], worktree_paths=[p])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit):
        mod.main()
    assert capsys.readouterr().err.count(p) == 1


def test_stop_reminder_flags_staged_command_file(monkeypatch, capsys):
    """Command files count as skill changes too, not just SKILL.md itself."""
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, ["skills/nitpicker/commands/audit.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "skills/nitpicker/commands/audit.md" in capsys.readouterr().err


def test_stop_reminder_silent_when_no_staged_skill(monkeypatch, capsys):
    """Dirty non-skill paths must stay quiet in either scope."""
    mod = _load("stop-reminder")
    # Dirty paths that are not skill files must stay quiet in either scope.
    _fake_staged(monkeypatch, mod, ["README.md"], worktree_paths=["README.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    mod.main()
    assert capsys.readouterr().err == ""


def test_stop_reminder_silent_when_nothing_staged(monkeypatch, capsys):
    """A clean tree produces no reminder."""
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, [])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    mod.main()
    assert capsys.readouterr().err == ""


def test_stop_reminder_does_not_loop_when_active(monkeypatch, capsys):
    """stop_hook_active means we are already on a forced continuation — must not re-block."""
    mod = _load("stop-reminder")

    def _boom(*a, **k):
        """Fail the test if git runs once stop_hook_active is set."""
        raise AssertionError("git must not run once stop_hook_active is set")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"stop_hook_active": True})))
    mod.main()  # returns cleanly, no SystemExit
    assert capsys.readouterr().err == ""


# ── deny-agents-path-hook: the substring bypasses must now be blocked ──────────


def test_deny_agents_blocks_cd_bypass(monkeypatch):
    """`cd` into the protected tree shifts the glob base; the guard resolves it anyway."""
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": "cd .claude/agents && cat > x.md"}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_blocks_double_slash(monkeypatch):
    """A repeated separator reaches the same path, so canonicalisation must fold it."""
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": "sed -i s/a/b/ .claude//agents/foo.md"}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_allows_unrelated_command(monkeypatch):
    """A sibling .claude/ path is not the agents tree and must not be blocked."""
    mod = _load("deny-agents-path-hook")
    command = "ls .claude/rules/"
    _run(mod, json.dumps({"tool_input": {"command": command}}), monkeypatch)  # no SystemExit
    # Pin the verdict, not just the absence of SystemExit: a hook that stopped
    # evaluating the command entirely would also raise nothing.
    assert mod._references_agents(command) is False


def test_deny_agents_blocks_dot_segment(monkeypatch):
    """A `.` segment reaches the same path and must not hide the match."""
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": "cat .claude/./agents/x.md"}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_blocks_escaped_slash(monkeypatch):
    """An escaped separator is still a separator to the shell."""
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": "cat .claude\\/agents/x.md"}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "command",
    [
        'cat .claude/agent"s"/reviewer.md',  # quote splice
        "cat .claude/'agents'/reviewer.md",  # single-quote splice
        "cat .claude/\\agents/reviewer.md",  # bare backslash escape
        'D=.claude; printf x > "$D/agents/reviewer.md"',  # variable indirection
        "A=agents; cat .claude/$A/reviewer.md",  # variable-built path
        "cat .claude/agent*/*.md",  # glob star
        "cat .claude/agent?/reviewer.md",  # glob question
        "cat .claude/a*/reviewer.md",  # glob truncated before "agent"
        "cat .claude/age*/reviewer.md",  # glob truncated mid-word
        "printf x > .claude/a[g]ents/reviewer.md",  # bracket glob, no literal "agent"
        "cat .?laude/agents/reviewer.md",  # glob obscures the "c" in .claude (no literal .claude)
        "cat .cl*de/agents/reviewer.md",  # glob obscures "au" in .claude
        "printf x > .?laude/agents/new-file.md",  # glob-obscured root, not-yet-existing file
        "cd .claude && cat a*/reviewer.md",  # cd shifts the glob base into .claude
        "cd .?laude && cat a*/reviewer.md",  # glob-spelled cd target shifts the base
    ],
)
def test_deny_agents_blocks_indirection_and_glob(monkeypatch, command):
    """Every spelling the shell resolves to .claude/agents/ must block — the literal
    substring match missed quoting, backslash, variable indirection, and globs."""
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": command}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_allows_agents_word_without_path(monkeypatch):
    # `.claude` present and the word "agents" present, but not as a path into the
    # agents dir (grepping rules for the word) — must not false-positive.
    """Both tokens present but not as a path into the tree — grepping rules for the word must not
    false-positive.
    """
    mod = _load("deny-agents-path-hook")
    command = "grep agents .claude/rules/foo.md"
    _run(mod, json.dumps({"tool_input": {"command": command}}), monkeypatch)  # no SystemExit
    assert mod._references_agents(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "cat /etc/*.conf",  # absolute glob outside the repo
        "cat /tmp/.cl*de/agents/*.md",  # absolute glob-obscured path outside the repo
        "find / -name a*",  # absolute root glob
    ],
)
def test_deny_agents_absolute_glob_does_not_crash(command):
    # Path.glob raises NotImplementedError/ValueError on absolute patterns; the
    # guard must swallow that (fail-safe) rather than crash open. These point
    # outside the repo, so they resolve to "allow".
    """Path.glob raises on some absolute patterns; the guard swallows that rather than crashing
    open.
    """
    mod = _load("deny-agents-path-hook")
    assert mod._references_agents(command) is False


@pytest.mark.parametrize(
    "command",
    [
        # Locates the file by NAME, never spelling the directory: no `.claude`,
        # no `agents` token, no glob metacharacter — invisible to all three of
        # the path-shaped mechanisms, and it really resolves to the definition.
        "find . -name release-readiness-reviewer.md -exec cat {} +",
        "find . -name skill-consistency-enforcer.md -exec sed -i s/x/y/ {} +",
        "cp skill-consistency-enforcer.md /tmp/x",
    ],
)
def test_deny_agents_blocks_content_addressed_reach(command, monkeypatch):
    """A command naming the file rather than the directory carries no path token, so the bare
    filename is matched instead.
    """
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": command}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "command",
    [
        "make check",
        "uv run --extra dev pytest tests/",
        "git commit -m 'fix: review comments'",
        "grep -rn review skills/nitpicker/commands/",
        "cat skills/nitpicker/commands/review.md",
        "gh pr review 42 --approve",
    ],
)
def test_deny_agents_filename_match_does_not_false_positive(command, monkeypatch):
    """The filename match is on the full `<name>.md`, not a stem fragment.

    Matching a fragment like 'review' would block routine work — it is a
    nitpicker command name and appears in ordinary commands constantly.
    """
    mod = _load("deny-agents-path-hook")
    _run(mod, json.dumps({"tool_input": {"command": command}}), monkeypatch)  # no SystemExit
    assert mod._references_agents(command) is False


@pytest.mark.parametrize(
    "command",
    [
        # A longer filename that merely *contains* an agent filename is a
        # different file. Substring matching blocked these; token-boundary
        # matching does not.
        "cat release-readiness-reviewer.md.bak",
        "cat notes-about-skill-consistency-enforcer.md",
        "git show HEAD:docs/release-readiness-reviewer.md.orig",
    ],
)
def test_deny_agents_filename_match_is_token_bounded(command, monkeypatch):
    """Substring matching would also block a different file whose name merely starts with a
    protected one.
    """
    mod = _load("deny-agents-path-hook")
    _run(mod, json.dumps({"tool_input": {"command": command}}), monkeypatch)  # no SystemExit
    assert mod._references_agents(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "cp skill-consistency-enforcer.md /tmp/x",
        "cat --file=release-readiness-reviewer.md",
        "tar cf a.tar release-readiness-reviewer.md,skill-consistency-enforcer.md",
    ],
)
def test_deny_agents_exact_filename_still_blocks_after_boundary_fix(command, monkeypatch):
    """The boundary fix must not reopen the class it was added to close."""
    mod = _load("deny-agents-path-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"command": command}}), monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_content_search_remains_a_known_gap():
    """Pins the documented boundary rather than pretending the surface is closed.

    A command that finds the file by CONTENT carries neither the path nor the
    filename, and its only shared token ('review') cannot be matched without
    blocking routine work. CODEOWNERS plus branch protection is the binding
    control; CLAUDE.md's PreToolUse section says so. If this ever starts
    returning True the docs claim must be revisited too.
    """
    mod = _load("deny-agents-path-hook")
    assert mod._references_agents("git ls-files | grep review | xargs cat") is False


ROOT = Path(__file__).parent.parent


def _pyproject_pin(package: str) -> str:
    """The version pyproject.toml's dev extra pins for `package`."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(rf'"{package}==([\d.]+)"', text)
    assert m, f"pyproject.toml no longer pins {package}"
    return m.group(1)


def test_every_ruff_call_site_names_the_same_version():
    """Four places invoke ruff and two of them WRITE (`make format`, the hook).

    A version that drifts between them means the tree gets formatted one way and
    judged another — reformat churn whose cause appears nowhere in the diff. This
    already happened: pyproject moved to 0.16.0 while the Makefile, CI, and the
    pre-commit rev stayed on 0.15.21.

    CI is no longer a site: the Validate job runs `make check`, so it inherits
    the Makefile's pin instead of carrying a fifth copy. That is the point of
    the collapse — fewer places to keep in step, not merely fewer lines.
    """
    want = _pyproject_pin("ruff")
    sites = {
        "scripts/hooks/ruff-hook.py": rf'"ruff=={re.escape(want)}"',
        "Makefile": rf"ruff=={re.escape(want)}\b",
        # SHA-pinned per github-actions-security.md, so the version lives in the
        # trailing comment; that is what has to match.
        ".pre-commit-config.yaml": rf"#\s*v{re.escape(want)}\b",
    }
    for rel, pattern in sites.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert re.search(pattern, text), f"{rel} does not name ruff {want}"

    # Both writing call sites, not just one of them.
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert len(re.findall(rf"ruff=={re.escape(want)}\b", makefile)) == 2, (
        "Makefile must pin ruff in both `format` and `format-check`"
    )

    # And CI must not quietly reacquire its own pin.
    workflow = (ROOT / ".github/workflows/validate-skills.yml").read_text(encoding="utf-8")
    assert "ruff==" not in workflow, (
        "the Validate job runs `make check`; a ruff pin here is a reintroduced second copy"
    )


# Only a NAMED GROUP opener, never a lookbehind. `(?<` also begins `(?<=` and
# `(?<!`, which JS and Python spell identically — rewriting those to `(?P<=` /
# `(?P<!` produces a pattern Python refuses to compile, so a matchString using
# lookbehind (`(?<=ruff==)` is a natural way to anchor one) would crash this
# test instead of checking the config. The lookahead requires an identifier
# character, which `=` and `!` are not.
_JS_NAMED_GROUP = re.compile(r"\(\?<(?=[A-Za-z_])")

# Renovate runs custom-manager regexes through RE2 (node-re2), whose docs state
# it "does not support backreferences and lookahead assertions" — lookbehind
# likewise. Python's `re` accepts all of them, so a matchString can compile
# perfectly here and be rejected by Renovate at config-load time, which leaves
# the manager inert and the pins unmanaged: the original bug, silently restored.
#
# A conservative syntactic check, not an RE2 parser: it catches the two
# constructs the docs name, which is what a matchString would plausibly reach
# for (`(?<=ruff==)` is the obvious way to anchor one).
_RE2_UNSUPPORTED = re.compile(
    r"""\(\?[=!]      # lookahead  (?=…) (?!…)
      | \(\?<[=!]     # lookbehind (?<=…) (?<!…)
      | \\[1-9]       # numeric backreference \1
      | \\k<[^>]+>    # named backreference \k<name>
    """,
    re.VERBOSE,
)


def _js_regex_to_python(pattern: str) -> str:
    """Renovate matchStrings are JS regexes; Python needs `(?P<name>)`.

    The named-group spelling is the only difference that matters for these
    patterns, and rewriting just that is what lets the test run the real config
    rather than a restatement of it.
    """
    return _JS_NAMED_GROUP.sub("(?P<", pattern)


# Renovate: "If a string is not a regex pattern, it is treated as a glob pattern
# parsed using the minimatch library" — a regex is one wrapped in slashes, with
# optional trailing flags (`/pat/i`).
_SLASH_REGEX = re.compile(r"^/(?P<body>.*)/(?P<flags>[a-z]*)$", re.DOTALL)


def _renovate_pattern_selects(pattern: str, filename: str) -> bool:
    """Does a managerFilePatterns entry select `filename`?

    Approximates Renovate, and the approximation has a stated edge: minimatch is
    not fnmatch. They agree on the literal filenames and simple `*` globs this
    repo uses; brace expansion, `!` negation and globstar are not modelled. The
    point of the helper is to catch a pattern that selects *nothing* — the way
    the pre-commit manager first shipped — not to reimplement minimatch.

    The flags handling is not decorative: `/pat/i` is a valid Renovate pattern,
    and an `endswith("/")` test reads it as a glob and reports no match, which
    would fail this guard on a correct config.
    """
    m = _SLASH_REGEX.match(pattern)
    if m:
        flags = re.IGNORECASE if "i" in m.group("flags") else 0
        return bool(re.search(_js_regex_to_python(m.group("body")), filename, flags))
    return fnmatch.fnmatch(filename, pattern)


@pytest.mark.parametrize(
    ("pattern", "selects"),
    [
        (".pre-commit-config.yaml", True),  # literal glob — what this repo uses
        ("*.yaml", True),
        ("scripts/hooks/*.py", False),  # a glob for other files
        ("/^\\.pre-commit-config\\.yaml$/", True),  # slash-wrapped regex
        ("/^\\.PRE-COMMIT-CONFIG\\.YAML$/i", True),  # ...with a flag
        ("/^\\.PRE-COMMIT-CONFIG\\.YAML$/", False),  # same regex, no flag: no match
        ("/nomatch/", False),
        # The form that shipped in #98: regex syntax without the slashes, so
        # Renovate reads it as a glob and it selects nothing.
        ("^\\.pre-commit-config\\.yaml$", False),
    ],
)
def test_renovate_pattern_matcher_follows_renovate_semantics(pattern, selects):
    """The guard is only as good as this matcher, so the matcher gets its own test."""
    assert _renovate_pattern_selects(pattern, ".pre-commit-config.yaml") is selects


@pytest.mark.parametrize(
    ("js", "expected"),
    [
        # named groups are rewritten
        (r"(?<depName>a)==(?<currentValue>b)", r"(?P<depName>a)==(?P<currentValue>b)"),
        # lookbehind is left alone — both spellings are already valid Python
        (r"(?<=ruff==)(?<currentValue>[0-9.]+)", r"(?<=ruff==)(?P<currentValue>[0-9.]+)"),
        (r"(?<!no)(?<depName>z)", r"(?<!no)(?P<depName>z)"),
    ],
)
def test_js_regex_translation_leaves_lookbehind_intact(js, expected):
    """A blanket `(?<` -> `(?P<` swap corrupts `(?<=` and `(?<!`.

    The result does not compile, so the helper would crash the config test with
    a regex error rather than reporting what the config does — and the failure
    would read as a bad matchString rather than a bad test helper.
    """
    translated = _js_regex_to_python(js)
    assert translated == expected
    re.compile(translated)  # must be valid Python, not merely different


@pytest.mark.parametrize(
    ("pattern", "rejected"),
    [
        (r"ruff==(?=(?<currentValue>[0-9.]+))", True),  # lookahead
        (r"(?<=ruff==)(?<currentValue>[0-9.]+)", True),  # lookbehind
        (r"(?<!no)(?<depName>z)", True),  # negative lookbehind
        (r"(?<depName>a)\1", True),  # numeric backreference
        (r"(?<depName>a)\k<depName>", True),  # named backreference
        # the two patterns renovate.json actually ships
        (r"--with\s+(?<depName>[A-Za-z0-9._-]+)==(?<currentValue>[0-9][^\s]*)", False),
        (r"dependencies\s*=\s*\[\"(?<depName>[A-Za-z0-9._-]+)==(?<currentValue>[^\"]+)\"\]", False),
    ],
)
def test_re2_guard_rejects_what_renovate_cannot_run(pattern, rejected):
    """RE2 supports neither lookaround nor backreferences, named or numeric.

    Catching them here keeps the failure in the explicit guard. Left to Python,
    a named backreference surfaces as `bad escape \\k` from `re.compile` — an
    error that points at the test helper rather than at the unsupported
    construct in renovate.json.
    """
    assert bool(_RE2_UNSUPPORTED.search(pattern)) is rejected


def test_renovate_can_see_every_tool_pin_the_sync_tests_enforce():
    """The sync tests above are only satisfiable if Renovate can reach every site.

    They could not be: a ruff bump updated pyproject.toml alone and left the
    Makefile, the PEP 723 hook block and the pre-commit rev behind, because no
    enabled manager reads those. The gate then failed the bot's own PR with no
    way for it to comply. Assert the customManagers actually match the pins.
    """
    cfg = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    assert "custom.regex" in cfg["enabledManagers"], (
        "customManagers do nothing unless custom.regex is an enabled manager"
    )

    expected = {"Makefile": {"pre-commit", "pyright", "ruff"}, "scripts/hooks/*.py": {"ruff"}}
    seen: dict[str, set[str]] = {}
    for mgr in cfg["customManagers"]:
        glob_pat = mgr["managerFilePatterns"][0]
        match_string = mgr["matchStrings"][0]
        # Python's `re` is strictly more permissive than what Renovate runs, so
        # checking only that a pattern compiles here would pass a config
        # Renovate rejects at load time — leaving the manager inert and the
        # pins unmanaged again, the exact failure this file exists to prevent.
        assert not _RE2_UNSUPPORTED.search(match_string), (
            f"{glob_pat}: matchString uses a construct RE2 rejects "
            f"(lookaround or backreference): {match_string}"
        )
        rx = re.compile(_js_regex_to_python(match_string))
        found = {
            m.group("depName")
            for f in sorted(ROOT.glob(glob_pat))
            for m in rx.finditer(f.read_text(encoding="utf-8"))
        }
        seen[glob_pat] = found

    for glob_pat, want in expected.items():
        assert glob_pat in seen, f"no customManager covers {glob_pat}"
        missing = want - seen[glob_pat]
        assert not missing, f"{glob_pat}: customManager matches nothing for {sorted(missing)}"


def test_the_builtin_pre_commit_manager_stays_disabled():
    """It cannot version a SHA-pinned rev, and it does not fail quietly.

    Reading a `rev:` it cannot parse, it proposes replacing the pin with a bare
    tag: #69, #70, #71 and #99 were all that same un-pinning, each one undoing
    the SHA discipline .claude/rules/github-actions-security.md requires. The
    SHA-pin test fails such a PR, so nothing merged — but the PR kept coming
    back, and a gate that has to keep rejecting the same proposal is the wrong
    place to solve it.

    Re-enabling the manager adds no coverage:
    test_the_renovate_custom_manager_matches_every_pre_commit_rev asserts the
    custom.regex manager already reaches every rev in the file.
    """
    cfg = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    assert "pre-commit" not in cfg["enabledManagers"], (
        "the built-in pre-commit manager cannot version a 40-character SHA rev and "
        "repeatedly proposes un-pinning it to a tag; custom.regex covers those revs"
    )


def test_renovate_groups_each_tool_across_its_managers():
    """One PR per tool, or every PR is a partial bump.

    ruff on PyPI and astral-sh/ruff-pre-commit are separate packages to
    Renovate. Ungrouped they arrive as two PRs, and each one on its own fails
    test_every_ruff_call_site_names_the_same_version.
    """
    cfg = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    groups = {
        r["groupName"]: set(r["matchPackageNames"])
        for r in cfg.get("packageRules", [])
        if "groupName" in r and "matchPackageNames" in r
    }
    assert {"ruff", "astral-sh/ruff-pre-commit"} <= groups.get("ruff", set()), (
        "ruff and its pre-commit repo must share a groupName"
    )
    assert {"bandit", "PyCQA/bandit"} <= groups.get("bandit", set()), (
        "bandit and its pre-commit repo must share a groupName"
    )


def test_bandit_pin_matches_the_pre_commit_rev_comment():
    """Same discipline as ruff: `make security`, CI, and the pre-commit hook all
    read [tool.bandit] from pyproject.toml, so the version must not drift."""
    want = _pyproject_pin("bandit")
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert re.search(rf"#\s*{re.escape(want)}\b", config), (
        f".pre-commit-config.yaml does not name bandit {want}"
    )


def test_ci_breaking_marker_gate_matches_both_footer_spellings():
    """Conventional Commits treats `BREAKING CHANGE` and `BREAKING-CHANGE` as
    synonymous and release-please honours both, so a gate matching only the space
    form would wave through half the spellings.

    Reads the regex out of the workflow rather than restating it, so the test
    cannot pass against a literal the workflow no longer uses.
    """
    workflow = (ROOT / ".github/workflows/validate-skills.yml").read_text(encoding="utf-8")
    m = re.search(r'r"(\^BREAKING[^"]*)"', workflow)
    assert m, "could not find the breaking-footer regex in the workflow"
    footer = re.compile(m.group(1), re.M)
    assert footer.search("BREAKING CHANGE: drops the v1 store")
    assert footer.search("BREAKING-CHANGE: drops the v1 store")
    assert not footer.search("mentions a breaking change in prose")


def test_bandit_pre_commit_hook_scans_the_same_roots_as_make_security():
    """pre-commit passes changed files explicitly, bypassing both `-r skills/
    scripts/` and [tool.bandit] exclude_dirs — so the hook must restate them or
    it gates a different set than `make security` and CI."""
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    block = config.split("- id: bandit", 1)[1].split("- repo:", 1)[0]
    assert "files:" in block, "bandit hook must bound itself to the scanned roots"
    assert "skills" in block and "scripts" in block
    assert "tests" in block, "tests/ must stay excluded (B101 is the test mechanism)"


def test_every_pre_commit_rev_is_sha_pinned_with_a_version_comment():
    """github-actions-security.md requires it, and nothing enforced it.

    Two things depend on this shape, not just the security clause:

    1. A `rev:` naming a tag is mutable — the tag can be repointed at new code
       without the pin changing, and these repos execute arbitrary code inside
       the authoritative Validate job.
    2. The renovate.json custom manager that keeps these revs current matches
       `rev: <40-hex> # <version>`. A rev in any other shape is invisible to it,
       so un-pinning does not merely weaken the pin — it stops updates entirely.

    This was not hypothetical: PRs #69/#70/#71 were Renovate's built-in
    pre-commit manager proposing to replace a SHA with a tag, and #71 merged,
    leaving `pre-commit/pre-commit-hooks` tag-pinned until this test existed.
    """
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    revs = re.findall(r"^\s+rev:\s*(\S+)(.*)$", config, re.MULTILINE)
    assert revs, "no rev: lines found — has the config moved?"
    for value, trailer in revs:
        assert re.fullmatch(r"[0-9a-f]{40}", value), (
            f"rev {value!r} is not a 40-character commit SHA; a tag is mutable "
            "and the renovate custom manager cannot read it"
        )
        assert re.match(r"\s*#\s*\S+", trailer), (
            f"rev {value[:8]}… has no trailing version comment; Renovate takes currentValue from it"
        )


def test_the_renovate_custom_manager_matches_every_pre_commit_rev():
    """The pin shape above and the manager's regex must stay in step.

    Asserting the shape is not enough on its own: the guard that matters is that
    the *actual* pattern in renovate.json still matches every rev in the file.
    """
    cfg = json.loads((ROOT / "renovate.json").read_text(encoding="utf-8"))
    managers = [
        m
        for m in cfg.get("customManagers", [])
        if any(".pre-commit-config" in p for p in m.get("managerFilePatterns", []))
    ]
    assert len(managers) == 1, "expected exactly one custom manager for the pre-commit config"

    # managerFilePatterns must actually SELECT the file, which is a separate
    # question from whether matchStrings parses it. A bare
    # `^\.pre-commit-config\.yaml$` is a glob matching nothing, which is how this
    # manager first shipped — valid config, silently inert, and this test passed
    # anyway because it only ever exercised matchStrings.
    for raw in managers[0]["managerFilePatterns"]:
        assert _renovate_pattern_selects(raw, ".pre-commit-config.yaml"), (
            f"managerFilePatterns entry {raw!r} selects no file: as a glob it matches nothing, "
            "and a regex must be wrapped in slashes to be read as one"
        )

    # Renovate uses JS named groups (?<name>); Python spells them (?P<name>).
    pattern = re.compile(_js_regex_to_python(managers[0]["matchStrings"][0]))
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    matched = {m.group("depName") for m in pattern.finditer(config)}
    declared = set(re.findall(r"^\s+- repo:\s*https://github\.com/(\S+)", config, re.MULTILINE))
    assert matched == declared, (
        f"custom manager misses {sorted(declared - matched)}; those revs get no updates"
    )


# The one step allowed to run without being `make check`. Widening this set is a
# deliberate edit to a file CODEOWNERS covers, which is the real control.
GATE_SETUP_STEPS = frozenset({"Install opengrep"})


def _run_steps(workflow: str, job: str = "validate") -> list[tuple[str, str]]:
    """(name, run-body) for each step in `job` that executes something.

    Parsed, not pattern-matched. Four separate bypasses of this guard came from
    hand-rolling the YAML: splitting on `- name:`/`- uses:` made a bare `- run:`
    step invisible as a boundary and merged it into its predecessor's body, so a
    `- run: ./deploy.sh` after the allowed install step was scanned as part of
    that step and waved through. Key order, block scalars, and quoting were the
    same accident waiting to happen. A parser knows all of it.

    Name is "" for an unnamed step, which no setup allowlist contains, so such a
    step fails on its own rather than needing a rule of its own.
    """
    steps = yaml.safe_load(workflow)["jobs"][job].get("steps") or []
    return [(step.get("name") or "", step["run"]) for step in steps if "run" in step]


# What a declared setup step may invoke. An allowlist, not a denylist: rejecting
# `make` and `uv` by name let `./scripts/deploy-everything.sh` through a step
# named `Install opengrep`, because it carries neither token. Enumerating what
# may run is the only form that does not need extending once per attack.
_SETUP_COMMANDS = frozenset({"set", "curl", "echo", "sha256sum", "chmod", "sudo", "mv", "opengrep"})

# Wrappers whose argument is itself a command, so the word after one runs too —
# otherwise `sudo ./deploy.sh` reads as the allowed `sudo` and nothing else.
_COMMAND_WRAPPERS = frozenset({"sudo", "env", "command", "exec", "time", "nohup", "xargs"})


def _command_words(body: str) -> list[str] | None:
    """Every token in command position, or None if the body will not parse.

    Line by line, because a newline separates commands and shlex treats it as
    plain whitespace — reading the body as one stream saw only the first command
    of each line. `punctuation_chars` makes `;`, `&&`, `|` and friends their own
    tokens, so the word after an operator is recognised as a new command rather
    than as an argument to the previous one.

    Backslash continuations are joined first. Without that the real install step
    fails its own allowlist: `curl -sSfL -o /tmp/opengrep \\` puts the URL on the
    next physical line, which then reads as a command in its own right.
    """
    words: list[str] = []
    for line in body.replace("\\\n", " ").splitlines():
        try:
            lexer = shlex.shlex(line, punctuation_chars=True)
            lexer.whitespace_split = True
            tokens = list(lexer)
        except ValueError:
            return None
        expect_command = True
        for token in tokens:
            if set(token) <= set(";&|()<>"):
                expect_command = True
                continue
            if expect_command:
                words.append(token)
                expect_command = token in _COMMAND_WRAPPERS
    return words


def _shell_tokens(body: str) -> list[str] | None:
    """Shell-aware tokens of a run body, comments removed; None if unparseable.

    shlex rather than a regex, because a regex cannot tell a comment from a hash
    inside a string. `echo " # x"; uv run …` defeated the previous
    `(^|\\s)#.*$` strip: the space inside the quotes looked like the start of a
    comment, so everything after it — including the `uv` — was deleted before the
    scan. Measured; the same line with the space removed was caught, which is why
    the hole survived review once.

    None on unbalanced quoting so the caller fails closed. Returning the raw
    tokens there would let an unparseable body match nothing and pass.
    """
    try:
        return shlex.split(body, comments=True)
    except ValueError:
        return None


def _gate_violations(validate_job: str, setup_steps: frozenset[str]) -> list[str]:
    """Every run step that is neither the gate nor a declared tool install.

    Classification is by token, not by substring: a step whose *comment* mentions
    `make check` used to be accepted as the gate and skip the smuggling check
    entirely, so a second step carrying that name could run anything it liked.

    The gate body must be exactly the two tokens, and there must be exactly one
    such step. Accepting `make check` merely *among* the tokens let
    `echo make check && uv run …` pass as the gate, and counting nothing let a
    second identical gate step through — neither is the single invocation the
    job is supposed to be.
    """
    problems = []
    gates = 0
    for name, body in _run_steps(validate_job):
        tokens = _shell_tokens(body)
        if tokens is None:
            problems.append(f"step {name!r} has a run body that is not parseable as shell")
            continue
        if tokens == ["make", "check"]:
            gates += 1
            if name != "Run the repository gate":
                problems.append(f"unexpected step running the gate: {name!r}")
            continue
        if name not in setup_steps:
            problems.append(
                f"the Validate job runs {name!r} outside `make check` — a gate belongs "
                "in the Makefile, not in a second copy here"
            )
            continue
        # Command substitution runs a command without putting it in command
        # position, so the allowlist never sees it: `echo "$(./deploy.sh)"`
        # tokenises to a bare `echo`. Rejected outright rather than parsed,
        # since a setup step has no need of it. `${VAR}` is untouched — the
        # install step interpolates its pinned version and digest that way.
        substitutions = [form for form in ("$(", "`") if form in body]
        if substitutions:
            problems.append(
                f"setup step {name!r} uses command substitution {substitutions} — "
                "it hides a command from the allowlist"
            )
            continue
        words = _command_words(body)
        if words is None:
            problems.append(f"step {name!r} has a run body that is not parseable as shell")
            continue
        disallowed = sorted({word for word in words if word not in _SETUP_COMMANDS})
        if disallowed:
            problems.append(
                f"setup step {name!r} runs {disallowed} — a declared setup step may only "
                f"invoke {sorted(_SETUP_COMMANDS)}, so it installs a tool rather than "
                "executing repository code"
            )
    if gates != 1:
        problems.append(f"expected exactly one `make check` step, found {gates}")
    return problems


def test_ci_runs_the_repository_gate_through_make_check():
    """The Validate job must invoke `make check`, not restate its targets.

    Replaces the old per-target assertions. Those pinned CI and the Makefile to
    the same shape, but a *new* target added to `make check` was still absent
    from CI until someone noticed — the assertion could only catch drift in
    steps that already existed. Running the Makefile removes the second copy
    instead of guarding it.
    """
    # No gate may run outside `make check`.
    #
    # Matching each `make check` target name against the `run:` lines was the
    # obvious check and is useless: a reintroduced security step runs
    # `bandit ...`, which contains no "security".
    #
    # Counting `run:` steps replaced it, and held until a scanner needed
    # installing — opengrep ships no action to pin, so it is fetched and
    # checksum-verified in a `run:` block. A count cannot tell that setup step
    # from a smuggled-in gate, so the property is stated directly instead, in
    # `_gate_violations`: exactly one step runs `make check` and nothing else,
    # and every other step is a declared install that executes no repo code.
    #
    # The separate `run: make check` line assertion this replaced is subsumed:
    # `gates != 1` fails when that step is missing, and it checks the parsed
    # command rather than the file's text.
    workflow = (ROOT / ".github/workflows/validate-skills.yml").read_text(encoding="utf-8")
    assert _gate_violations(workflow, GATE_SETUP_STEPS) == []


# The one legitimate gate step, for composing synthetic jobs that need it present.
_GATE_STEP = {"name": "Run the repository gate", "run": "make check"}


def _job(*steps: dict) -> str:
    """A synthetic workflow containing `validate` with the given steps.

    Emitted through the YAML dumper rather than assembled as text, so a fixture
    cannot encode an indentation assumption the parser does not share — the
    thing that made the previous hand-rolled fixtures agree with a broken parser.
    """
    return yaml.safe_dump({"jobs": {"validate": {"steps": list(steps)}}})


def test_a_comment_naming_the_gate_does_not_make_a_step_the_gate():
    """The classification hole: a second step named like the gate ran unchecked.

    `"make check" in body` matched the words wherever they appeared, so a step
    could carry them in a shell comment, take the gate branch, and skip the
    smuggling check entirely — while running whatever it liked.
    """
    smuggler = {"name": "Run the repository gate", "run": "# make check\nuv run --extra dev bandit"}
    assert _gate_violations(_job(_GATE_STEP, smuggler), GATE_SETUP_STEPS) != []


@pytest.mark.parametrize(
    "line",
    [
        'echo " # harmless"; uv run --extra dev bandit',
        "echo ' # harmless'; uv run --extra dev bandit",
    ],
    ids=["double-quoted", "single-quoted"],
)
def test_a_hash_inside_a_string_does_not_hide_a_command(line):
    """A quoted hash defeated the regex that stripped comments.

    `(^|\\s)#.*$` read the space inside the quotes as the start of a comment and
    deleted the rest of the line, `uv` included. Note the space: without it the
    regex did catch this, which is how the hole survived a review that named the
    unspaced form.
    """
    step = {"name": "Install opengrep", "run": line}
    assert _gate_violations(_job(_GATE_STEP, step), GATE_SETUP_STEPS) != []


def test_an_unnamed_run_step_is_its_own_step():
    """An unnamed `- run:` step was absorbed into the previous step's body.

    Splitting on `- name:`/`- uses:` made a bare `- run:` invisible as a
    boundary, so a repository command placed after the allowed install step was
    scanned as part of it — and passed, since it contains neither `make` nor
    `uv`. Parsed as its own step it has no name, which no allowlist contains.
    """
    install = {"name": "Install opengrep", "run": "curl -sSfL -o /tmp/og https://x"}
    job = _job(install, {"run": "./scripts/deploy-everything.sh"}, _GATE_STEP)
    assert [name for name, _ in _run_steps(job)] == ["Install opengrep", "", _GATE_STEP["name"]]
    assert _gate_violations(job, GATE_SETUP_STEPS) != []


def test_the_gate_step_must_be_exactly_make_check():
    """`echo make check && uv run …` contained the tokens without being the gate.

    Adjacency was too weak: any body mentioning the two words in order was
    classified as the gate and skipped the smuggling check.
    """
    extra = {
        "name": "Run the repository gate",
        "run": "echo make check && uv run --extra dev bandit",
    }
    assert _gate_violations(_job(_GATE_STEP, extra), GATE_SETUP_STEPS) != []


def test_exactly_one_gate_step_is_required():
    """Two gate steps, or none, is not the single invocation the job is meant to be."""
    assert _gate_violations(_job(_GATE_STEP, dict(_GATE_STEP)), GATE_SETUP_STEPS) != []
    install = {"name": "Install opengrep", "run": "curl https://x"}
    assert _gate_violations(_job(install), GATE_SETUP_STEPS) != []


@pytest.mark.parametrize(
    "run",
    [
        "./scripts/deploy-everything.sh",
        "sudo ./scripts/deploy-everything.sh",
        "curl -sSfL -o /tmp/og https://x && ./scripts/deploy-everything.sh",
    ],
    ids=["bare", "behind-sudo", "after-&&"],
)
def test_a_declared_setup_step_may_not_run_repository_code(run):
    """A denylist of `make`/`uv` missed everything else the repo can execute.

    A step *named* `Install opengrep` running `./scripts/deploy-everything.sh`
    carries neither token, so it passed while executing repository code outside
    the single gate. The allowlist names what may run instead, which is why the
    sudo and `&&` variants need no rule of their own.
    """
    step = {"name": "Install opengrep", "run": run}
    assert _gate_violations(_job(_GATE_STEP, step), GATE_SETUP_STEPS) != []


@pytest.mark.parametrize(
    "run",
    [
        'echo "$(./scripts/deploy-everything.sh)"',
        'echo "`./scripts/deploy-everything.sh`"',
    ],
    ids=["dollar-paren", "backticks"],
)
def test_command_substitution_cannot_hide_a_command(run):
    """Substitution runs a command without it ever being in command position.

    `echo "$(./deploy.sh)"` tokenises to a bare `echo`, so the allowlist saw
    nothing to object to while the script ran. Only the quoted forms bypassed it
    — unquoted `$(` happens to split into its own token — which is why both are
    pinned rather than the one that failed.
    """
    step = {"name": "Install opengrep", "run": run}
    assert _gate_violations(_job(_GATE_STEP, step), GATE_SETUP_STEPS) != []


def test_the_real_install_step_satisfies_the_command_allowlist():
    """The allowlist has to admit the actual install step, or it is just a ban.

    Pinned because tightening the allowlist without checking this would fail the
    workflow it exists to permit — and the failure would look like a smuggled
    command rather than an over-tight rule.
    """
    workflow = (ROOT / ".github/workflows/validate-skills.yml").read_text(encoding="utf-8")
    install = [body for name, body in _run_steps(workflow) if name == "Install opengrep"]
    assert install, "the Install opengrep step is gone; this test guards the wrong thing now"
    words = _command_words(install[0])
    # Not `or []`: that turned a parse failure into an empty set, which satisfies
    # any allowlist — a malformed body would have passed this assertion instead
    # of failing it.
    assert words is not None, "the install step's run body no longer parses as shell"
    assert set(words) <= _SETUP_COMMANDS


def test_an_unparseable_run_body_fails_closed():
    """Unbalanced quoting cannot be classified, so it is a violation, not a pass."""
    broken = {"name": "Install opengrep", "run": 'echo "unterminated'}
    assert _gate_violations(_job(_GATE_STEP, broken), GATE_SETUP_STEPS) != []


def test_make_check_still_covers_every_gate():
    """The collapse is only safe while `check` actually runs everything.

    Pins the target list, so dropping one from `make check` — which would now
    silently drop it from CI too — fails here instead of quietly narrowing the
    gate.
    """
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    check_rule = re.search(r"^check:(.*)$", makefile, re.M)
    assert check_rule, "Makefile has no `check:` rule"
    targets = set(check_rule.group(1).split())
    required = {
        "validate",
        "validate-rules",
        "version-sync",
        "audit-consistency",
        "index-check",
        "lint",
        "format-check",
        "security",
        "opengrep",
        "typecheck",
        "test",
        "pre-commit",
    }
    assert required <= targets, f"`make check` no longer runs: {sorted(required - targets)}"


def test_validate_rules_hook_surfaces_validator_failure(monkeypatch, tmp_path, capsys):
    """The subprocess payload — run the two validators, set `failed`, surface stderr,
    exit 2 — was untested; only the early-return guards were. Stub the validators as
    failing and assert the hook blocks the call with their output."""
    mod = _load("validate-rules-hook")
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    rule = rules / "bad.md"
    rule.write_text("# Bad\n", encoding="utf-8")
    # The existence guard needs both validator scripts present.
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate-rules.py").touch()
    anatomy = tmp_path / "skills" / "nitpicker" / "scripts"
    anatomy.mkdir(parents=True)
    (anatomy / "check-rules-anatomy.py").touch()
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    def _failing_run(cmd, *a, **k):
        """Simulate a validator that exits non-zero with a violation."""

        class _R:
            """Stand-in for a failed CompletedProcess."""

            returncode = 1
            stdout = ""
            stderr = "RULE VIOLATION: hedged language in bad.md\n"

        return _R()

    monkeypatch.setattr(mod.subprocess, "run", _failing_run)
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(rule)}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "RULE VIOLATION" in capsys.readouterr().err


def test_stop_reminder_flags_untracked_new_command(monkeypatch, capsys):
    """A brand-new unstaged command file appears only in `git ls-files --others`,
    not in either `git diff` form — it must still be flagged."""
    mod = _load("stop-reminder")

    def _run_git(argv, *a, **k):
        """Return an untracked-only path set, mimicking ls-files --others."""
        untracked = "--others" in argv
        paths = ["skills/nitpicker/commands/newcmd.md"] if untracked else []

        class _R:
            """Stand-in for CompletedProcess with NUL-separated stdout."""

            returncode = 0
            stdout = "\0".join([*paths, ""])

        return _R()

    monkeypatch.setattr(mod.subprocess, "run", _run_git)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "skills/nitpicker/commands/newcmd.md" in capsys.readouterr().err


# ── fail-open guards and module entry points (tests-33e74157) ─────────────────

ALL_HOOKS = [
    "validate-json-hook",
    "validate-skill-hook",
    "check-version-sync-hook",
    "ruff-hook",
    "validate-rules-hook",
    "validate-audit-findings-hook",
    "deny-agents-path-hook",
    "stop-reminder",
]


def _script_repo(tmp_path: Path) -> Path:
    """A minimal REPO_ROOT the hooks will accept.

    `_hooklib.repo_root()` only honours $REPO_ROOT when the directory really
    contains scripts/hooks/_hooklib.py, so a bare tmp dir is silently ignored.
    Callers must also drop $CLAUDE_PROJECT_DIR: it is checked first and points at
    the real checkout inside a Claude Code session, which silently wins.
    """
    hooks = tmp_path / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    shutil.copy(HOOKS_DIR / "_hooklib.py", hooks / "_hooklib.py")
    for rel in (
        "scripts/validate-skill.py",
        "scripts/validate-rules.py",
        "scripts/validate-evals.py",
        "scripts/check-version-sync.py",
        "skills/nitpicker/scripts/check-rules-anatomy.py",
        "skills/nitpicker/scripts/findings.py",
    ):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    return tmp_path


# (hook, event payload builder, expected stderr marker). Each payload drives the
# hook to an outcome only main() can produce — a bare import cannot exit 2.
SCRIPT_ENTRY_CASES = [
    ("validate-json-hook", "bad.json", "INVALID JSON"),
    ("validate-skill-hook", "skills/foo/SKILL.md", ""),
    ("check-version-sync-hook", "package.json", "Run ./scripts/bump-version.py"),
    ("ruff-hook", "lint_me.py", "RUFF SAID NO"),
    ("validate-rules-hook", ".claude/rules/a-rule.md", "RULE VIOLATION"),
    ("validate-audit-findings-hook", "docs/audit/findings/a/open/a-11111111.md", "not a valid"),
    ("validate-evals-hook", "skills/foo/evals/evals.json", "EVAL SET BROKEN"),
]


@pytest.mark.parametrize(("name", "rel", "marker"), SCRIPT_ENTRY_CASES)
def test_hook_runs_as_a_script(name, rel, marker, monkeypatch, tmp_path, capsys):
    """Covers each `if __name__ == '__main__'` body, and proves it is wired.

    Deleting `main()` from the guard makes these fail: the module still imports
    cleanly under runpy, but nothing exits 2 and nothing reaches stderr.
    """
    import subprocess as _subprocess

    repo = _script_repo(tmp_path)
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('{"a": 1,}' if rel.endswith(".json") else "x = 1\n", encoding="utf-8")

    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)  # checked first; would win
    monkeypatch.setenv("REPO_ROOT", str(repo))
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/ruff")
    monkeypatch.setattr(
        _subprocess, "run", lambda *_a, **_k: _Result(returncode=1, stdout=marker or "FAILED")
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"file_path": rel}})))

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / f"{name}.py"), run_name="__main__")
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert err.strip(), f"{name}: exited 2 with nothing on stderr"
    if marker:
        assert marker in err


def test_deny_agents_hook_runs_as_a_script(monkeypatch, capsys):
    """The __main__ path must behave like the imported one — it is how the hook actually runs."""
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"tool_input": {"command": "cat .claude/agents/x.md"}})),
    )
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "deny-agents-path-hook.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "DENIED" in capsys.readouterr().err


def test_stop_reminder_runs_as_a_script(monkeypatch, capsys):
    """The __main__ path must behave like the imported one."""
    import subprocess as _subprocess

    def _fake_git(cmd, *a, **k):
        """Report a staged command file, and nothing in the worktree."""
        staged = "--cached" in cmd
        return _Result(stdout="skills/nitpicker/commands/audit.md\0" if staged else "")

    monkeypatch.setattr(_subprocess, "run", _fake_git)
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "stop-reminder.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "skills/nitpicker/commands/audit.md" in capsys.readouterr().err


PATH_GUARD_HOOKS = ["validate-json-hook", "validate-skill-hook", "check-version-sync-hook"]


@pytest.mark.parametrize("name", PATH_GUARD_HOOKS)
def test_path_outside_the_repo_is_a_silent_noop(name, monkeypatch, tmp_path, capsys):
    """Containment: an edit resolving outside REPO_ROOT must not be validated."""
    mod = _load(name)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path / "repo")
    outside = tmp_path / "elsewhere" / "config.json"
    outside.parent.mkdir(parents=True)
    outside.write_text("{,}", encoding="utf-8")  # invalid on purpose
    _run(mod, json.dumps({"tool_input": {"file_path": str(outside)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


VALIDATOR_HOOKS = [
    ("validate-skill-hook", "skills/foo/SKILL.md"),
    ("check-version-sync-hook", "package.json"),
    ("validate-rules-hook", ".claude/rules/a-rule.md"),
    ("validate-evals-hook", "skills/foo/evals/evals.json"),
]


@pytest.mark.parametrize(("name", "rel"), VALIDATOR_HOOKS)
def test_missing_validator_script_is_a_silent_noop(name, rel, monkeypatch, tmp_path, capsys):
    """A checkout without the validator must not traceback — the hook returns."""
    mod = _load(name)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("whatever\n", encoding="utf-8")
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_rules_hook_noops_when_its_shipped_scripts_are_absent(
    monkeypatch, tmp_path, capsys
):
    """`_SHIPPED_ROOT`, not `REPO_ROOT`, is what has to be emptied to reach this.

    The generic `test_missing_validator_script_is_a_silent_noop` case for this
    hook repoints `REPO_ROOT`, which no longer decides where the validators live:
    they are resolved from `__file__` so the hook always runs the copies that
    ship beside it. That made the existing case stop exercising this branch
    without failing — it still passes, just against a real validator. This one
    empties the directory the hook actually looks in.
    """
    mod = _load("validate-rules-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "_SHIPPED_ROOT", tmp_path / "empty")
    target = tmp_path / ".claude" / "rules" / "a-rule.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("whatever\n", encoding="utf-8")

    def _boom(*_a, **_k):
        """Fail loudly if the hook shells out with no validator on disk."""
        raise AssertionError("subprocess ran despite the shipped scripts being absent")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize(
    "rel",
    [
        ".claude/rules-evil/a.md",  # sibling whose name starts with the rules dir
        ".claude/notrules/a.md",  # outside entirely
        ".claude/rules/a.txt",  # inside, wrong suffix
    ],
    ids=["prefix-sibling", "outside", "wrong-suffix"],
)
def test_validate_rules_hook_ignores_paths_outside_the_rules_dir(
    rel, monkeypatch, tmp_path, capsys
):
    """The containment guard, including the case a bare prefix test would miss.

    The check is `realpath(path).startswith(realpath(rules_dir) + os.sep)`. The
    trailing separator is what rejects `.claude/rules-evil/` — without it that
    sibling passes, because its path genuinely starts with the rules directory's
    path. A file inside the tree but not a `.md` is rejected by the same branch.
    """
    mod = _load("validate-rules-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / ".claude" / "rules").mkdir(parents=True, exist_ok=True)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("whatever\n", encoding="utf-8")

    def _boom(*_a, **_k):
        """Fail loudly if the hook runs a validator on a path it should ignore."""
        raise AssertionError(f"validator ran on {rel}, which is outside .claude/rules/")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_json_non_existent_path_is_a_silent_noop(monkeypatch, tmp_path, capsys):
    """A deleted or renamed file is not a JSON defect."""
    mod = _load("validate-json-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    payload = {"tool_input": {"file_path": str(tmp_path / "gone.json")}}
    _run(mod, json.dumps(payload), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_version_sync_surfaces_checker_output_when_it_fails_without_problems(
    monkeypatch, tmp_path, capsys
):
    """The checker exiting non-zero with no parsed problem lines must still reach
    the agent — silence here would report a desync as clean."""
    mod = _load("check-version-sync-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check-version-sync.py").write_text("", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")

    class _R:
        """Stand-in for a checker that failed with output on stdout."""

        returncode = 1
        stdout = "checker blew up"
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _R())
    payload = {"tool_input": {"file_path": str(tmp_path / "package.json")}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "checker blew up" in capsys.readouterr().err


def test_stop_reminder_silent_when_git_fails(monkeypatch, capsys):
    """A git call that fails (detached worktree, broken index) must not be read as
    'nothing pending' *and* must not crash the stop."""
    mod = _load("stop-reminder")

    class _R:
        """Stand-in for git reporting 'not a repository'."""

        returncode = 128
        stdout = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _R())
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    mod.main()
    assert capsys.readouterr().err == ""


def test_deny_agents_unparseable_event_is_a_silent_noop(monkeypatch, capsys):
    """PreToolUse payload that is not a JSON object: the guard returns rather than
    blocking every Bash call or crashing the session."""
    mod = _load("deny-agents-path-hook")
    _run(mod, "not json at all", monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize(
    "command",
    [
        # `**` adjacent to other characters in a component: CPython <3.13 raises
        # ValueError from Path.glob, which the guard used to swallow — while the
        # shell expands it into the protected tree all the same.
        "cat .cl**de/agents/*.md",
        "cat .cl**de/agents/brand-new-agent.md",
        "cp x.md .cl**de/agents/brand-new-agent.md",  # a write, not just a read
        "cd .cl**de && cat agents/*.md",  # via the cd-base expansion
        "printf x > .clau**/agents/new.md",  # via the parent probe
        # Runs longer than two: `str.replace("**", "*")` consumes stars pairwise,
        # so `.cl***de` collapsed to `.cl**de` — still raising, still a bypass.
        # Only a whole-run collapse closes these.
        "cat .cl***de/agents/*.md",
        "cat .cl****de/agents/*.md",
        "cp x.md .cl***de/agents/new.md",
        "cd .cl***de && cat agents/*.md",
        "printf x > .clau***/agents/new.md",
    ],
)
def test_deny_agents_blocks_globstar_spelled_paths(command, monkeypatch):
    """A `**`-adjacent glob must not slip through on 3.11/3.12.

    `Path.glob` raises ValueError there; treating that as "no match" let the
    token pass unexamined. Caught by CodeRabbit on PR #95.
    """
    mod = _load("deny-agents-path-hook")
    assert mod._references_agents(command) is True
    event = json.dumps({"tool_input": {"command": command}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "command",
    [
        # Non-path tokens that ALSO raise in Path.glob on <3.13. A blanket
        # fail-closed on the exception would deny every one of these — this hook
        # gates every Bash call, so that trade is not available.
        'python -c "print(2**8)"',
        "grep a**b file.txt",
        "grep a***b file.txt",
        "awk '{print 2**3}' data.txt",
        "make check",
    ],
)
def test_deny_agents_allows_non_path_tokens_that_break_glob(command, monkeypatch):
    """Ordinary tokens carrying glob metacharacters must not deny the call."""
    mod = _load("deny-agents-path-hook")
    assert mod._references_agents(command) is False
    _run(mod, json.dumps({"tool_input": {"command": command}}), monkeypatch)  # no SystemExit


def test_deny_agents_blocks_globstar_paths_on_a_stdlib_that_rejects_them(monkeypatch):
    """The version-independent form of the test above.

    The real bypass only reproduces on CPython 3.11/3.12, where `Path.glob`
    raises on a `**`-adjacent component; 3.13+ accepts the pattern and blocks it
    without the fallback. CI pins no Python version, so on a modern interpreter
    the parametrized test above passes with or without the fix. This one forces
    the <3.13 behaviour, so a revert of `_shell_glob` fails on every runtime.
    """
    mod = _load("deny-agents-path-hook")
    real_glob = Path.glob

    def _pre_313(self, pattern, *a, **k):
        """Reproduce CPython <3.13 raising on an adjacent '**' pattern."""
        if "**" in pattern:
            raise ValueError("Invalid pattern: '**' can only be an entire path component")
        return real_glob(self, pattern, *a, **k)

    monkeypatch.setattr(Path, "glob", _pre_313)
    assert mod._references_agents("cat .cl**de/agents/*.md") is True
    assert mod._references_agents("cp x.md .cl**de/agents/brand-new-agent.md") is True
    # Longer runs must collapse in one step, not pairwise — `.cl***de` -> `.cl*de`,
    # never `.cl**de` (which would raise again and slip through).
    assert mod._references_agents("cat .cl***de/agents/*.md") is True
    assert mod._references_agents("cp x.md .cl****de/agents/new.md") is True
    # and the non-path tokens that share the raising class stay allowed
    assert mod._references_agents('python -c "print(2**8)"') is False
    assert mod._references_agents("grep a***b file.txt") is False


def test_shell_glob_returns_empty_when_every_spelling_fails(monkeypatch, tmp_path):
    """The last-resort arm: when both the raw and the normalised pattern raise,
    the helper yields nothing rather than propagating out of the hook."""
    mod = _load("deny-agents-path-hook")

    def _raises(*_a, **_k):
        """Simulate glob refusing a pattern with OSError."""
        raise OSError("unsupported pattern")

    monkeypatch.setattr(Path, "glob", _raises)
    assert mod._shell_glob(tmp_path, "a*/x.md") == []
    assert mod._references_agents("cd d*/ && cat a*/x.md") is False


# ── validate-audit-findings-hook: the store's own gate ────────────────────────


def _findings_repo(tmp_path: Path) -> Path:
    """Build a tmp repo carrying a real copy of the shipped findings.py."""
    shipped = tmp_path / "skills" / "nitpicker" / "scripts"
    shipped.mkdir(parents=True)
    # findings.py imports its sibling md_fences, so both travel or neither works.
    for _name in ("findings.py", "md_fences.py"):
        shutil.copy(
            SCRIPTS_DIR.parent / "skills" / "nitpicker" / "scripts" / _name,
            shipped / _name,
        )
    return tmp_path


def test_audit_findings_ignores_a_path_outside_the_store(monkeypatch, tmp_path, capsys):
    """An edit outside docs/audit/findings/ must not invoke findings.py at all."""
    mod = _load("validate-audit-findings-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.subprocess, "run", _never_run("no subprocess for an out-of-store path"))
    other = tmp_path / "README.md"
    other.write_text("hi\n", encoding="utf-8")
    _run(mod, json.dumps({"tool_input": {"file_path": str(other)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def _never_run(msg: str):
    """Build a fake that fails the test if it is ever called."""

    def _boom(*_a, **_k):
        """Fail the test with the caller's message."""
        raise AssertionError(msg)

    return _boom


def test_audit_findings_ledger_failure_exits_2(monkeypatch, tmp_path, capsys):
    """A corrupt resolved.jsonl must reach the agent — the ledger is append-only,
    so a bad record silently accepted is permanent."""
    mod = _load("validate-audit-findings-hook")
    repo = _findings_repo(tmp_path)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    monkeypatch.setattr(mod, "FINDINGS", repo / "skills" / "nitpicker" / "scripts" / "findings.py")
    ledger = repo / "docs" / "audit" / "findings" / "resolved.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("{not json}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(ledger)}}), monkeypatch)
    assert exc.value.code == 2
    assert "resolved.jsonl failed store validation" in capsys.readouterr().err


def test_audit_findings_index_failure_exits_2(monkeypatch, tmp_path, capsys):
    """INDEX.md drift fails `make check`; a silent regeneration failure would hand
    the agent a red build with no cause."""
    mod = _load("validate-audit-findings-hook")
    repo = _findings_repo(tmp_path)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    index = repo / "docs" / "audit" / "findings" / "INDEX.md"
    index.parent.mkdir(parents=True)
    index.write_text("stale\n", encoding="utf-8")

    class _R:
        """Stand-in for an index regeneration that failed."""

        returncode = 1
        stdout = ""
        stderr = "index blew up"

    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _R())
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(index)}}), monkeypatch)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "INDEX.md regeneration failed" in err
    assert "index blew up" in err


# ── the success arms: a passing validator must exit silently ──────────────────
#
# Every subprocess-driven hook had only its failure path tested, so the
# "validator returned 0, stay quiet" branch was never taken. A hook that started
# exiting 2 on success would block every edit in the session.


def test_ruff_hook_silent_when_ruff_is_clean(monkeypatch, tmp_path, capsys):
    """A clean file produces no output and no exit."""
    mod = _load("ruff-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/ruff")
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result())
    _run(mod, json.dumps({"tool_input": {"file_path": str(f)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_version_sync_hook_silent_when_versions_agree(monkeypatch, tmp_path, capsys):
    """Matching manifests produce no output."""
    mod = _load("check-version-sync-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check-version-sync.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(stdout="  OK  all\n"))
    payload = {"tool_input": {"file_path": str(tmp_path / "package.json")}}
    _run(mod, json.dumps(payload), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_skill_hook_silent_when_the_skill_is_valid(monkeypatch, tmp_path, capsys):
    """A valid skill produces no output."""
    mod = _load("validate-skill-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate-skill.py").write_text("", encoding="utf-8")
    skill = tmp_path / "skills" / "foo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: foo\n---\n", encoding="utf-8")
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(stdout="OK\n"))
    _run(mod, json.dumps({"tool_input": {"file_path": str(skill)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_rules_hook_silent_when_both_validators_pass(monkeypatch, tmp_path, capsys):
    """Also covers the loop's continue arm: the first validator returning 0 must
    not short-circuit the second."""
    mod = _load("validate-rules-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate-rules.py").write_text("", encoding="utf-8")
    anatomy = tmp_path / "skills" / "nitpicker" / "scripts"
    anatomy.mkdir(parents=True)
    (anatomy / "check-rules-anatomy.py").write_text("", encoding="utf-8")
    rule = tmp_path / ".claude" / "rules" / "a-rule.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("body\n", encoding="utf-8")

    calls = []

    def _ok(cmd, *a, **k):
        """Record the argv and report success."""
        calls.append(cmd)
        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", _ok)
    _run(mod, json.dumps({"tool_input": {"file_path": str(rule)}}), monkeypatch)
    # Assert WHICH validators ran: a bare `len(calls) == 2` also passes if the
    # hook ran one of them twice and never invoked the other.
    commands = [" ".join(cmd) for cmd in calls]
    assert len(commands) == 2
    assert any("validate-rules.py" in cmd for cmd in commands)
    assert any("check-rules-anatomy.py" in cmd for cmd in commands)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── post-bash-revalidate: the Bash-edit half of the enforcement surface ────────
#
# The five Write|Edit validators never see a `sed -i`/redirection/`git mv` edit;
# this hook is what re-runs the whole-tree gates for those. It takes no stdin —
# it asks git what is dirty — so every test drives it through a fake
# subprocess.run that dispatches on argv.


class _Result:
    """Stand-in for CompletedProcess in the revalidate tests."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        """Store the three fields the hook reads."""
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _revalidate(monkeypatch, tmp_path, *, status, gate=None, gates_on_disk=True, missing_bins=()):
    """Load the hook against a tmp REPO_ROOT with subprocess.run faked.

    `status` is the _Result for `git status`; `gate` is called with each gate's
    argv and returns that gate's _Result (default: success). Either may be an
    exception instance instead, which the fake runner raises — that is how the
    timeout and OSError arms are driven.

    `missing_bins` names binaries `shutil.which` should report absent. The
    default keeps every other test hermetic: without it the preflight would
    depend on `uv` actually being installed on the machine running the suite.
    """
    mod = _load("post-bash-revalidate")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    if gates_on_disk:
        for script, _cmd in mod.GATES:
            p = tmp_path / script
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    def _fake_run(cmd, *a, **k):
        """Dispatch on argv: git status returns `status`, everything else is a gate. An exception
        instance is raised rather than returned, which is how the timeout and OSError arms are
        driven.
        """
        calls.append(list(cmd))
        if cmd[:2] == ["git", "status"]:
            if isinstance(status, BaseException):
                raise status
            return status
        result = gate(cmd) if gate else _Result()
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        mod.shutil, "which", lambda name: None if name in missing_bins else f"/usr/bin/{name}"
    )
    return mod, calls


def _gate_calls(calls: list[list[str]]) -> list[list[str]]:
    """The recorded argv list with the git status call removed."""
    return [c for c in calls if c[:2] != ["git", "status"]]


def test_governed_covers_the_enforcement_surface(monkeypatch, tmp_path):
    """permissions.deny stops Edit/Write on scripts/hooks/ and settings.json but
    never reaches Bash, and no PreToolUse guard matches them. Without these
    entries a `sed -i` disabling a guard ran the gates zero times."""
    governed = _load("post-bash-revalidate").GOVERNED
    assert "scripts/" in governed
    assert ".claude/settings.json" in governed


def test_revalidate_skips_a_gate_whose_binary_is_absent(monkeypatch, tmp_path, capsys):
    """The existence check covered the gate script but never the interpreter, so
    an absent `uv` raised an uncaught FileNotFoundError instead of a skip line."""
    mod, calls = _revalidate(
        monkeypatch,
        tmp_path,
        status=_Result(stdout=" M skills/nitpicker/SKILL.md\n"),
        missing_bins={"uv"},
    )
    mod.main()
    assert [c for c in _gate_calls(calls) if c[0] == "uv"] == []
    assert "gate skipped, uv not on PATH" in capsys.readouterr().err


def test_revalidate_records_a_timed_out_gate_as_a_failure(monkeypatch, tmp_path, capsys):
    """`uv run` resolves an environment on a cold cache; unbounded, an unreachable
    index blocked the session forever with no output. Bounded, it must surface."""
    mod, _ = _revalidate(
        monkeypatch,
        tmp_path,
        status=_Result(stdout=" M skills/nitpicker/SKILL.md\n"),
        # Fixed command string: the hook builds its message from the gate argv it
        # already holds, never from the exception, so nothing here reads .cmd.
        gate=lambda _cmd: subprocess.TimeoutExpired("test-gate", 120),
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "timed out after" in capsys.readouterr().err


def test_revalidate_stops_at_the_first_hung_gate(monkeypatch, tmp_path, capsys):
    """GATE_TIMEOUT bounds each gate independently, so recording a timeout and
    continuing let six hung gates hold this PostToolUse hook for 6 *
    GATE_TIMEOUT. Whatever wedges one `uv run` wedges the rest, so one timeout
    ends the run — and the message has to say so, or a truncated run reads as a
    complete one."""
    mod, calls = _revalidate(
        monkeypatch,
        tmp_path,
        status=_Result(stdout=" M skills/nitpicker/SKILL.md\n"),
        gate=lambda _cmd: subprocess.TimeoutExpired("test-gate", 120),
    )
    assert len(mod.GATES) > 1, "a single gate cannot demonstrate the multiplication"
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert len(_gate_calls(calls)) == 1, "the run continued past a hung gate"
    assert "remaining gates skipped" in capsys.readouterr().err


def test_revalidate_records_a_gate_that_cannot_run_as_a_failure(monkeypatch, tmp_path, capsys):
    """An OSError from exec (permissions, ENOEXEC) must name the gate, not raise."""
    mod, _ = _revalidate(
        monkeypatch,
        tmp_path,
        status=_Result(stdout=" M skills/nitpicker/SKILL.md\n"),
        gate=lambda cmd: OSError("exec format error"),
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "could not run" in capsys.readouterr().err


def test_revalidate_returns_when_git_status_cannot_run(monkeypatch, tmp_path, capsys):
    """git absent or the status call timing out means nothing to scope against —
    return rather than block or raise."""
    mod, calls = _revalidate(
        monkeypatch, tmp_path, status=subprocess.TimeoutExpired(["git", "status"], 120)
    )
    mod.main()
    assert _gate_calls(calls) == []
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── reliability-397b7fec: every hook subprocess call is bounded ───────────────


def _aliases(names: list[ast.alias], wanted: str) -> set[str]:
    """The local names one import statement binds `wanted` to."""
    return {a.asname or a.name for a in names if a.name == wanted}


def _subprocess_run_spellings(tree: ast.Module) -> tuple[set[str], set[str]]:
    """The names one module binds to `subprocess` and to `subprocess.run`.

    Returned as (module aliases, function aliases). Resolving the spelling is
    what stops a new call site from dodging the timeout guard below by changing
    only its import line: `import subprocess as sp` and `from subprocess import
    run` both read as a different name than the literal `subprocess.run`, and a
    matcher keyed to that literal scanned them clean while they ran unbounded.
    """
    modules: set[str] = set()
    funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules |= _aliases(node.names, "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            funcs |= _aliases(node.names, "run")
    return modules, funcs


def _calls_subprocess_run(node: ast.Call, modules: set[str], funcs: set[str]) -> bool:
    """Whether `node` calls subprocess.run under any spelling the module bound."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr == "run" and getattr(func.value, "id", "") in modules
    return isinstance(func, ast.Name) and func.id in funcs


def test_every_hook_subprocess_call_passes_a_timeout():
    """An unbounded shell-out in a hook freezes the session with no output and no
    recovery short of interrupting it. This is a source-level assertion rather
    than a behavioural one so a NEW call site cannot land unbounded."""
    unbounded = []
    for path in sorted(HOOKS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules, funcs = _subprocess_run_spellings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and _calls_subprocess_run(node, modules, funcs)
                and not any(k.arg == "timeout" for k in node.keywords)
            ):
                unbounded.append(f"{path.name}:{node.lineno}")
    assert unbounded == [], f"unbounded subprocess.run call sites: {unbounded}"


@pytest.mark.parametrize(
    "name,event",
    [
        ("validate-skill-hook", {"tool_input": {"file_path": "skills/x/SKILL.md"}}),
        ("check-version-sync-hook", {"tool_input": {"file_path": "package.json"}}),
        ("validate-rules-hook", {"tool_input": {"file_path": ".claude/rules/x.md"}}),
        ("validate-evals-hook", {"tool_input": {"file_path": "skills/x/evals/evals.json"}}),
    ],
)
def test_hook_is_silent_when_its_gate_cannot_run(name, event, monkeypatch, capsys):
    """uv absent (FileNotFoundError) or the gate hung (TimeoutExpired): the hook
    must return, not raise a traceback and not block the edit.

    `ran` is asserted because silence alone does not prove the arm was reached:
    every one of these hooks returns early and silently for a path it does not
    own, so a guard tightening upstream would leave this passing while testing
    nothing.
    """
    mod = _load(name)
    ran = []

    def _boom(*a, **k):
        """Record the call, then simulate uv absent from PATH."""
        ran.append(1)
        raise FileNotFoundError("uv")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps(event), monkeypatch)
    out = capsys.readouterr()
    assert ran, "the hook returned before shelling out — the except arm was never reached"
    assert out.out == "" and out.err == ""


def test_ruff_hook_is_silent_when_ruff_hangs(monkeypatch, tmp_path, capsys):
    """ruff-hook fires on every .py edit and shells out three times, so it is the
    likeliest place for an unbounded call to freeze a session."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ruff")

    def _hang(*a, **k):
        """Simulate ruff exceeding its timeout."""
        raise subprocess.TimeoutExpired(["ruff"], 120)

    monkeypatch.setattr(mod.subprocess, "run", _hang)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_stop_reminder_is_silent_when_git_cannot_run(monkeypatch, tmp_path, capsys):
    """A Stop hook that raises replaces the reminder with a traceback."""
    mod = _load("stop-reminder")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)

    def _boom(*a, **k):
        """Simulate git absent from PATH."""
        raise FileNotFoundError("git")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


# ── agent-loopholes-338dfd70: the protected-write half of the guard ──────────


def _guard_blocks(command: str) -> bool:
    """True if deny-agents-path-hook would block this Bash command."""
    mod = _load("deny-agents-path-hook")
    return mod._references_agents(command) or mod._writes_protected(command)


@pytest.mark.parametrize(
    "command",
    [
        "sed -i 's/PROTECTED/x/' scripts/hooks/deny-unsafe-git-hook.py",
        "sed --in-place s/a/b/ scripts/hooks/ruff-hook.py",
        "echo '{}' > .claude/settings.json",
        "echo x >> scripts/hooks/ruff-hook.py",
        "cp /tmp/evil.py scripts/hooks/ruff-hook.py",
        "mv /tmp/evil.py scripts/hooks/_hooklib.py",
        "rm scripts/hooks/deny-unsafe-git-hook.py",
        "truncate -s 0 .claude/settings.json",
        "cd scripts/hooks && sed -i s/a/b/ ruff-hook.py",
        "git checkout -- scripts/hooks/ruff-hook.py",
        "git restore .claude/settings.json",
        "perl -i -pe s/a/b/ scripts/hooks/stop-reminder.py",
        "tee scripts/hooks/ruff-hook.py < /tmp/evil.py",
        "dd of=scripts/hooks/ruff-hook.py if=/tmp/evil.py",
        "chmod 000 scripts/hooks/deny-agents-path-hook.py",
        # `./` prefix is stripped before the prefix comparison.
        "rm ./scripts/hooks/ruff-hook.py",
    ],
)
def test_guard_blocks_a_write_to_the_enforcement_surface(command):
    """permissions.deny covers Edit/Write on these paths but never Bash, so a
    one-liner could disable every in-session guard unobserved."""
    assert _guard_blocks(command), command


@pytest.mark.parametrize(
    "command",
    [
        # Read is NOT denied for these paths — blocking reads would contradict
        # the permission model and break ordinary work.
        "cat scripts/hooks/ruff-hook.py",
        "grep -rn timeout scripts/hooks/",
        "head -20 .claude/settings.json",
        "python3 -m pytest tests/test_hooks.py",
        "ruff check scripts/hooks/ruff-hook.py",
        "sed -n '1,5p' scripts/hooks/ruff-hook.py",
        # Mutations that land somewhere else entirely.
        "rm -rf /tmp/scratch",
        "git commit -m 'fix: something'",
        "cp README.md /tmp/README.md",
        "echo hi > /tmp/out.txt",
        "sed -i s/a/b/ README.md",
        # A `cd` to an absolute directory outside the repo: relative_to raises,
        # which must read as "not protected" rather than crashing the guard.
        "cd /tmp && rm scratch.txt",
        # `of=` with an empty tail — the split leaves nothing to resolve.
        "dd of= if=/tmp/x",
        # A glob that expands, but to nothing under a protected root.
        "rm scripts/*.py",
    ],
)
def test_guard_allows_reads_and_unrelated_writes(command):
    """Read is not denied on these paths, so blocking a read would contradict the permission model
    and break ordinary work.
    """
    assert not _guard_blocks(command), command


def test_guard_blocks_a_glob_spelled_write(tmp_path):
    """A metacharacter that obscures the literal path is expanded through the same
    machinery the agents half uses, so it resolves rather than reading literally."""
    assert _guard_blocks("rm scripts/ho*ks/ruff-hook.py")


def test_guard_denial_message_names_the_surface(monkeypatch, capsys):
    """A denial that does not say what is protected, or that reading is still allowed, invites the
    same command back in a different spelling.
    """
    mod = _load("deny-agents-path-hook")
    event = {"tool_input": {"command": "sed -i s/a/b/ scripts/hooks/ruff-hook.py"}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(event), monkeypatch)
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "enforcement surface" in err
    assert "Reading" in err


@pytest.mark.parametrize(
    "command",
    [
        "git reset --hard",
        "git reset --hard HEAD~1",
        "git reset --merge",
        "git checkout .",
        "git checkout -- .",
        "git restore .",
        "git restore :/",
        "git apply /tmp/x.patch",
        "git -C . apply /tmp/x.patch",
    ],
)
def test_guard_blocks_an_unscoped_worktree_rewrite(command):
    """These rewrite tracked files under scripts/hooks/ while naming no path, so
    no operand check sees a protected token and the guard would otherwise pass
    them. `git reset --hard` is the plain case."""
    assert _guard_blocks(command), command


@pytest.mark.parametrize(
    "command",
    [
        "git reset --soft HEAD~1",
        "git reset HEAD~1",
        "git checkout -b feature/x",
        "git checkout main",
        "git restore --staged README.md",
        "git stash",
        "git clean -fd",
    ],
)
def test_guard_allows_scoped_and_recoverable_git(command):
    """Over-blocking git makes the guard something to route around. `--soft` and a
    bare reset move refs only; branch switching is ordinary work already covered
    by ask-destructive-restore-hook; clean touches untracked files only, and every
    file under scripts/hooks/ is tracked; stash is recoverable by `stash pop`."""
    assert not _guard_blocks(command), command


def test_git_rewrites_worktree_ignores_a_bare_git():
    """A `git` with no subcommand names nothing to rewrite."""
    assert _load("deny-agents-path-hook")._git_rewrites_worktree(["git"]) is False


def test_guard_blocks_an_absolute_path_under_a_symlinked_checkout(monkeypatch, tmp_path):
    """An absolute token naming the REAL path under a symlinked root must still
    be protected. Comparing against an unresolved _REPO_ROOT made relative_to
    raise, which read as "not protected" — and the glob arm cannot recover it,
    because a plain absolute path carries no metacharacter."""
    real = tmp_path / "real"
    (real / "scripts" / "hooks").mkdir(parents=True)
    target = real / "scripts" / "hooks" / "ruff-hook.py"
    target.write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    mod = _load("deny-agents-path-hook")
    monkeypatch.setattr(mod, "_REPO_ROOT", link)

    via_link = link / "scripts" / "hooks" / "ruff-hook.py"
    assert mod._writes_protected(f"sed -i s/a/b/ {via_link}")
    assert mod._writes_protected(f"sed -i s/a/b/ {target}"), (
        "the real underlying path bypassed the guard under a symlinked checkout"
    )


def test_guard_ignores_an_absolute_path_outside_the_repo(monkeypatch, tmp_path):
    """Resolving both sides must not start capturing paths outside the root."""
    mod = _load("deny-agents-path-hook")
    monkeypatch.setattr(mod, "_REPO_ROOT", tmp_path)
    outside = tmp_path.parent / "elsewhere" / "scripts" / "hooks" / "x.py"
    assert not mod._writes_protected(f"sed -i s/a/b/ {outside}")


@pytest.mark.parametrize("spelling", ["./", ".//", ":/.", ".", ":/", "././"])
def test_git_guard_normalises_whole_tree_pathspecs(spelling):
    """`git add ./` stages exactly what `git add .` stages, so comparing raw
    tokens let three spellings through a check the docstring declares blocked."""
    mod = _load("deny-unsafe-git-hook")
    assert mod._norm_pathspec(spelling) in mod._ADD_ALL, spelling


def test_ruff_hook_keeps_a_completed_failure_when_a_later_call_errors(
    monkeypatch, tmp_path, capsys
):
    """A tool error must not erase a finding an earlier validator already
    produced — that silently drops an enforcement result."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/ruff")
    calls = []

    def _run_ruff(cmd, *a, **k):
        """Fail the first ruff call, then time out."""
        calls.append(cmd)
        if len(calls) == 1:
            return _Result(returncode=2, stderr="ruff: bad configuration\n")
        raise subprocess.TimeoutExpired(["ruff"], 120)

    monkeypatch.setattr(mod.subprocess, "run", _run_ruff)
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    assert exc.value.code == 2
    assert "bad configuration" in capsys.readouterr().err
    # Without this the test also passes when the hook stops at the first failing
    # pass — the TimeoutExpired arm this test exists for would never be reached.
    assert len(calls) == 2, "the second ruff call never ran; the timeout arm was not exercised"


def test_ruff_hook_returns_when_nothing_had_failed_yet(monkeypatch, tmp_path, capsys):
    """With no completed failure to preserve, a tool error stays silent."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/ruff")

    ran = []

    def _boom(*a, **k):
        """Fail before any validator completes."""
        ran.append(1)
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    # Silence alone does not prove the arm was reached: an early return before the
    # hook ever shells out is just as quiet.
    assert ran, "the hook returned before shelling out — the except arm was never reached"
    assert out.out == "" and out.err == ""


def test_ruff_hook_reports_a_failed_fix_when_the_check_passes(monkeypatch, tmp_path, capsys):
    """`ruff check --fix` failing on its own — bad config, a syntax error — while
    the final check comes back clean. The fix pass's output is the only place
    that cause appears, so returning silently loses it entirely."""
    mod = _load("ruff-hook")
    target = tmp_path / "x.py"
    target.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/ruff")
    calls = []

    def _run_ruff(cmd, *a, **k):
        """Fail the --fix pass; pass the format and the final check."""
        calls.append(cmd)
        if len(calls) == 1:
            return _Result(returncode=2, stderr="ruff: bad configuration\n")
        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", _run_ruff)
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    assert exc.value.code == 2
    assert "bad configuration" in capsys.readouterr().err
    # The premise is that the passing format and check passes still ran after the
    # failing --fix. Asserting only stderr also passes if the hook bailed at call 1.
    assert len(calls) == 3, "the hook stopped at the failing --fix instead of continuing"


def test_validate_rules_hook_keeps_a_completed_failure(monkeypatch, tmp_path, capsys):
    """The rule validator runs first and the anatomy checker second. A failure
    already collected from the first has to survive an error in the second —
    the branch is reachable without this test, but nothing pinned the outcome."""
    mod = _load("validate-rules-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate-rules.py").write_text("", encoding="utf-8")
    anatomy = tmp_path / "skills" / "nitpicker" / "scripts"
    anatomy.mkdir(parents=True)
    (anatomy / "check-rules-anatomy.py").write_text("", encoding="utf-8")
    rule = tmp_path / ".claude" / "rules" / "x.md"
    rule.parent.mkdir(parents=True)
    rule.write_text("# R\n", encoding="utf-8")
    calls = []

    def _run_validator(cmd, *a, **k):
        """Fail the rule validator, then make the anatomy checker unrunnable."""
        calls.append(cmd)
        if len(calls) == 1:
            return _Result(returncode=1, stdout="RULE VIOLATION: hedged language\n")
        raise FileNotFoundError("python3")

    monkeypatch.setattr(mod.subprocess, "run", _run_validator)
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps({"tool_input": {"file_path": str(rule)}}), monkeypatch)
    assert exc.value.code == 2
    assert "RULE VIOLATION" in capsys.readouterr().err
    # Without this the test also passes when the hook stops at the failing rule
    # validator — the anatomy checker's FileNotFoundError arm is the point here.
    assert len(calls) == 2, "the anatomy checker never ran; its error arm was not exercised"


def test_revalidate_returns_when_not_a_git_tree(monkeypatch, tmp_path, capsys):
    """A non-zero `git status` means there is nothing to scope against — the hook
    must return, not run every gate against an unknown tree."""
    mod, calls = _revalidate(monkeypatch, tmp_path, status=_Result(returncode=128))
    mod.main()
    assert _gate_calls(calls) == []
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_revalidate_ignores_a_dirty_path_outside_the_governed_set(monkeypatch, tmp_path, capsys):
    """An ungoverned dirty path must not trigger the whole-tree gates."""
    mod, calls = _revalidate(monkeypatch, tmp_path, status=_Result(stdout=" M README.md\n"))
    mod.main()
    assert _gate_calls(calls) == []
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "porcelain",
    [
        " M skills/nitpicker/SKILL.md\n",
        " M .claude/rules/skill-style.md\n",
        "?? docs/audit/findings/tests/open/tests-abcd1234.md\n",
        " M package.json\n",
        " M pyproject.toml\n",
        " M .claude-plugin/plugin.json\n",
        " M .claude-plugin/marketplace.json\n",
        " M .release-please-manifest.json\n",
    ],
)
def test_revalidate_runs_every_gate_for_each_governed_marker(
    monkeypatch, tmp_path, capsys, porcelain
):
    """Every entry in GOVERNED must actually trigger the gates — a marker that
    stopped matching would silently stop validating that whole tree."""
    mod, calls = _revalidate(monkeypatch, tmp_path, status=_Result(stdout=porcelain))
    mod.main()  # all gates pass -> no SystemExit
    # Assert WHICH gates ran, not just how many: a count alone also passes if one
    # gate ran len(GATES) times and the rest never fired.
    ran = [" ".join(c) for c in _gate_calls(calls)]
    assert len(ran) == len(mod.GATES)
    for _script, cmd in mod.GATES:
        assert " ".join(cmd) in ran, f"gate never ran: {' '.join(cmd)}"
    assert capsys.readouterr().err == ""


def test_revalidate_asks_git_for_ignored_paths_too(monkeypatch, tmp_path):
    """The findings store supports being gitignored; plain --porcelain omits
    ignored paths, so a Bash edit there would skip the findings gates."""
    mod, calls = _revalidate(monkeypatch, tmp_path, status=_Result(stdout=""))
    mod.main()
    assert calls[0] == ["git", "status", "--porcelain", "--ignored"]


def test_revalidate_reports_a_missing_gate_script_instead_of_skipping_silently(
    monkeypatch, tmp_path, capsys
):
    """A silently skipped gate is indistinguishable from a passing one."""
    mod, calls = _revalidate(
        monkeypatch, tmp_path, status=_Result(stdout=" M skills/x/SKILL.md\n"), gates_on_disk=False
    )
    mod.main()
    assert _gate_calls(calls) == []
    err = capsys.readouterr().err
    assert "gate skipped" in err
    assert "scripts/validate-skill.py not found" in err


def test_revalidate_exits_2_with_the_failing_gate_output(monkeypatch, tmp_path, capsys):
    """The agent sees only stderr, so the failing gate's own output has to reach it."""

    def _gate(cmd):
        """Fail the skill validator, pass everything else."""
        if "validate-skill.py" in " ".join(cmd):
            return _Result(returncode=1, stdout="  ERROR  SKILL.md: missing frontmatter")
        return _Result()

    mod, _ = _revalidate(
        monkeypatch, tmp_path, status=_Result(stdout=" M skills/x/SKILL.md\n"), gate=_gate
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "missing frontmatter" in capsys.readouterr().err


def test_revalidate_names_a_silent_failing_gate(monkeypatch, tmp_path, capsys):
    """A gate exiting non-zero with no output would otherwise block the call with
    an empty message — the fallback must name the command and the exit code."""

    def _gate(cmd):
        """Fail the version-sync gate with blank output."""
        if "check-version-sync.py" in " ".join(cmd):
            return _Result(returncode=3, stdout="   ", stderr="")
        return _Result()

    mod, _ = _revalidate(
        monkeypatch, tmp_path, status=_Result(stdout=" M package.json\n"), gate=_gate
    )
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "check-version-sync.py" in err
    assert "exit 3" in err


def test_revalidate_runs_as_a_script(monkeypatch, tmp_path, capsys):
    """The `__main__` body, proven by an outcome only main() can produce: a
    governed dirty path plus a failing gate must exit 2 with that gate's output.

    runpy re-executes the module, so the fake is installed on the shared
    `subprocess` module rather than on a module attribute.
    """
    import subprocess as _subprocess

    # _script_repo, not a bare tmp_path: repo_root() only honours $REPO_ROOT for a
    # directory that really contains scripts/hooks/_hooklib.py, so a tmp dir
    # holding just the gate files is rejected and the real checkout wins.
    repo = _script_repo(tmp_path)
    for script, _cmd in _load("post-bash-revalidate").GATES:
        p = repo / script
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")

    def _fake_run(cmd, *a, **k):
        """Report a governed dirty path, then fail every gate."""
        if cmd[:2] == ["git", "status"]:
            return _Result(stdout=" M skills/nitpicker/SKILL.md\n")
        return _Result(returncode=1, stdout="GATE SAID NO")

    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)  # checked first; would win
    monkeypatch.setenv("REPO_ROOT", str(repo))
    monkeypatch.setattr(_subprocess, "run", _fake_run)
    # Pin the root the hook actually resolved, so this cannot silently fall back
    # to the real checkout again and pass for the wrong reason.
    assert repo == _load("post-bash-revalidate").REPO_ROOT
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "post-bash-revalidate.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "GATE SAID NO" in capsys.readouterr().err


# ── deny-unsafe-git-hook: the two git-write mandates (agent-hooks-0c0fbd4c) ────


class _Exploding:
    """A stdin stand-in whose read() raises — drives each hook's fail-closed arm.

    `load_event` catches only JSONDecodeError/EOFError, so this propagates to the
    module-level `except Exception`, which is the arm under test.
    """

    def read(self, *_a):
        """Raise while reading stdin, to drive the fail-closed arm."""
        raise RuntimeError("stdin exploded")


def _bash(command: str) -> str:
    """Wrap a shell command in a PreToolUse Bash event payload."""
    return json.dumps({"tool_input": {"command": command}})


NEW_GUARDS = ["deny-unsafe-git-hook", "guard-ctx-ok-hook", "ask-destructive-restore-hook"]


@pytest.mark.parametrize("name", NEW_GUARDS)
@pytest.mark.parametrize(
    "payload", ["", "null", "[]", "not json"], ids=["empty", "null", "list", "garbage"]
)
def test_new_guards_are_silent_on_an_unparseable_event(name, payload, monkeypatch, capsys):
    """load_event() returns None for all of these; every guard must no-op rather
    than crash the tool call or block it."""
    _run(_load(name), payload, monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize(
    ("command", "denied"),
    [
        ("git --no-pager commit --no-verify -m x", True),  # valueless global flag
        ("git -c user.name=x commit --no-verify -m y", True),  # value-taking global opt
        ("git --git-dir .git commit --no-verify -m z", True),
        ("FOO=1 git commit --no-verify -m w", True),  # env prefix before git
        ("echo hi && git -C . commit --no-verify -m v", True),  # not the first stage
        ("git --version", False),  # flags only, no subcommand
        ("git --no-pager log --oneline", False),  # a read, but not a guarded write
        ("/usr/bin/git commit --no-verify -m p", True),  # path-qualified git
    ],
)
def test_git_guard_finds_the_subcommand_past_global_options(command, denied, monkeypatch, capsys):
    """Regression: a `(?:\\s+-\\S+)*` pattern walks past `-C dir` and never reaches
    `commit`, so `git -C . commit --no-verify` bypassed the guard entirely."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "_current_branch", lambda: "feature/x")
    if denied:
        with pytest.raises(SystemExit) as exc:
            _run(mod, _bash(command), monkeypatch)
        assert exc.value.code == 2
    else:
        _run(mod, _bash(command), monkeypatch)
        assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("command", "denied"),
    [
        ("git --no-pager log --oneline # ctx-ok", True),  # valueless global flag
        ("git -C . diff HEAD # ctx-ok", True),  # value-taking global opt
        ("git log --oneline | head -20 # ctx-ok", True),  # read in a later stage
        ("git --version # ctx-ok", False),  # flags only — bare `git`, a mutation verb
        ("git -c user.name=x commit -m y # ctx-ok", False),  # mutation past a global opt
        ("git status # ctx-ok", False),  # short fixed output, exempt by the rule
    ],
)
def test_ctx_ok_guard_classifies_git_by_subcommand(command, denied, monkeypatch, capsys):
    """`git` alone is a mutation verb, but `git log` is a read — the hatch must be
    judged on the subcommand, and on every pipeline stage, not just the first."""
    mod = _load("guard-ctx-ok-hook")
    if denied:
        with pytest.raises(SystemExit) as exc:
            _run(mod, _bash(command), monkeypatch)
        assert exc.value.code == 2
        assert "read" in capsys.readouterr().err
    else:
        _run(mod, _bash(command), monkeypatch)
        assert capsys.readouterr().err == ""


def _oserror(*_a, **_k):
    """subprocess.run stand-in raising the class the guards actually catch.

    `_never_run` raises AssertionError, which those handlers deliberately do NOT
    swallow — using it here would test the harness, not the guard.
    """
    raise OSError("git unavailable")


@pytest.mark.parametrize(
    "command",
    [
        'git commit --no-verify -m "skip the gates"',
        "git commit -n -m short",
        'git -C . commit --no-verify -m "with a global flag"',
    ],
)
def test_git_guard_denies_no_verify(command, monkeypatch, capsys):
    """--no-verify skips the pre-commit validators guarding skills/, the version
    manifests and the findings store — commit-gate-integrity.md says nothing
    enforced this."""
    mod = _load("deny-unsafe-git-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 2
    assert "--no-verify" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "git add -A",
        "git add --all",
        "git add .",
        "git add :/",
        "git add -A -- .",
        "git -C . add -A",  # past a value-taking global option
        "echo staged && git add --all",  # not the first stage
        "FOO=1 git add .",  # env prefix before git
    ],
)
def test_git_guard_denies_staging_the_whole_tree(command, monkeypatch, capsys):
    """`git add -A` is a recurring source of commits carrying files the change
    never touched — scratch output, local config, editor artifacts. Blocking the
    flag alone would move the hazard to `git add .`, which stages the same set
    from the repo root, so the whole stage-everything class is denied."""
    mod = _load("deny-unsafe-git-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 2
    assert "stages the whole tree" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "git add README.md",
        "git add tests/test_hooks.py docs/audit/findings/INDEX.md",
        "git add -u",  # tracked files only — stages no new file
        "git add -p",  # interactive, per hunk
        "git add --update docs/",
        'git commit -m "git add -A is banned"',  # the token as message content
        "grep -rn 'git add -A' docs/",  # the token as search content
    ],
)
def test_git_guard_allows_targeted_staging(command, monkeypatch, capsys):
    """The guard must not push the agent off `git add` entirely: explicit
    pathspecs and `-u` are the intended replacements, and the token appearing as
    quoted content is not an invocation."""
    mod = _load("deny-unsafe-git-hook")
    _run(mod, _bash(command), monkeypatch)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "ordinary"',
        "git commit --amend",
        "make check",
        "grep -n 'no-verify' README.md",  # the flag as *content*, not as a flag
        "",
    ],
)
def test_git_guard_allows_ordinary_commands(command, monkeypatch, capsys):
    """The guard must not obstruct routine git use."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "_current_branch", lambda: "feature/x")
    _run(mod, _bash(command), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_git_guard_denies_push_to_protected_refspec(monkeypatch, capsys):
    """An explicit refspec reaches main regardless of what HEAD is."""
    mod = _load("deny-unsafe-git-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash("git push origin main"), monkeypatch)
    assert exc.value.code == 2
    assert "protected branch" in capsys.readouterr().err


def test_git_guard_allows_push_to_a_feature_refspec(monkeypatch, capsys):
    """Pushing a feature branch is the intended path and stays allowed."""
    mod = _load("deny-unsafe-git-hook")
    _run(mod, _bash("git push origin feature/x"), monkeypatch)
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("command", "branch", "denied"),
    [
        ("git push origin feature/x main", "wip", True),  # protected in a LATER refspec
        ("git push origin feature:feature main:main", "wip", True),  # ...in colon form
        ("git push origin +main", "wip", True),  # force-push shorthand
        ("git push origin refs/heads/main", "wip", True),  # fully qualified
        ("git push --all origin", "wip", True),  # names no refspec, pushes every ref
        ("git push --mirror origin", "wip", True),
        ("git push origin HEAD", "main", True),  # HEAD resolves to the protected branch
        ("git push origin HEAD", "wip", False),  # ...and here it does not
        ("git push origin feature/x topic", "main", False),  # explicit refs; HEAD is moot
    ],
)
def test_git_guard_checks_every_refspec_not_just_the_first(
    command, branch, denied, monkeypatch, capsys
):
    """Regression: only `operands[1]` was checked, so `git push origin feature main`
    reached main through a refspec the guard never looked at. `--all`/`--mirror`
    name no refspec at all and were judged on HEAD, which does not bound them."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "_current_branch", lambda: branch)
    if denied:
        with pytest.raises(SystemExit) as exc:
            _run(mod, _bash(command), monkeypatch)
        assert exc.value.code == 2
        assert "protected branch" in capsys.readouterr().err
    else:
        _run(mod, _bash(command), monkeypatch)
        assert capsys.readouterr().err == ""


@pytest.mark.parametrize(("branch", "denied"), [("main", True), ("master", True), ("wip", False)])
def test_git_guard_judges_a_bare_push_on_head(branch, denied, monkeypatch, capsys):
    """`git push` with no refspec follows HEAD's upstream, so HEAD decides."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "_current_branch", lambda: branch)
    if denied:
        with pytest.raises(SystemExit) as exc:
            _run(mod, _bash("git push"), monkeypatch)
        assert exc.value.code == 2
    else:
        _run(mod, _bash("git push"), monkeypatch)
        assert capsys.readouterr().err == ""


def test_git_guard_denies_when_the_branch_cannot_be_resolved(monkeypatch, capsys):
    """Fail closed: an unresolvable HEAD cannot prove the push is safe."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "_current_branch", lambda: None)
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash("git push"), monkeypatch)
    assert exc.value.code == 2
    assert "unknown" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("command", "denied"),
    [
        ("git push origin feature # push to main later", False),  # `main` in a comment
        ('git commit -m "merge main into feature" # ctx-ok', False),  # ...and in a message
        ("make check 2>&1 && git push origin main", True),  # still seen past a redirect
        ("git status # look\ngit push origin main", True),  # still seen on line 2
        ("git push -qf origin main", True),  # clustered short flags
        ('git push origin "main"', True),  # quoted refspec is still a refspec
    ],
)
def test_git_guard_ignores_comments_and_quotes_without_going_blind(
    command, denied, monkeypatch, capsys
):
    """CodeRabbit on #97: `git_calls` did not strip comments, so a trailing
    `# push to main later` put `main` in the operand list and denied a feature
    push. The fix must not buy that by losing sight of a real push."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "_current_branch", lambda: "feature/x")
    if denied:
        with pytest.raises(SystemExit) as exc:
            _run(mod, _bash(command), monkeypatch)
        assert exc.value.code == 2
    else:
        _run(mod, _bash(command), monkeypatch)
        assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    ("command", "denied"),
    [
        ("git push \\\n  origin main", True),  # the bypass: continuation hid the refspec
        ("git push \\\n  origin \\\n  main", True),
        ("git commit \\\n  --no-verify -m x", True),
        ("git push \\\n  origin feature/x", False),  # a feature push is still fine
        ("echo a # note \\\ngit push origin main", True),  # `\` inside a comment joins nothing
    ],
)
def test_git_guard_sees_past_a_line_continuation(command, denied, monkeypatch, capsys):
    """A backslash-newline is a continuation, not a stage boundary.

    Splitting on it parsed `git push \\<newline> origin main` as ('push', ['\\\\']):
    one operand, so `_push_targets_protected` fell through to the HEAD check, saw
    a feature branch and ALLOWED a push to main. `git commit \\<newline>
    --no-verify` slipped through the same way. Both mandates this hook exists to
    enforce were bypassable by pressing enter mid-command.
    """
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "_current_branch", lambda: "feature/x")
    if denied:
        with pytest.raises(SystemExit) as exc:
            _run(mod, _bash(command), monkeypatch)
        assert exc.value.code == 2
    else:
        _run(mod, _bash(command), monkeypatch)
        assert capsys.readouterr().err == ""


def test_git_guard_current_branch_reads_git(monkeypatch, tmp_path):
    """HEAD decides when no refspec does, so the branch is read from git itself."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(stdout="topic\n"))
    assert mod._current_branch() == "topic"


@pytest.mark.parametrize("mode", ["non-zero-exit", "raises"])
def test_git_guard_current_branch_returns_none_when_git_fails(mode, monkeypatch, tmp_path):
    """Both failure arms return None, which the caller treats as fail-closed."""
    mod = _load("deny-unsafe-git-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    if mode == "raises":
        monkeypatch.setattr(mod.subprocess, "run", _oserror)
    else:
        monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(returncode=128))
    assert mod._current_branch() is None


def test_git_guard_runs_as_a_script_and_fails_closed(monkeypatch, capsys):
    """Both the `__main__` wiring and its fail-closed exception arm."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(_bash("git commit --no-verify -m x")))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "deny-unsafe-git-hook.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "--no-verify" in capsys.readouterr().err

    monkeypatch.setattr(sys, "stdin", _Exploding())
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "deny-unsafe-git-hook.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "failed internally" in capsys.readouterr().err


# ── guard-ctx-ok-hook: validate the escape hatch (agent-hooks-d003dd20) ───────


@pytest.mark.parametrize(
    "command",
    [
        "grep -rn TODO src/ # ctx-ok",
        "cat big.log # ctx-ok",
        "find . -name '*.py' # ctx-ok",
        "git log --oneline | head -20 # ctx-ok",  # pipeline head is the verb
        "curl https://example.com # ctx-ok",
    ],
)
def test_ctx_ok_guard_denies_the_hatch_on_read_commands(command, monkeypatch, capsys):
    """The hatch is for a state mutation; claiming it on a read is what it exists to catch."""
    mod = _load("guard-ctx-ok-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 2
    assert "ctx-ok" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m x # ctx-ok",  # state mutation
        "make check # ctx-ok",  # pass/fail runner
        "echo hi # ctx-ok",  # fixed output
        "rm -f stale.tmp # ctx-ok",
        "FOO=1 git push origin feature # ctx-ok",  # env prefix skipped
        "/usr/bin/git status # ctx-ok",  # path-qualified verb
        # The shipped-tool runner. use-uv-runner.md mandates plain python3
        # for skills/*/scripts/, and these store subcommands write files —
        # denying them left an agent that had edited a shipped script with
        # no sanctioned way to file a finding at all.
        "python3 skills/nitpicker/scripts/findings.py new --auditor audit x # ctx-ok",
        "python3 skills/nitpicker/scripts/findings.py resolve id --status fixed # ctx-ok",
        "python skills/nitpicker/scripts/findings.py index # ctx-ok",
        "grep -rn TODO src/",  # no hatch claimed — the plugin owns this
    ],
)
def test_ctx_ok_guard_allows_must_run_direct_and_unclaimed(command, monkeypatch, capsys):
    """An unmarked command belongs to the routing guard, not this one."""
    mod = _load("guard-ctx-ok-hook")
    _run(mod, _bash(command), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize(
    "command",
    [
        "grep -rn '# ctx-ok' .claude/rules/",  # marker mid-command, as an argument
        "grep -rn '# ctx-ok'",  # ...and at the end, but quoted
        'rg "# ctx-ok" scripts/',
    ],
)
def test_ctx_ok_guard_ignores_the_marker_as_content(command, monkeypatch, capsys):
    """The hatch is a TRAILING comment. A command searching for the literal string
    carries the marker without claiming it — matching anywhere denied a plain grep."""
    mod = _load("guard-ctx-ok-hook")
    _run(mod, _bash(command), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize(
    "command",
    [
        'git commit -m "fix: handle a|b" # ctx-ok',  # `|` inside the message
        'git commit -m "a && b" # ctx-ok',
        "git commit -m 'a; b' # ctx-ok",
        "make check 2>&1 # ctx-ok",  # the `&` of a redirection is not a separator
        "make check 1>&2 # ctx-ok",
        "git status # look\ngit commit -m x # ctx-ok",  # comment on an earlier LINE
    ],
)
def test_ctx_ok_guard_does_not_split_inside_quotes_or_redirections(command, monkeypatch, capsys):
    """CodeRabbit on #97: operator splitting ignored quoting, so a commit message
    containing `|` produced a second stage beginning `b"` and the guard denied it.

    Two more the review did not name, found by asserting against the fix: `2>&1`
    split on the `&` into a stage `1`, and comment stripping without re.MULTILINE
    left an earlier line's `#` to become a stage verb.
    """
    mod = _load("guard-ctx-ok-hook")
    _run(mod, _bash(command), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


@pytest.mark.parametrize(
    "command",
    [
        'gh pr create --base main \\\n  --title "x" \\\n  --body-file b.md # ctx-ok',
        "cd /repo \\\n  && git commit -m x # ctx-ok",
        "git push \\\n  origin feature/x # ctx-ok",
    ],
)
def test_ctx_ok_guard_allows_a_continued_command(command, monkeypatch, capsys):
    """The same continuation bug seen from the false-positive side: the second
    physical line became its own stage, so `--title` was classified as the verb
    and denied as unrecognised. It fired on a real `gh pr create` in session."""
    mod = _load("guard-ctx-ok-hook")
    _run(mod, _bash(command), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_ctx_ok_guard_fails_closed_on_an_unrecognised_verb(monkeypatch, capsys):
    """An unknown command is exactly what the hatch must not silently cover."""
    mod = _load("guard-ctx-ok-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash("frobnicate --all # ctx-ok"), monkeypatch)
    assert exc.value.code == 2
    assert "unrecognised" in capsys.readouterr().err


def test_ctx_ok_guard_fails_closed_on_a_hatch_with_no_command(monkeypatch, capsys):
    """A bare hatch, and an assignment-only line, resolve to no verb at all —
    reported as empty rather than misdescribed as an unrecognised command."""
    mod = _load("guard-ctx-ok-hook")
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash("# ctx-ok"), monkeypatch)
    assert exc.value.code == 2
    assert "empty command" in capsys.readouterr().err


@pytest.mark.parametrize(
    "command",
    [
        "cd /repo && git push origin feature # ctx-ok",
        "cd scripts && chmod +x a.py # ctx-ok",
        "pushd /repo && git commit -m x && popd # ctx-ok",
        "export GIT_AUTHOR_NAME=x # ctx-ok",
        "source .venv/bin/activate && pip install -e . # ctx-ok",
    ],
)
def test_ctx_ok_guard_allows_navigation_and_shell_state(command, monkeypatch, capsys):
    """Regression: `cd` was not in the allowlist, so the fail-closed arm denied
    `cd /repo && git push ...` as an unrecognised command. It fired on a real
    push during this session — the second allowlist hole to do so, after the
    `VAR=value` prefix above.

    Classification is per stage, so a `cd` prefix is judged on its own merits and
    a missing entry rejects the whole command however ordinary the rest of it is.
    """
    mod = _load("guard-ctx-ok-hook")
    _run(mod, _bash(command), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_ctx_ok_guard_allows_an_assignment_prefixed_mutation(monkeypatch, capsys):
    """Regression: the first version read only the first pipeline stage, so a
    leading `VAR=value` yielded no verb and the hook denied an ordinary `cp`.
    It fired on a real command during this session."""
    mod = _load("guard-ctx-ok-hook")
    _run(
        mod, _bash("S=/tmp/x && cp $S/a.py scripts/ && chmod +x scripts/a.py # ctx-ok"), monkeypatch
    )
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_ctx_ok_guard_ignores_an_empty_command(monkeypatch, capsys):
    """An empty command claims nothing."""
    mod = _load("guard-ctx-ok-hook")
    _run(mod, _bash(""), monkeypatch)
    assert capsys.readouterr().err == ""


def test_ctx_ok_guard_runs_as_a_script_and_fails_closed(monkeypatch, capsys):
    """The __main__ path must deny too — a guard that exits 0 on error enforces nothing."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(_bash("grep -rn TODO src/ # ctx-ok")))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "guard-ctx-ok-hook.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "ctx-ok" in capsys.readouterr().err

    monkeypatch.setattr(sys, "stdin", _Exploding())
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "guard-ctx-ok-hook.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "failed internally" in capsys.readouterr().err


# ── ask-destructive-restore-hook: confirm before discard (agent-hooks-855cb93b) ─


def _restore_mod(monkeypatch, tmp_path, dirty: list[str]):
    """Load the restore guard with git status faked to `dirty`."""
    mod = _load("ask-destructive-restore-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    # `git status --porcelain -z`: NUL-terminated records, no quoting.
    porcelain = "".join(f" M {p}\0" for p in dirty)
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(stdout=porcelain))
    return mod


def _ask_payload(capsys) -> dict:
    """The structured permission decision the hook wrote to stdout."""
    return json.loads(capsys.readouterr().out)["hookSpecificOutput"]


@pytest.mark.parametrize(
    "command",
    ["git checkout -- README.md", "git restore README.md", "git checkout -- .", "git restore ."],
)
def test_restore_guard_asks_when_the_target_is_dirty(command, monkeypatch, tmp_path, capsys):
    """Uncommitted content at the target exists nowhere else — no reflog, no stash."""
    mod = _restore_mod(monkeypatch, tmp_path, ["README.md"])
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 0  # `ask` is a decision, not a block
    out = _ask_payload(capsys)
    assert out["permissionDecision"] == "ask"
    assert out["hookEventName"] == "PreToolUse"
    assert "UNCOMMITTED" in out["permissionDecisionReason"]
    assert "README.md" in out["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "git checkout -b feature",  # branch creation, not a restore
        "git checkout feature",  # branch switch, not a restore
        "git status",
        "git log --oneline",
        "",
    ],
)
def test_restore_guard_ignores_non_restore_commands(command, monkeypatch, tmp_path, capsys):
    """Only the discarding forms are the guard's business."""
    mod = _restore_mod(monkeypatch, tmp_path, ["README.md"])
    _run(mod, _bash(command), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_restore_guard_silent_when_the_target_is_clean(monkeypatch, tmp_path, capsys):
    """A clean target means an ordinary revert; interrupting it would train the prompt to be
    ignored.
    """
    mod = _restore_mod(monkeypatch, tmp_path, [])
    _run(mod, _bash("git checkout -- README.md"), monkeypatch)
    assert capsys.readouterr().out == ""


def test_restore_guard_ignores_untracked_files(monkeypatch, tmp_path, capsys):
    """An untracked file is not destroyed by a restore, so it must not prompt."""
    mod = _load("ask-destructive-restore-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(stdout="?? scratch.txt\0"))
    _run(mod, _bash("git checkout -- ."), monkeypatch)
    assert capsys.readouterr().out == ""


def test_restore_guard_truncates_a_long_dirty_list(monkeypatch, tmp_path, capsys):
    """A prompt has to stay readable to be read at all."""
    mod = _restore_mod(monkeypatch, tmp_path, [f"f{i}.py" for i in range(9)])
    with pytest.raises(SystemExit):
        _run(mod, _bash("git checkout -- ."), monkeypatch)
    assert "(+4 more)" in _ask_payload(capsys)["permissionDecisionReason"]


@pytest.mark.parametrize("mode", ["non-zero-exit", "raises"])
def test_restore_guard_asks_when_git_status_cannot_prove_clean(mode, monkeypatch, tmp_path, capsys):
    """Cannot prove clean => treat as dirty. The alternative is discarding work
    because a subprocess failed."""
    mod = _load("ask-destructive-restore-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    if mode == "raises":
        monkeypatch.setattr(mod.subprocess, "run", _oserror)
    else:
        monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(returncode=128))
    with pytest.raises(SystemExit):
        _run(mod, _bash("git checkout -- README.md"), monkeypatch)
    assert _ask_payload(capsys)["permissionDecision"] == "ask"


def test_restore_guard_drops_flags_from_the_target_list(monkeypatch, tmp_path):
    """Flags are not paths; treating them as targets would report nonsense."""
    mod = _load("ask-destructive-restore-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    assert mod._targets("git restore --staged --worktree src/a.py src/b.py") == [
        "src/a.py",
        "src/b.py",
    ]
    assert mod._targets("git checkout -- . && echo done") == ["."]


@pytest.mark.parametrize(
    "command",
    [
        "git -C . checkout -- README.md",  # the value-taking global opt that slipped past
        "git -c core.pager=cat restore README.md",
        "git --work-tree . checkout -- README.md",
        "git --namespace ns restore README.md",
        # Detected by the old regex too, but only by accident: `\\bgit\\b` matched the
        # `git` inside `.git`, at offset 15. Kept as a spelling that must work, not
        # as evidence the fix works — the params above carry that.
        "git --git-dir .git checkout -- README.md",
        "FOO=1 git checkout -- README.md",
        "echo hi && git restore README.md",  # not the first stage
        "/usr/bin/git checkout -- README.md",  # path-qualified git
    ],
)
def test_restore_guard_finds_the_verb_past_global_options(command, monkeypatch, tmp_path, capsys):
    """Regression: `\\bgit\\b(?:\\s+-\\S+)*` cannot step over `-C .` — the `.` is not
    `-\\S+`, so the loop stops and the alternation never reaches `checkout`. The
    guard missed exactly the spellings its sibling guards already tokenise for."""
    mod = _restore_mod(monkeypatch, tmp_path, ["README.md"])
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 0
    assert _ask_payload(capsys)["permissionDecision"] == "ask"


def test_restore_guard_stays_silent_when_only_another_file_is_dirty(monkeypatch, tmp_path, capsys):
    """Pathspec filtering moved out of git's argv and into the hook, so this is the
    case that proves the hook's own matching narrows to the target."""
    mod = _restore_mod(monkeypatch, tmp_path, ["src/other.py"])
    _run(mod, _bash("git checkout -- README.md"), monkeypatch)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("target", ["src", "src/", "./src"])
def test_restore_guard_matches_files_under_a_directory_target(
    target, monkeypatch, tmp_path, capsys
):
    """A directory target discards every dirty file beneath it, not just an exact match."""
    mod = _restore_mod(monkeypatch, tmp_path, ["src/a.py"])
    with pytest.raises(SystemExit):
        _run(mod, _bash(f"git checkout -- {target}"), monkeypatch)
    assert "src/a.py" in _ask_payload(capsys)["permissionDecisionReason"]


@pytest.mark.parametrize(
    "command",
    [
        "cd src && git checkout -- a.py",
        "cd src; git restore a.py",
        "pushd src && git checkout -- a.py && popd",
    ],
)
def test_restore_guard_asks_when_a_stage_changes_directory(command, monkeypatch, tmp_path, capsys):
    """CodeRabbit on #97: targets are shell-relative, `git status` entries are
    repo-relative. `cd src && git checkout -- a.py` compared `a.py` against
    `src/a.py`, matched nothing, and the guard stayed SILENT while the restore
    discarded the file — fail-open in a guard whose only job is to speak up.

    Path matching cannot be trusted once the shell moves, so the filter is
    skipped rather than trusted.
    """
    mod = _restore_mod(monkeypatch, tmp_path, ["src/a.py"])
    with pytest.raises(SystemExit) as exc:
        _run(mod, _bash(command), monkeypatch)
    assert exc.value.code == 0
    assert "src/a.py" in _ask_payload(capsys)["permissionDecisionReason"]


def test_restore_guard_reads_renamed_and_quoted_paths(monkeypatch, tmp_path, capsys):
    """`--porcelain` quotes odd paths and renders a rename as `old -> new`, both of
    which the `line[3:]` slice turned into a path matching nothing. `-z` emits
    NUL-terminated records with no quoting, the rename source as its own record."""
    mod = _load("ask-destructive-restore-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    # R record: new path in the record, old path follows and must not be read as one.
    stdout = "R  src/new name.py\0src/old.py\0 M src/tab\there.py\0"
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(stdout=stdout))
    assert mod._tracked_dirty() == ["src/new name.py", "src/tab\there.py"]

    with pytest.raises(SystemExit):
        _run(mod, _bash("git checkout -- src"), monkeypatch)
    assert "src/new name.py" in _ask_payload(capsys)["permissionDecisionReason"]


def test_restore_guard_resolves_absolute_targets_against_the_repo(monkeypatch, tmp_path):
    """An absolute target is repo-relative before comparison; one outside the repo
    can never match a `git status` entry."""
    mod = _load("ask-destructive-restore-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    assert mod._covers(str(tmp_path / "src"), "src/a.py")
    assert not mod._covers("/etc/passwd", "src/a.py")


def test_restore_guard_runs_as_a_script_and_fails_closed(monkeypatch, capsys, tmp_path):
    """The __main__ path must ask rather than allow when it cannot judge."""
    import subprocess as _subprocess

    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setenv("REPO_ROOT", str(_script_repo(tmp_path)))
    monkeypatch.setattr(_subprocess, "run", lambda *_a, **_k: _Result(stdout=" M tracked.py\0"))
    monkeypatch.setattr(sys, "stdin", io.StringIO(_bash("git checkout -- tracked.py")))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "ask-destructive-restore-hook.py"), run_name="__main__")
    assert exc.value.code == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["permissionDecision"] == "ask"

    monkeypatch.setattr(sys, "stdin", _Exploding())
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(HOOKS_DIR / "ask-destructive-restore-hook.py"), run_name="__main__")
    assert exc.value.code == 0
    payload = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert payload["permissionDecision"] == "ask"
    assert "failed internally" in payload["permissionDecisionReason"]


# ── validate-evals-hook: scoping and the two subprocess outcomes ──────────────


def _evals_hook_repo(tmp_path: Path) -> Path:
    """A REPO_ROOT holding the validator, so main() reaches its subprocess call."""
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts" / "validate-evals.py").write_text("", encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize(
    ("rel", "why"),
    [
        ("skills/foo/evals/evals.json", "the shape the hook owns"),
        ("skills/foo/evals/trigger-queries.json", "the other eval file"),
    ],
)
def test_is_eval_file_accepts_an_eval_set(rel, why, tmp_path):
    mod = _load("validate-evals-hook")
    assert mod.is_eval_file(tmp_path / rel, tmp_path), why


@pytest.mark.parametrize(
    ("rel", "why"),
    [
        ("skills/foo/evals/notes.md", "not .json"),
        ("skills/foo/SKILL.md", "not under evals/"),
        ("skills/foo/commands/audit.json", "parent is not evals/"),
        ("skills/foo/evals/files/fixture.json", "an eval input, one level too deep"),
        ("docs/audit/findings/a.json", "outside skills/"),
    ],
)
def test_is_eval_file_rejects_everything_else(rel, why, tmp_path):
    """Scoping is the whole guard: a false positive hands the validator a file it
    has no opinion on, and reports its complaint as an eval-set defect."""
    mod = _load("validate-evals-hook")
    assert not mod.is_eval_file(tmp_path / rel, tmp_path), why


def test_validate_evals_hook_surfaces_validator_failure(monkeypatch, tmp_path, capsys):
    """Exit 2 + stderr is the only channel a PostToolUse hook has back to the agent."""
    mod = _load("validate-evals-hook")
    repo = _evals_hook_repo(tmp_path)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    monkeypatch.setattr(
        mod.subprocess, "run", lambda *_a, **_k: _Result(returncode=1, stdout="EVAL SET BROKEN")
    )
    target = repo / "skills" / "foo" / "evals" / "evals.json"
    payload = {"tool_input": {"file_path": str(target)}}
    with pytest.raises(SystemExit) as exc:
        _run(mod, json.dumps(payload), monkeypatch)
    assert exc.value.code == 2
    assert "EVAL SET BROKEN" in capsys.readouterr().err


def test_validate_evals_hook_silent_when_the_validator_passes(monkeypatch, tmp_path, capsys):
    """A clean eval set produces no output — the hook must not narrate success."""
    mod = _load("validate-evals-hook")
    repo = _evals_hook_repo(tmp_path)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(returncode=0, stdout="OK"))
    target = repo / "skills" / "foo" / "evals" / "evals.json"
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_evals_hook_passes_the_skill_dir_not_the_json(monkeypatch, tmp_path):
    """validate-evals.py takes a skill directory. Handing it the JSON file would
    find no evals/ under it and — since the fail-open fix — exit 1 on a clean set,
    so the hook would report every passing eval file as broken."""
    mod = _load("validate-evals-hook")
    repo = _evals_hook_repo(tmp_path)
    monkeypatch.setattr(mod, "REPO_ROOT", repo)
    seen = []

    def _capture(argv, *_a, **_k):
        """Record the argv the hook builds, then report success."""
        seen.append(argv)
        return _Result(returncode=0, stdout="")

    monkeypatch.setattr(mod.subprocess, "run", _capture)
    target = repo / "skills" / "foo" / "evals" / "evals.json"
    _run(mod, json.dumps({"tool_input": {"file_path": str(target)}}), monkeypatch)
    assert seen, "the hook never shelled out"
    assert seen[0][-1] == str(repo / "skills" / "foo")
