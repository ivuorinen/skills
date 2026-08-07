"""Tests for the PostToolUse / Stop hooks in scripts/hooks/.

Focus: the protocol contract (failures reach the agent only via exit 2 + stderr)
and the gating branches (empty stdin, non-dict payload, irrelevant paths) that
must be silent no-ops. These hooks had no coverage before.
"""

import importlib.util
import io
import json
import re
import runpy
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

STDIN_HOOKS = [
    "validate-json-hook",
    "validate-skill-hook",
    "check-version-sync-hook",
    "ruff-hook",
    "validate-rules-hook",
]


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
    # common.py path-loads the shipped parser, so the fake repo needs it too.
    shipped = tmp_path / "skills" / "nitpicker" / "scripts"
    shipped.mkdir(parents=True)
    shutil.copy(
        SCRIPTS_DIR.parent / "skills" / "nitpicker" / "scripts" / "findings.py",
        shipped / "findings.py",
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


def test_ruff_hook_missing_binary_is_silent_noop(monkeypatch, tmp_path, capsys):
    """No ruff on PATH: fail open like every sibling, not a FileNotFoundError traceback."""
    mod = _load("ruff-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)

    def _boom(*a, **k):
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
    return _load("_hooklib")


def _fake_checkout(root):
    """A tree repo_root() will accept — it probes for scripts/hooks/_hooklib.py."""
    (root / "scripts" / "hooks").mkdir(parents=True)
    (root / "scripts" / "hooks" / "_hooklib.py").touch()
    return root


def test_repo_root_empty_claude_project_dir_falls_through(monkeypatch, tmp_path):
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
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", "")
    monkeypatch.setenv("REPO_ROOT", "")
    assert _hooklib().repo_root() == HOOKS_DIR.parent.parent


# ── stop-reminder: gate on git porcelain output ───────────────────────────────


def _fake_staged(monkeypatch, mod, staged_paths, worktree_paths=()):
    """Stub the two `git diff --name-only -z` calls (staged, then working tree)."""

    def _run(argv, *a, **k):
        paths = staged_paths if "--cached" in argv else worktree_paths

        class _Result:
            returncode = 0
            stdout = "\0".join([*paths, ""])

        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", _run)


def test_stop_reminder_flags_staged_skill(monkeypatch, capsys):
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
    mod = _load("stop-reminder")
    _fake_staged(monkeypatch, mod, ["skills/nitpicker/commands/audit.md"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2
    assert "skills/nitpicker/commands/audit.md" in capsys.readouterr().err


def test_stop_reminder_silent_when_no_staged_skill(monkeypatch, capsys):
    mod = _load("stop-reminder")
    # Dirty paths that are not skill files must stay quiet in either scope.
    _fake_staged(monkeypatch, mod, ["README.md"], worktree_paths=["README.md"])
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


# ── deny-agents-path-hook: the substring bypasses must now be blocked ──────────


def test_deny_agents_blocks_cd_bypass(monkeypatch):
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": "cd .claude/agents && cat > x.md"}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_blocks_double_slash(monkeypatch):
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": "sed -i s/a/b/ .claude//agents/foo.md"}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_allows_unrelated_command(monkeypatch):
    mod = _load("deny-agents-path-hook")
    command = "ls .claude/rules/"
    _run(mod, json.dumps({"tool_input": {"command": command}}), monkeypatch)  # no SystemExit
    # Pin the verdict, not just the absence of SystemExit: a hook that stopped
    # evaluating the command entirely would also raise nothing.
    assert mod._references_agents(command) is False


def test_deny_agents_blocks_dot_segment(monkeypatch):
    mod = _load("deny-agents-path-hook")
    event = json.dumps({"tool_input": {"command": "cat .claude/./agents/x.md"}})
    with pytest.raises(SystemExit) as exc:
        _run(mod, event, monkeypatch)
    assert exc.value.code == 2


def test_deny_agents_blocks_escaped_slash(monkeypatch):
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


def test_ci_runs_the_repository_gate_through_make_check():
    """The Validate job must invoke `make check`, not restate its targets.

    Replaces the old per-target assertions. Those pinned CI and the Makefile to
    the same shape, but a *new* target added to `make check` was still absent
    from CI until someone noticed — the assertion could only catch drift in
    steps that already existed. Running the Makefile removes the second copy
    instead of guarding it.
    """
    workflow = (ROOT / ".github/workflows/validate-skills.yml").read_text(encoding="utf-8")
    validate_job = workflow.split("  validate:", 1)[1]
    assert re.search(r"^\s*run:\s*make check\s*$", validate_job, re.M), (
        "the Validate job must run `make check`"
    )

    # Exactly one `run:` step, so a gate cannot be re-added alongside it.
    #
    # Matching each `make check` target name against the `run:` lines was the
    # obvious check and is useless: a reintroduced security step runs
    # `bandit ...`, which contains no "security". Counting the steps is the
    # property that actually holds — the job's whole job is to call the Makefile.
    runs = re.findall(r"^\s*run:", validate_job, re.M)
    assert len(runs) == 1, (
        f"the Validate job has {len(runs)} run steps; it should have exactly one "
        "(`make check`) — an extra step is a second copy of a gate"
    )


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
        class _R:
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
        untracked = "--others" in argv
        paths = ["skills/nitpicker/commands/newcmd.md"] if untracked else []

        class _R:
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
        _subprocess, "run", lambda *a, **k: _Result(returncode=1, stdout=marker or "FAILED")
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
    import subprocess as _subprocess

    def _fake_git(cmd, *a, **k):
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


def test_validate_json_non_existent_path_is_a_silent_noop(monkeypatch, tmp_path, capsys):
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
        returncode = 1
        stdout = "checker blew up"
        stderr = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _R())
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
        returncode = 128
        stdout = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _R())
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


def test_deny_agents_survives_a_glob_that_raises(monkeypatch):
    """Path.glob raises on patterns the stdlib will not expand (absolute, bad '**').
    Both the cd-base expansion and the token expansion must swallow it — a crash
    here fails the guard open."""
    mod = _load("deny-agents-path-hook")

    def _raises(*_a, **_k):
        raise OSError("unsupported pattern")

    monkeypatch.setattr(Path, "glob", _raises)
    assert mod._references_agents("cd d*/ && cat a*/x.md") is False


# ── validate-audit-findings-hook: the store's own gate ────────────────────────


def _findings_repo(tmp_path: Path) -> Path:
    shipped = tmp_path / "skills" / "nitpicker" / "scripts"
    shipped.mkdir(parents=True)
    shutil.copy(
        SCRIPTS_DIR.parent / "skills" / "nitpicker" / "scripts" / "findings.py",
        shipped / "findings.py",
    )
    return tmp_path


def test_audit_findings_ignores_a_path_outside_the_store(monkeypatch, tmp_path, capsys):
    mod = _load("validate-audit-findings-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod.subprocess, "run", _never_run("no subprocess for an out-of-store path"))
    other = tmp_path / "README.md"
    other.write_text("hi\n", encoding="utf-8")
    _run(mod, json.dumps({"tool_input": {"file_path": str(other)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def _never_run(msg: str):
    def _boom(*_a, **_k):
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
        returncode = 1
        stdout = ""
        stderr = "index blew up"

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _R())
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
    mod = _load("ruff-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    f = tmp_path / "clean.py"
    f.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/ruff")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result())
    _run(mod, json.dumps({"tool_input": {"file_path": str(f)}}), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_version_sync_hook_silent_when_versions_agree(monkeypatch, tmp_path, capsys):
    mod = _load("check-version-sync-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "check-version-sync.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result(stdout="  OK  all\n"))
    payload = {"tool_input": {"file_path": str(tmp_path / "package.json")}}
    _run(mod, json.dumps(payload), monkeypatch)
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_validate_skill_hook_silent_when_the_skill_is_valid(monkeypatch, tmp_path, capsys):
    mod = _load("validate-skill-hook")
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "validate-skill.py").write_text("", encoding="utf-8")
    skill = tmp_path / "skills" / "foo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: foo\n---\n", encoding="utf-8")
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result(stdout="OK\n"))
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
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _revalidate(monkeypatch, tmp_path, *, status, gate=None, gates_on_disk=True):
    """Load the hook against a tmp REPO_ROOT with subprocess.run faked.

    `status` is the _Result for `git status`; `gate` is called with each gate's
    argv and returns that gate's _Result (default: success).
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
        calls.append(list(cmd))
        if cmd[:2] == ["git", "status"]:
            return status
        return gate(cmd) if gate else _Result()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    return mod, calls


def _gate_calls(calls: list[list[str]]) -> list[list[str]]:
    return [c for c in calls if c[:2] != ["git", "status"]]


def test_revalidate_returns_when_not_a_git_tree(monkeypatch, tmp_path, capsys):
    """A non-zero `git status` means there is nothing to scope against — the hook
    must return, not run every gate against an unknown tree."""
    mod, calls = _revalidate(monkeypatch, tmp_path, status=_Result(returncode=128))
    mod.main()
    assert _gate_calls(calls) == []
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_revalidate_ignores_a_dirty_path_outside_the_governed_set(monkeypatch, tmp_path, capsys):
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
    def _gate(cmd):
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
