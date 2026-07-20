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


def _settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


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
