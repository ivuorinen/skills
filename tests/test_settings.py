"""Tests for the hook registry in .claude/settings.json.

test_hooks.py exercises the hook SCRIPTS; nothing guarded the registry that
decides whether they run at all. pre-commit's check-json accepts `{"hooks": {}}`
as valid, so a deleted registration was previously invisible.
"""

import json
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
    "Read(./.claude/agents/**)",
    "Edit(./.claude/agents/**)",
    "Write(./.claude/agents/**)",
    "Edit(./scripts/hooks/**)",
    "Write(./scripts/hooks/**)",
    "Edit(./.claude/settings.json)",
    "Write(./.claude/settings.json)",
]

# Every path the deny list exists to protect, and the tools it names for each.
# The agents tree adds Read because its contents are what must not be seen, not
# merely what must not change.
PROTECTED_PATHS = {
    "./.claude/agents/**": {"Read", "Edit", "Write"},
    "./scripts/hooks/**": {"Edit", "Write"},
    "./.claude/settings.json": {"Edit", "Write"},
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
    """The three trees an agent must not rewrite: its own agents, the hook
    scripts, and the settings file wiring them. A new one added to the config
    without a line here would pass unnoticed."""
    denied_paths = {r[r.index("(") + 1 : r.rindex(")")] for r in _deny()}
    assert denied_paths == set(PROTECTED_PATHS)


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
    assert "post-bash-revalidate.py" in _commands("PostToolUse", "Bash")


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
    assert undocumented == [], (
        f"PreToolUse hooks configured but not named in CLAUDE.md: {sorted(set(undocumented))}"
    )
