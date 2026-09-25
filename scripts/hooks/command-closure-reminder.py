#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Stop hook — remind when a loaded nitpicker command still has open process steps.

`_conventions.md` § Execution makes every command a task list: seed one task per
numbered step, close each, read the list back before reporting. Skipping steps
recurred as a defect class (agent-hooks-60b3ebb1) and every fix so far was prose.
This hook reads the session transcript and reconstructs, per MCP server, which
`np_read_command` loads were followed by seeded tasks and which of those tasks
are still `pending` or `in_progress`.

A reminder, not a block. A turn ending is not a command ending: a run waits on
the user (the apply-fixes and commit prompts, `cr`'s Step 6 menu) and on
background work (subagents, a review poll) across turns, and a hard block there
would force a continuation on every legitimate wait. The open steps reach the
agent as `additionalContext` (`_hooklib.stop_feedback`) once per stop cycle —
the `stop_hook_active` guard keeps it from re-firing on its own forced
continuation — and the agent either closes them
or says what it is waiting on. It repeats once per turn while steps stay open,
the same shape `stop-reminder.py` has.

Ceiling: it sees only runs that loaded the command through `np_read_command` and
tracked with `np_task_*`, so Copilot, pi, CI and a CLI-fallback run are outside
it — they keep the prose rule and its printed step record. It checks that seeded
steps were closed, never that the work behind them was done: it raises the cost
of skipping from nothing to closing a step that did not run.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import load_event, report_skip, stop_feedback

# Tool names carry the server qualifier: `mcp__nitpicker__np_…` for the
# project-scope server, `mcp__plugin_<plugin>_nitpicker__np_…` for the plugin
# one. The two hold separate task lists whose ids collide, so state is keyed
# by server as well as id.
_TOOL = re.compile(r"^mcp__(?P<server>[A-Za-z0-9_-]*nitpicker)__(?P<tool>np_[a-z_]+)$")
_OPEN = frozenset({"pending", "in_progress"})


def _text(content: Any) -> str:
    """A tool_result's text: a plain string, or the joined text blocks of a list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _json(text: str) -> Any:
    """Parsed JSON, or None — a transcript line or result that is not JSON is skipped."""
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _field(result: Any, key: str) -> Any:
    """`result[key]` when the result is a JSON object, else None."""
    return result.get(key) if isinstance(result, dict) else None


class _Session:
    """Command runs and task statuses, rebuilt from the transcript in order.

    A run is `{server, command, tasks}`; `status` maps (server, task id) to the
    task's last known status. One handler per nitpicker tool that moves either.
    """

    def __init__(self) -> None:
        """Start with no runs and no tasks."""
        self.runs: list[dict] = []
        self.status: dict[tuple[str, str], str] = {}

    def _latest(self, server: str) -> dict | None:
        """The most recent run loaded through `server`, if any."""
        return next((r for r in reversed(self.runs) if r["server"] == server), None)

    def _closed(self, run: dict) -> bool:
        """True when the run seeded steps and none of them is still open."""
        return bool(run["tasks"]) and all(
            self.status.get((run["server"], t)) not in _OPEN for t in run["tasks"]
        )

    def read_command(self, server: str, args: dict, _result: Any) -> None:
        """A command load opens a run."""
        self.runs.append({"server": server, "command": str(args.get("command", "")), "tasks": []})

    def task_create(self, server: str, _args: dict, result: Any) -> None:
        """A created task joins the latest run on its server, unless that run closed.

        Tasks made after a run closed every step it seeded are the agent's own,
        not the command's: firing on a real session reported a finished `cr` as
        open over tasks it never seeded. Ceiling: a run that seeds, closes
        everything, then seeds more goes silent — the lenient direction, and a
        breach of seed-before-start anyway.
        """
        task = _field(result, "task")
        if not isinstance(task, dict) or "id" not in task:
            return
        run = self._latest(server)
        if run is not None and not self._closed(run):
            run["tasks"].append(str(task["id"]))
        self.status[(server, str(task["id"]))] = "pending"

    def task_update(self, server: str, args: dict, _result: Any) -> None:
        """An update moves one task's status; `deleted` removes it."""
        key = (server, str(args.get("task_id", "")))
        new = args.get("status")
        if new == "deleted":
            self.status.pop(key, None)
        elif isinstance(new, str):
            self.status[key] = new

    def task_list(self, server: str, _args: dict, result: Any) -> None:
        """The server's whole list is authoritative: an id it no longer carries was deleted."""
        tasks = _field(result, "tasks")
        if not isinstance(tasks, list):
            return
        listed = {
            str(t["id"]): str(t.get("status", ""))
            for t in tasks
            if isinstance(t, dict) and "id" in t
        }
        for key in [k for k in self.status if k[0] == server]:
            if key[1] in listed:
                self.status[key] = listed[key[1]]
            else:
                del self.status[key]

    def reminders(self) -> list[str]:
        """One line per run with open steps, or loaded with none seeded."""
        out: list[str] = []
        for i, run in enumerate(self.runs):
            if not run["tasks"]:
                # A load re-issued later for the same command is the same run
                # restarting, not a second one left unseeded.
                if not any(r["command"] == run["command"] for r in self.runs[i + 1 :]):
                    out.append(f"  {run['command']}: loaded, but no process step was seeded")
                continue
            still_open = [t for t in run["tasks"] if self.status.get((run["server"], t)) in _OPEN]
            if still_open:
                out.append(
                    f"  {run['command']}: {len(still_open)} of {len(run['tasks'])} steps still "
                    f"open (task ids {', '.join(still_open)})"
                )
        return out


_HANDLERS = {
    "np_read_command": _Session.read_command,
    "np_task_create": _Session.task_create,
    "np_task_update": _Session.task_update,
    "np_task_list": _Session.task_list,
    "np_todo_write": _Session.task_list,
}


def _blocks(lines: list[str]):
    """Every content block of the main thread, in order.

    Subagent entries (`isSidechain`) are another agent's run, so they are skipped.
    """
    for raw in lines:
        entry = _json(raw)
        if not isinstance(entry, dict) or entry.get("isSidechain"):
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, list):
            yield from (b for b in content if isinstance(b, dict))


def open_steps(lines: list[str]) -> list[str]:
    """One reminder line per loaded command that is not closed.

    A call whose result is an error changed nothing on the server, so only a
    successful result is folded into the state.
    """
    session = _Session()
    calls: dict[str, tuple[str, str, dict]] = {}
    for block in _blocks(lines):
        if block.get("type") == "tool_use":
            match = _TOOL.match(str(block.get("name", "")))
            if match and match["tool"] in _HANDLERS:
                args = block.get("input")
                calls[str(block.get("id"))] = (
                    match["server"],
                    match["tool"],
                    args if isinstance(args, dict) else {},
                )
        elif block.get("type") == "tool_result" and not block.get("is_error"):
            call = calls.pop(str(block.get("tool_use_id")), None)
            if call:
                server, tool, args = call
                _HANDLERS[tool](session, server, args, _json(_text(block.get("content"))))
    return session.reminders()


def main() -> None:
    """Remind once per stop cycle about loaded commands with open process steps."""
    event = load_event() or {}
    # The reminder re-invokes Claude; on that forced continuation `stop_hook_active`
    # is true, so return and let it stop — once per cycle, not a loop.
    if event.get("stop_hook_active"):
        return
    transcript = event.get("transcript_path")
    if not transcript:
        return  # nothing to read: not a Claude Code stop event
    try:
        lines = Path(transcript).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        # Visible, not silent: a skipped check must not read as a closed run.
        report_skip("command-closure-reminder", f"{type(exc).__name__}: {exc}", "transcript read")
    reminders = open_steps(lines)
    if reminders:
        stop_feedback(
            "\n".join(
                [
                    "Nitpicker command process not closed:",
                    *reminders,
                    "Close each step with np_task_update and read the list back with "
                    "np_task_list before reporting (_conventions.md § Execution). If the run "
                    "is waiting on the user or on background work, say so; if the command was "
                    "read without being run, say that.",
                ]
            )
        )


if __name__ == "__main__":
    main()
