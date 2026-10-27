"""Tests for the hook registry in .claude/settings.json.

test_hooks.py exercises the hook SCRIPTS; nothing guarded the registry that
decides whether they run at all. pre-commit's check-json accepts `{"hooks": {}}`
as valid, so a deleted registration was previously invisible.
"""

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
SETTINGS = REPO_ROOT / ".claude" / "settings.json"
HOOKS_DIR = REPO_ROOT / ".mise" / "tasks" / "hook"
HOOK_REL = ".mise/tasks/hook"
# Every registered Python hook runs by path through uv, from the project
# directory, and never through mise: no mise config — project or user, any
# `[env]`, `[tools]`, `[tasks]` override, version file or `.miserc.toml` — is
# read on the way to a hook. Running them through mise either let the
# agent-writable project config in, or (from `/`) dropped the uv a contributor
# installed with `mise install` and every guard denied every call.
HOOK_PREFIX = f'uv run --quiet "$CLAUDE_PROJECT_DIR/{HOOK_REL}/'
# graphify-guard is a bash task; it runs under bash directly, from the project
# directory, where `graphify hook-guard` looks for graphify-out/.
GRAPHIFY_GUARD = f'bash "$CLAUDE_PROJECT_DIR/{HOOK_REL}/graphify-guard"'
_IN_CI = os.environ.get("CI", "").lower() in ("1", "true", "yes")

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
    "Edit(./.mise/tasks/hook/**)",
    "Write(./.mise/tasks/hook/**)",
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
    "./.mise/tasks/hook/**": {"Edit", "Write"},
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
    guards = [c for c in _registered_commands() if f'{HOOK_REL}/graphify-guard"' in c]
    assert sorted(c.rsplit('"', 1)[1].strip() for c in guards) == ["read", "search"]
    assert "ask the owner" in (HOOKS_DIR / "graphify-guard").read_text(encoding="utf-8")


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


INTEGRITY = "enforcement-surface-integrity.py"


@pytest.mark.parametrize("tool", [*SHELL_TOOLS, "Write", "Edit"])
def test_surface_integrity_check_follows_every_tool_that_can_write(tool):
    """The detective control for the enforcement surface (agent-hooks-c8ad2907)
    runs after every call that can change a file: each shell tool, and the file
    tools the deny list already binds."""
    matchers = _matchers_for("PostToolUse", INTEGRITY)
    assert any(re.fullmatch(m, tool) for m in matchers), f"{INTEGRITY} never sees {tool}"


def test_surface_integrity_baseline_is_taken_at_session_start():
    """Without a SessionStart baseline, a change made before the first tool call
    would become the baseline."""
    assert INTEGRITY in _commands("SessionStart")


def _integrity_commands() -> list[str]:
    """Every registered command that runs the integrity check."""
    return [
        cmd
        for entries in _settings()["hooks"].values()
        for entry in entries
        for h in entry.get("hooks", [])
        if INTEGRITY in (cmd := h.get("command", ""))
    ]


@pytest.mark.parametrize("command", _integrity_commands())
@pytest.mark.parametrize(("hook_exit", "expected"), [(None, 2), (1, 2), (0, 0), (2, 2)])
def test_surface_integrity_check_that_cannot_run_says_so(command, hook_exit, expected, tmp_path):
    """Exit 2 is the only PostToolUse exit whose stderr reaches the agent, so a
    check that cannot start — `uv` missing (None), or dying with exit 1 —
    reports as 2 rather than passing in silence."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if hook_exit is not None:
        fake_uv = bin_dir / "uv"
        fake_uv.write_text(f"#!/bin/sh\nexit {hook_exit}\n", encoding="utf-8")
        fake_uv.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", "-c", command],
        input="{}",
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": str(bin_dir), "CLAUDE_PROJECT_DIR": str(REPO_ROOT)},
    )
    assert result.returncode == expected, result.stderr
    assert hook_exit in (0, 2) or result.stderr


def test_stop_reminder_registered():
    assert "stop-reminder.py" in _commands("Stop")


def test_command_closure_reminder_registered():
    assert "command-closure-reminder.py" in _commands("Stop")


@pytest.mark.parametrize("matcher", ["Bash", "Read|Glob"])
def test_pretooluse_hooks_registered(matcher):
    """The two graphify hook-guards can block a tool call — removal must not be silent.

    Asserts the matcher and the guard invocation, not the full command string:
    the wrapper around it (existence guards, flags) is allowed to change.
    """
    assert f'{HOOK_REL}/graphify-guard"' in _commands("PreToolUse", matcher)
    task = (HOOKS_DIR / "graphify-guard").read_text(encoding="utf-8")
    assert 'exec graphify hook-guard "$mode"' in task


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


HOOK_INVENTORY = ".claude/rules/hook-inventory.md"


def test_claude_md_points_at_the_hook_inventory():
    """The inventory left CLAUDE.md for a path-scoped rule to keep CLAUDE.md short.

    A path-scoped rule loads only with the files it names, so an agent that never
    touches `.claude/settings.json` reaches the inventory through CLAUDE.md's
    pointer alone. Drop the pointer and the inventory stops being discoverable
    from the file every turn loads, while the check below still passes.
    """
    assert HOOK_INVENTORY in (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert (REPO_ROOT / HOOK_INVENTORY).is_file()


def test_every_pretooluse_hook_is_documented_in_the_hook_inventory():
    """A blocking hook nobody wrote down is one an agent can only find by tripping it.

    The hook inventory (`.claude/rules/hook-inventory.md`, pointed at from
    CLAUDE.md) is the only description of this surface an
    agent gets. CLAUDE.md said "three PreToolUse hooks" while six were configured, and
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
    documented = (REPO_ROOT / HOOK_INVENTORY).read_text(encoding="utf-8")
    undocumented = []
    for entry in _settings()["hooks"]["PreToolUse"]:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if "$CLAUDE_PROJECT_DIR/" not in cmd:  # pragma: no cover - not a repo hook
                pytest.fail(f"cannot name this PreToolUse hook for the docs check: {cmd!r}")
            name = Path(cmd.split("$CLAUDE_PROJECT_DIR/")[1].split('"')[0]).name
            if name == "graphify-guard":
                # The mode, not the bare task. Both graphify guards run the one
                # task, so collapsing them to it let the inventory drop either
                # bullet and still pass on the strength of the other.
                name = f"graphify-guard {cmd.rsplit(chr(34), 1)[1].split()[0]}"
            if name not in documented:
                undocumented.append(name)
    missing = sorted(set(undocumented) - PENDING_CLAUDE_MD)
    assert missing == [], (
        f"PreToolUse hooks configured but not named in {HOOK_INVENTORY}: {missing}"
    )
    expired = sorted(PENDING_CLAUDE_MD - set(undocumented))
    assert expired == [], (
        f"now named in {HOOK_INVENTORY} (or unregistered); drop from PENDING: {expired}"
    )


# PreToolUse hooks whose inventory bullet is delivered separately from the patch
# that adds them: the enforcement surface ships as owner-applied patches, and
# the inventory is edited in another change. The second assertion above fails the
# moment the inventory names an entry, so this list empties itself rather than
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
    """(script name, registered command) for every PreToolUse guard this repo ships.

    The Python guards only: graphify-guard hands the decision to an external
    binary and keeps the exits it returns, so it has no exit mapping or deadline
    of its own to pin here.
    """
    return [
        (name, cmd)
        for entry in _settings()["hooks"]["PreToolUse"]
        for h in entry.get("hooks", [])
        if f"$CLAUDE_PROJECT_DIR/{HOOK_REL}/" in (cmd := h.get("command", ""))
        and (name := Path(cmd.split("$CLAUDE_PROJECT_DIR/")[1].split('"')[0]).name).endswith(".py")
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


def _guard_deadline_seconds() -> float:
    """`_hooklib.GUARD_DEADLINE_SECONDS`, read without importing the hooks package."""
    text = (HOOKS_DIR / "_hooklib.py").read_text(encoding="utf-8")
    match = re.search(r"^GUARD_DEADLINE_SECONDS = (\d+(?:\.\d+)?)$", text, re.M)
    assert match, "_hooklib.py no longer defines GUARD_DEADLINE_SECONDS"
    return float(match.group(1))


def test_every_pretooluse_hook_sets_an_explicit_timeout():
    """agent-loopholes-793d7db7: Claude Code cancels a hook at its timeout and a
    timed-out command hook does not block the call. Every PreToolUse hook names
    its timeout, so the bound is a reviewed value rather than the default."""
    for entry in _settings()["hooks"]["PreToolUse"]:
        for hook in entry.get("hooks", []):
            timeout = hook.get("timeout")
            assert isinstance(timeout, int) and timeout > 0, hook.get("command", "")[:80]


@pytest.mark.parametrize(("name", "command"), _repo_guard_commands())
def test_every_repo_guard_denies_before_its_hook_timeout(name, command):
    """The guard's own deadline exits 2 before Claude Code's timeout can cancel it
    into an allow, with margin left for `uv` to start the interpreter."""
    timeout = next(
        h["timeout"]
        for entry in _settings()["hooks"]["PreToolUse"]
        for h in entry.get("hooks", [])
        if h.get("command") == command
    )
    assert _guard_deadline_seconds() * 1.5 <= timeout, name
    source = (HOOKS_DIR / name).read_text(encoding="utf-8")
    main_block = source.split('if __name__ == "__main__":', 1)[-1]
    assert "with guard_deadline(" in main_block, f"{name} runs without a deadline"


def _hook_entries() -> list[tuple[str, str]]:
    """(event, command) for every registered command that runs a repo hook."""
    return [
        (event, cmd)
        for event, entries in _settings()["hooks"].items()
        for entry in entries
        for h in entry.get("hooks", [])
        if "$CLAUDE_PROJECT_DIR/" in (cmd := h.get("command", ""))
    ]


@pytest.mark.parametrize(("event", "command"), _hook_entries())
def test_every_hook_runs_by_path_without_mise(event, command):
    """A hook runs by path through uv (or bash), and no command invokes mise.

    Through mise, a project `[tasks]` entry can replace a hook and a project
    `[env]` (CLAUDE_PROJECT_DIR included), `[tools]`, version file or
    `.miserc.toml` env reaches it — every one of those files agent-writable.
    """
    assert HOOK_PREFIX in command or GRAPHIFY_GUARD in command, f"{event}: {command}"
    assert not re.search(r"(^|[\s;&|(])mise\s", command), f"{event}: {command}"
    assert "scripts/hooks" not in command


def _assign(path: Path, name: str) -> tuple[str, ...]:
    """The tuple literal a module assigns to `name` at top level."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, tuple), f"{path.name}: {name} is not a tuple literal"
            return value
    raise AssertionError(f"{path.name} assigns no {name}")


def test_the_hook_dir_is_on_every_protection_list():
    """The protection moves with the files, in every list that holds it.

    Each list guards a different write path — the shell guard, the integrity
    check, the file-tool deny, review — so one left on the old path leaves that
    path open on the new directory.
    """
    protected = _assign(HOOKS_DIR / "deny-agents-path-hook.py", "PROTECTED_WRITE")
    surface = _assign(HOOKS_DIR / "enforcement-surface-integrity.py", "SURFACE")
    codeowners = (REPO_ROOT / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    inventory = (REPO_ROOT / ".claude" / "rules" / "hook-inventory.md").read_text(encoding="utf-8")
    assert HOOK_REL in protected
    assert HOOK_REL in surface
    assert {f"Edit(./{HOOK_REL}/**)", f"Write(./{HOOK_REL}/**)"} <= set(_deny())
    assert re.search(rf"^/{re.escape(HOOK_REL)}/\s+@ivuorinen$", codeowners, re.M)
    assert f"`{HOOK_REL}/`" in inventory
    for name, entries in (("PROTECTED_WRITE", protected), ("SURFACE", surface)):
        assert "scripts/hooks" not in entries, name
    assert not any("scripts/hooks" in rule for rule in _deny())
    assert "scripts/hooks" not in codeowners


def test_every_hook_file_is_a_described_task():
    """mise lists only executable files, and `mise tasks` shows the description.

    `_hooklib.py` is a library the hooks import, not a task, so it stays
    non-executable and mise skips it.
    """
    hooks = sorted(HOOKS_DIR.glob("*.py"))
    assert hooks
    for path in hooks:
        if path.name in NOT_A_HOOK:
            assert not os.access(path, os.X_OK), path.name
            continue
        assert os.access(path, os.X_OK), path.name
        text = path.read_text(encoding="utf-8")
        assert re.search(r'^# \[MISE\] description="[^"]+"$', text, re.M), path.name


def test_every_hook_task_is_hidden_from_mise_tasks():
    """Claude Code runs the hooks, so `mise tasks` lists only what a person runs.

    `mise tasks --hidden` still lists them, and `mise run hook:<name>` still works.
    """
    tasks = sorted(p for p in HOOKS_DIR.iterdir() if p.is_file() and os.access(p, os.X_OK))
    assert len(tasks) > 1
    for path in tasks:
        text = path.read_text(encoding="utf-8")
        assert re.search(r"^#( \[MISE\]|MISE) hide=true$", text, re.M), path.name


@pytest.mark.parametrize(
    ("event", "command"), [(e, c) for e, c in _hook_entries() if GRAPHIFY_GUARD not in c]
)
def test_every_hook_command_fails_closed_without_uv(event, command, tmp_path):
    """With uv absent, a guard denies and every other hook says what did not run.

    PATH is an empty directory, so only the shell builtins (`command -v`, `echo`)
    resolve. PreToolUse and the integrity check exit 2, the only exit that blocks
    or reaches the agent. PostToolUse and Stop hooks exit 1: a non-blocking error
    shown to the user, the way a missing validator already reports, because exit 2
    from a Stop hook would keep the session from stopping. graphify-guard needs
    no uv; with graphify absent it is a no-op by design (hook-inventory.md).
    """
    bash = shutil.which("bash")
    assert bash
    result = subprocess.run(
        [bash, "-c", command],
        input="{}",
        capture_output=True,
        text=True,
        timeout=30,
        env={"PATH": str(tmp_path), "CLAUDE_PROJECT_DIR": str(REPO_ROOT)},
    )
    guard = event in ("PreToolUse", "SessionStart") or INTEGRITY in command
    assert result.returncode == (2 if guard else 1), f"{event}: {result.stderr}"
    assert "uv missing" in result.stderr


def _hook_prefix_command(task: str) -> str:
    """The registered prefix, aimed at `task` in the hook directory."""
    return f'{HOOK_PREFIX}{task}"'


@pytest.mark.skipif(
    shutil.which("mise") is None and not _IN_CI,
    reason="mise is not installed; under CI a missing mise fails instead",
)
def test_project_mise_config_does_not_reach_a_hook(tmp_path):
    """Planted project config — `[env]`, an env chosen by `.miserc.toml` — stays out.

    The control run, through mise with the project trusted, shows the planted
    values are live, so the hook run's clean output comes from the registered
    form and not from a fixture mise never read. The probe looks like a real
    hook: a uv shebang, a `[MISE]` header and the `{{` an f-string brace escape
    leaves, which made an earlier mise-based form refuse every hook.
    """
    hook_dir = tmp_path / ".mise" / "tasks" / "hook"
    hook_dir.mkdir(parents=True)
    probe = hook_dir / "probe.py"
    probe.write_text(
        "#!/usr/bin/env -S uv run --quiet\n"
        '# [MISE] description="probe"\n'
        "# /// script\n"
        '# requires-python = ">=3.11"\n'
        "# ///\n"
        "import os\n\n"
        "print(f\"probe={os.environ.get('PROBE', '')} env={os.environ.get('PROBE_ENV', '')}\")"
        '  # f"{operand}^{{commit}}"\n',
        encoding="utf-8",
    )
    probe.chmod(0o755)
    (tmp_path / "mise.local.toml").write_text('[env]\nPROBE = "leak"\n', encoding="utf-8")
    (tmp_path / ".miserc.toml").write_text('env = ["dev"]\n', encoding="utf-8")
    (tmp_path / "mise.dev.toml").write_text('[env]\nPROBE_ENV = "dev"\n', encoding="utf-8")
    # Under CI `uv` is a mise shim, which needs a version from the cwd's config,
    # and tmp_path has none. Resolve the real binary from the checkout and link
    # it from a directory mise does not manage: `mise run` drops its own install
    # directories from PATH, so prepending the one `mise which` names is undone.
    which = subprocess.run(
        ["mise", "which", "uv"], cwd=REPO_ROOT, capture_output=True, text=True, timeout=60
    )
    uv_path = which.stdout.strip() if which.returncode == 0 else shutil.which("uv")
    assert uv_path, "no uv binary to run the probe with"
    uv_dir = tmp_path / "bin"
    uv_dir.mkdir()
    (uv_dir / "uv").symlink_to(uv_path)
    env = {
        **os.environ,
        "PATH": f"{uv_dir}{os.pathsep}{os.environ['PATH']}",
        "CLAUDE_PROJECT_DIR": str(tmp_path),
    }
    for var in ("MISE_ENV", "MISE_TRUSTED_CONFIG_PATHS", "MISE_IGNORED_CONFIG_PATHS"):
        env.pop(var, None)

    def run(command: str, extra: dict[str, str]) -> str:
        result = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=tmp_path,
            env={**env, **extra},
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    control = run(f'mise run -q "{probe}"', {"MISE_TRUSTED_CONFIG_PATHS": str(tmp_path)})
    assert "probe=leak" in control
    assert "env=dev" in control
    assert run(_hook_prefix_command("probe.py"), {}).strip() == "probe= env="


_BASH_GUARDS = [
    (name, cmd)
    for name, cmd in _repo_guard_commands()
    if name
    in (
        "deny-agents-path-hook.py",
        "deny-unsafe-git-hook.py",
        "guard-ctx-ok-hook.py",
        "ask-destructive-restore-hook.py",
    )
]


@pytest.mark.parametrize(("name", "command"), _BASH_GUARDS)
def test_every_bash_guard_command_runs_its_real_hook(name, command):
    """The registered command, real uv and real hook, allows a harmless call.

    The exit-mapping tests stand a fake `uv` in for the hook, so a command that
    could not start the real hook — every guard denying every call, which an
    earlier mise-based form did — passed all of them. This runs the command.
    """
    event = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    result = subprocess.run(
        ["bash", "-c", command],
        input=event,
        capture_output=True,
        text=True,
        timeout=120,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT)},
    )
    assert result.returncode == 0, f"{name}: {result.stderr}"


def test_graphify_guard_rejects_an_unknown_mode():
    """A mode other than `search` or `read` denies rather than reaching graphify."""
    result = subprocess.run(
        ["bash", str(HOOKS_DIR / "graphify-guard"), "bogus"],
        input="{}",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=REPO_ROOT,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(REPO_ROOT)},
    )
    assert result.returncode == 2
    assert "mode must be search or read" in result.stderr


@pytest.mark.parametrize("mode", ["search", "read"])
def test_graphify_guard_runs_hook_guard_from_the_project(mode, tmp_path):
    """`graphify hook-guard` reads graphify-out/ relative to its cwd, so it runs there.

    Started from anywhere else it found no graph and exited 0 in silence: the
    guard was a no-op while looking like it ran. A stand-in `graphify` records
    where it ran and with which mode; the pin matches it.
    """
    project, bin_dir = tmp_path / "project", tmp_path / "bin"
    (project / ".claude" / "skills" / "graphify").mkdir(parents=True)
    (project / ".claude" / "skills" / "graphify" / ".graphify_version").write_text(
        "9.9.9\n", encoding="utf-8"
    )
    bin_dir.mkdir()
    fake = bin_dir / "graphify"
    fake.write_text(
        '#!/bin/sh\n[ "$1" = --version ] && { echo "graphify 9.9.9"; exit 0; }\n'
        'echo "cwd=$PWD args=$*"\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    command = next(c for e, c in _hook_entries() if GRAPHIFY_GUARD in c and c.endswith(mode))
    result = subprocess.run(
        ["bash", "-c", command.replace("$CLAUDE_PROJECT_DIR", str(REPO_ROOT), 1)],
        input="{}",
        capture_output=True,
        text=True,
        timeout=30,
        cwd="/",
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "CLAUDE_PROJECT_DIR": str(project),
        },
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"cwd={project} args=hook-guard {mode}"


@pytest.mark.skipif(
    shutil.which("pyright") is None and not _IN_CI,
    reason="pyright is not on PATH (mise provides it); under CI a missing pyright fails",
)
def test_pyright_checks_every_hook():
    """pyright auto-excludes dot-directories, so the main project never saw a hook.

    The hooks get a project of their own, rooted in their directory, and the
    typecheck task runs it as a second pass.
    """
    result = subprocess.run(
        ["pyright", "-p", str(HOOKS_DIR), "--outputjson"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=REPO_ROOT,
    )
    summary = json.loads(result.stdout)["summary"]
    assert summary["filesAnalyzed"] == len(list(HOOKS_DIR.glob("*.py")))
    task = (REPO_ROOT / ".mise" / "tasks" / "typecheck").read_text(encoding="utf-8")
    assert f"-p {HOOK_REL}" in task
