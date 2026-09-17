"""Tests for the hook registry in .claude/settings.json.

test_hooks.py exercises the hook SCRIPTS; nothing guarded the registry that
decides whether they run at all. pre-commit's check-json accepts `{"hooks": {}}`
as valid, so a deleted registration was previously invisible.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
HOOKS_DIR = REPO_ROOT / "scripts" / "hooks"

WRITE_EDIT_HOOKS = [
    "validate-skill-hook.py",
    "validate-json-hook.py",
    "check-version-sync-hook.py",
    "ruff-hook.py",
    "validate-audit-findings-hook.py",
    "validate-rules-hook.py",
    "validate-evals-hook.py",
    "count-in-prose-hook.py",
]


# The exact deny list, pinned like VENDORED_SKILLS in test_validate_skill.py.
# Nothing else gated this: the whole `permissions` block could be deleted and the
# suite stayed green, on the one part of the enforcement surface that blocks a
# tool call before it runs. Narrowing or removing an entry must be a deliberate
# edit to this constant, visible in review.
#
# Write is named explicitly for every protected path rather than assumed to ride
# along with Edit. Whether an `Edit(...)` rule also binds the Write tool is
# undocumented, so relying on it would leave the strongest in-session control
# resting on client behaviour no gate here can see. Naming both is redundant if
# Edit does cover Write, and load-bearing if it does not.
EXPECTED_DENY = [
    "Edit(./.claude/agents/**)",
    "Write(./.claude/agents/**)",
    "Edit(./scripts/hooks/**)",
    "Write(./scripts/hooks/**)",
    "Edit(./.claude/settings.json)",
    "Write(./.claude/settings.json)",
    "Edit(./.claude/settings.local.json)",
    "Write(./.claude/settings.local.json)",
    "Edit(./.claude/skills/graphify/.graphify_version)",
    "Write(./.claude/skills/graphify/.graphify_version)",
]

# Every path the deny list exists to protect, and the tools it names for each.
# The agents tree is denied for Edit and Write only: the owner allows reading
# agent definitions so their language can be audited in-session. Changing them
# stays owner-only.
#
# settings.local.json is merged over the project settings and can set
# `disableAllHooks`, so one write there turned off every hook
# (agent-loopholes-bbe241dd). The graphify pin decides which binary the
# Bash/Read/Glob guards trust, so rewriting it re-trusts whatever is installed
# (agent-loopholes-8c3cdf74).
PROTECTED_PATHS = {
    "./.claude/agents/**": {"Edit", "Write"},
    "./scripts/hooks/**": {"Edit", "Write"},
    "./.claude/settings.json": {"Edit", "Write"},
    "./.claude/settings.local.json": {"Edit", "Write"},
    "./.claude/skills/graphify/.graphify_version": {"Edit", "Write"},
}


def _settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def _deny() -> list[str]:
    return _settings().get("permissions", {}).get("deny", [])


def test_deny_list_matches_the_pinned_set():
    assert _deny() == EXPECTED_DENY


def test_every_protected_path_is_denied_for_its_declared_tools():
    """Asserts the property, not just the literal — a reordering stays green,
    a silently dropped path does not."""
    rules = set(_deny())
    for path, tools in PROTECTED_PATHS.items():
        for tool in tools:
            assert f"{tool}({path})" in rules, f"{path} no longer denied for {tool}"


def test_the_enforcement_surface_paths_are_all_represented():
    """The paths an agent must not rewrite: its own agents, the hook scripts, the
    settings files wiring them, and the graphify pin the guards trust. A new one
    added to the config without a line here would pass unnoticed."""
    denied_paths = {r[r.index("(") + 1 : r.rindex(")")] for r in _deny()}
    assert denied_paths == set(PROTECTED_PATHS)


def test_graphify_pin_mismatch_sends_the_agent_to_the_owner():
    """The mismatch message used to name the pin file and nothing else, which
    pointed a blocked agent at the one edit that silently re-trusts any installed
    binary (agent-loopholes-8c3cdf74)."""
    guards = [c for c in _registered_commands() if "graphify hook-guard" in c]
    assert guards, "no graphify hook-guard registered"
    for cmd in guards:
        assert "ask the owner" in cmd, cmd


def _commands(event: str, matcher: str | None = None) -> str:
    """All hook command strings registered for an event, optionally by matcher."""
    entries = _settings()["hooks"].get(event, [])
    return "\n".join(
        h.get("command", "")
        for entry in entries
        if matcher is None or entry.get("matcher") == matcher
        for h in entry.get("hooks", [])
    )


@pytest.mark.parametrize("name", WRITE_EDIT_HOOKS)
def test_write_edit_hook_registered(name):
    assert name in _commands("PostToolUse", "Write|Edit")


def test_bash_revalidate_hook_registered():
    assert _matchers_for("PostToolUse", "post-bash-revalidate.py")


# The tools that execute shell text. `.claude/rules/use-context-mode.md` sends
# shell work to the context-mode tools, and a guard registered for `Bash` alone
# never saw those calls: a failed `cd` inside ctx_execute once let `git add -A`
# stage 61 paths in the real repository (agent-loopholes-41c1b2f3).
SHELL_TOOLS = [
    "Bash",
    "mcp__plugin_context-mode_context-mode__ctx_execute",
    "mcp__plugin_context-mode_context-mode__ctx_execute_file",
    "mcp__plugin_context-mode_context-mode__ctx_batch_execute",
]

# The guards that judge what a shell command does. guard-ctx-ok-hook.py is absent
# on purpose: `# ctx-ok` is the marker for opting OUT of context-mode, so on a
# context-mode call it claims nothing, and judging one would tell the agent to
# route through the tool it is already using.
SHELL_GUARDS = [
    ("PreToolUse", "deny-agents-path-hook.py"),
    ("PreToolUse", "deny-unsafe-git-hook.py"),
    ("PreToolUse", "ask-destructive-restore-hook.py"),
    ("PostToolUse", "post-bash-revalidate.py"),
]


def _matchers_for(event: str, script: str) -> list[str]:
    """Every matcher under which `script` is registered for `event`."""
    return [
        entry.get("matcher", "")
        for entry in _settings()["hooks"].get(event, [])
        if any(script in h.get("command", "") for h in entry.get("hooks", []))
    ]


@pytest.mark.parametrize("tool", SHELL_TOOLS)
@pytest.mark.parametrize(("event", "script"), SHELL_GUARDS)
def test_every_shell_guard_matches_every_shell_tool(event, script, tool):
    """A guard that a shell-running tool never reaches enforces nothing on it."""
    matchers = _matchers_for(event, script)
    assert matchers, f"{script} is not registered for {event}"
    assert any(re.fullmatch(m, tool) for m in matchers), f"{script} never sees {tool}"


@pytest.mark.parametrize(("event", "script"), SHELL_GUARDS)
def test_shell_guard_matchers_do_not_widen_past_shell_tools(event, script):
    """Control: the widened matcher must not start firing on file tools."""
    for tool in ("Read", "Write", "Edit", "mcp__plugin_context-mode_context-mode__ctx_search"):
        assert not any(re.fullmatch(m, tool) for m in _matchers_for(event, script)), tool


def test_stop_reminder_registered():
    assert "stop-reminder.py" in _commands("Stop")


@pytest.mark.parametrize("matcher", ["Bash", "Read|Glob"])
def test_pretooluse_hooks_registered(matcher):
    """The two graphify hook-guards can block a tool call — removal must not be silent.

    Asserts the matcher and the guard invocation, not the full command string:
    the wrapper around it (existence guards, flags) is allowed to change.
    """
    assert "graphify hook-guard" in _commands("PreToolUse", matcher)


def _registered_commands() -> list[str]:
    return [
        h.get("command", "")
        for entries in _settings()["hooks"].values()
        for entry in entries
        for h in entry.get("hooks", [])
    ]


# Library module, imported by the hooks rather than registered as one.
NOT_A_HOOK = {"_hooklib.py"}


def test_every_hook_script_on_disk_is_wired():
    """A hook added to scripts/hooks/ but never registered must fail the suite.

    Globs *.py, not *-hook.py: post-bash-revalidate.py and stop-reminder.py are
    both live hooks that the narrower glob never saw.
    """
    registered = "\n".join(_registered_commands())
    unwired = [
        p.name
        for p in sorted(HOOKS_DIR.glob("*.py"))
        if p.name not in NOT_A_HOOK and p.name not in registered
    ]
    assert unwired == [], f"hook scripts present but not registered: {unwired}"


def test_every_registered_hook_script_exists():
    """The reverse: a registration whose script has been deleted must fail too."""
    for cmd in _registered_commands():
        if "$CLAUDE_PROJECT_DIR/" not in cmd:
            continue
        rel = cmd.split("$CLAUDE_PROJECT_DIR/")[1].split('"')[0]
        assert (REPO_ROOT / rel).exists(), f"registered hook missing: {rel}"


def test_every_pretooluse_hook_is_documented_in_claude_md():
    """A blocking hook nobody wrote down is one an agent can only find by tripping it.

    CLAUDE.md is loaded every turn and is the only description of this surface an
    agent gets. It said "three PreToolUse hooks" while six were configured, and
    the three it omitted — deny-unsafe-git, guard-ctx-ok, ask-destructive-restore
    — all exit 2. An agent planning around the documented three had no basis to
    expect a denial from the other three and no stated recovery.

    Restricted to PreToolUse because only those block: a PostToolUse validator
    that fires unannounced costs a surprising message, not a refused call.

    This is `.claude/rules/counts-in-prose.md` enforced rather than asserted. The
    rule's own note concedes "no gate parses English number words", so the count
    drifted silently; a reference has a referent and can be checked, which is
    what this does.
    """
    documented = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    undocumented = []
    for entry in _settings()["hooks"]["PreToolUse"]:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if "$CLAUDE_PROJECT_DIR/" in cmd:
                name = Path(cmd.split("$CLAUDE_PROJECT_DIR/")[1].split('"')[0]).name
            elif "graphify hook-guard" in cmd:
                # The subcommand, not the bare prefix. Both graphify guards share
                # `graphify hook-guard`, so collapsing them to it let CLAUDE.md
                # drop either bullet and still pass on the strength of the other.
                name = f"graphify hook-guard {cmd.split('graphify hook-guard')[1].split()[0]}"
            else:  # pragma: no cover - a spelling neither branch handles
                pytest.fail(f"cannot name this PreToolUse hook for the docs check: {cmd!r}")
            if name not in documented:
                undocumented.append(name)
    missing = sorted(set(undocumented) - PENDING_CLAUDE_MD)
    assert missing == [], f"PreToolUse hooks configured but not named in CLAUDE.md: {missing}"
    expired = sorted(PENDING_CLAUDE_MD - set(undocumented))
    assert expired == [], f"now named in CLAUDE.md (or unregistered); drop from PENDING: {expired}"


# PreToolUse hooks whose CLAUDE.md bullet is delivered separately from the patch
# that adds them: the enforcement surface ships as owner-applied patches, and
# CLAUDE.md is edited in another change. The second assertion above fails the
# moment CLAUDE.md names an entry, so this list empties itself rather than
# outliving its reason. Adding to it is an owner decision, like the deny list.
PENDING_CLAUDE_MD: frozenset[str] = frozenset()


@pytest.mark.parametrize("tool", SHELL_TOOLS[1:])
def test_unguarded_cd_guard_matches_every_context_mode_shell_tool(tool):
    """The guard exists for context-mode shell code (agent-hooks-da747c0c)."""
    matchers = _matchers_for("PreToolUse", "deny-unguarded-cd-hook.py")
    assert any(re.fullmatch(m, tool) for m in matchers), tool
    assert not any(re.fullmatch(m, "Read") for m in matchers)


_STORE_WRITE_TOOLS = [
    "mcp__nitpicker__np_new_finding",
    "mcp__plugin_ivuorinen-skills_nitpicker__np_resolve_finding",
    "mcp__nitpicker__np_write_index",
    "mcp__plugin_ivuorinen-skills_nitpicker__np_process_sarif",
]


@pytest.mark.parametrize("tool", _STORE_WRITE_TOOLS)
def test_stale_write_guard_matches_every_store_write_tool(tool):
    """Both server spellings: `.mcp.json` registers `nitpicker`, the plugin
    registers the plugin-scoped name (agent-hooks-eaa13a08)."""
    matchers = _matchers_for("PreToolUse", "deny-stale-mcp-write-hook.py")
    assert any(re.fullmatch(m, tool) for m in matchers), tool


def test_stale_write_guard_leaves_read_tools_alone():
    """Control: reading the store never runs stale code into a permanent record."""
    matchers = _matchers_for("PreToolUse", "deny-stale-mcp-write-hook.py")
    assert matchers
    assert not any(re.fullmatch(m, "mcp__nitpicker__np_list_findings") for m in matchers)


def _repo_guard_commands() -> list[tuple[str, str]]:
    """(script name, registered command) for every PreToolUse guard this repo ships."""
    return [
        (Path(cmd.split("$CLAUDE_PROJECT_DIR/")[1].split('"')[0]).name, cmd)
        for entry in _settings()["hooks"]["PreToolUse"]
        for h in entry.get("hooks", [])
        if "$CLAUDE_PROJECT_DIR/scripts/hooks/" in (cmd := h.get("command", ""))
    ]


@pytest.mark.parametrize(("name", "command"), _repo_guard_commands())
@pytest.mark.parametrize(("hook_exit", "expected"), [(1, 2), (0, 0), (2, 2)])
def test_a_guard_that_fails_to_run_blocks_the_call(name, command, hook_exit, expected, tmp_path):
    """Claude Code blocks a PreToolUse call on exit 2 only; any other non-zero exit
    lets it through. An import error, a crash before `main()`'s own handler, or a
    `uv` failure all exit 1, so each guard failed OPEN (agent-loopholes-02f83e02).

    A fake `uv` stands in for the guard, so this pins the registered command's
    own exit handling: a failure becomes 2, while an allow (0) and a deny (2)
    pass through unchanged.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(f"#!/bin/sh\nexit {hook_exit}\n", encoding="utf-8")
    fake_uv.chmod(0o755)
    result = subprocess.run(
        ["sh", "-c", command],
        input="{}",
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(REPO_ROOT)},
    )
    assert result.returncode == expected, f"{name}: {result.stderr}"
