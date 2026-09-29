#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""SessionStart + PostToolUse hook — report a change to the enforcement surface.

Every guard for `scripts/hooks/**`, `.claude/settings.json`,
`.claude/settings.local.json` and the graphify pin is a PreToolUse text parser,
and each spelling it does not know rewrites the surface with no signal at all:
the ledger holds six fixed bypasses of that class, and one audit found six more
— a redirect, a `~` path, a verb, `patch`, an alias, `eval`
(agent-hooks-c8ad2907). `settings.local.json` never reaches a pull request,
so nothing downstream would see a change there either.

This hook does not parse commands. At SessionStart it records a SHA-256 of
every file on the surface; after each shell or Write/Edit call it hashes them
again, and any difference — a file changed, added or removed — exits 2 with
`enforcement surface changed: <paths>`, which Claude Code hands to the agent.
Whatever the spelling of the write, the change itself is seen.

The baseline is kept per session outside the checkout, and is re-taken only
on a fresh start or `/clear`: a resume or a compaction keeps it, so a change
cannot be laundered into the baseline by compacting. A PostToolUse call with
no baseline (the hook was added mid-session) takes one and reports nothing.
It keeps reporting on every call until the session is restarted, since a
change here is the owner's to review.

Ceiling: it detects after the fact, not before — the call that made the change
has already run, and a change reverted within one call is not seen. The
baseline file sits in the temp directory, where a write can reach it too.
Bytecode caches under `__pycache__` are not hashed: Python rewrites them on
every import.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event, repo_root

REPO_ROOT = repo_root()
# The paths the protected-write guard (deny-agents-path-hook.py) and the
# permissions deny list protect: its `PROTECTED_WRITE`.
SURFACE = (
    "scripts/hooks",
    ".claude/settings.json",
    ".claude/settings.local.json",
    ".claude/skills/graphify/.graphify_version",
)
STATE_DIR = Path(tempfile.gettempdir()) / "nitpicker-enforcement-surface"
# SessionStart sources that begin a new baseline; `resume` and `compact` keep
# the one the session already has.
_FRESH_SOURCES = frozenset({"startup", "clear"})


def _digest(path: Path) -> str:
    """SHA-256 of a file's bytes, or a marker when it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        return f"unreadable: {exc.strerror}"


def snapshot(root: Path) -> dict[str, str]:
    """Every file on the surface under `root`, repo-relative, to its digest."""
    found: dict[str, str] = {}
    for rel in SURFACE:
        path = root / rel
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        for file in files:
            if file.is_file() and "__pycache__" not in file.parts:
                found[file.relative_to(root).as_posix()] = _digest(file)
    return found


def changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Each path that differs, tagged `changed`, `added` or `removed`, sorted."""
    tagged = [f"{p} (removed)" for p in before if p not in after]
    tagged += [f"{p} (added)" for p in after if p not in before]
    tagged += [f"{p} (changed)" for p in before if p in after and before[p] != after[p]]
    return sorted(tagged)


def _state_file(event: dict) -> Path:
    """Where this session's baseline for this checkout is kept."""
    key = f"{REPO_ROOT.resolve()}\0{event.get('session_id') or 'no-session'}"
    return STATE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.json"


def _save(state: Path, digests: dict[str, str]) -> None:
    """Write the baseline, owner-readable only."""
    state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    state.write_text(json.dumps(digests, sort_keys=True), encoding="utf-8")
    state.chmod(0o600)


def _load(state: Path) -> dict[str, str] | None:
    """The saved baseline, or None when there is none or it cannot be parsed."""
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def main() -> None:
    """Take the baseline at SessionStart; compare against it after a tool call."""
    event = load_event() or {}
    state = _state_file(event)
    current = snapshot(REPO_ROOT)
    if event.get("hook_event_name") == "SessionStart":
        if event.get("source") in _FRESH_SOURCES or _load(state) is None:
            _save(state, current)
        return
    baseline = _load(state)
    if baseline is None:
        _save(state, current)
        return
    changed = changes(baseline, current)
    if changed:
        print(
            f"  enforcement surface changed: {', '.join(changed)}\n"
            "          A hook, a settings file or the graphify pin differs from the\n"
            "          session's baseline. Changing them is the owner's call: stop,\n"
            "          say what changed and how, and ask the owner.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # a detective control that dies must say so, not pass
        print(
            f"  enforcement surface integrity check failed internally: {exc}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(2)
