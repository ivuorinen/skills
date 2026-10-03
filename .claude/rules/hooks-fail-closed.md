---
paths:
  - "scripts/hooks/**"
---

# Guards Fail Closed

Claude Code blocks a tool call only when a PreToolUse hook exits 2. Any other
non-zero exit is a non-blocking error, so a guard that dies on an uncaught
exception exits 1 and lets through the call it exists to stop.

Every PreToolUse guard wraps its entry point and, on any exception, exits 2
with a `DENIED` line on stderr naming the internal failure. `SystemExit` is
re-raised so a deliberate exit keeps its code:

```python
if __name__ == "__main__":
    with guard_deadline("<guard>"):
        try:
            main()
        except SystemExit:
            raise
        except Exception as exc:  # fail closed
            print(f"  DENIED  <guard> failed internally: {exc}", file=sys.stderr, flush=True)
            sys.exit(2)
```

Every repo guard carries this form, `deny-agents-path-hook.py` included. A guard
whose decision is *ask* rather than *deny* answers ask from the same arm —
`ask-destructive-restore-hook.py` does — and never allow.

An event the guard cannot read is the same case. Every PreToolUse guard loads
its event with `_hooklib.load_event_strict`, which raises on an empty,
truncated or non-object event so the arm above denies; the lenient
`load_event`, which returns None, belongs to PostToolUse and Stop hooks only.
A guard that returned on None allowed the call (errors-4a2d2f34).

The same holds one layer out. Each repo guard's `.claude/settings.json` command
exits 2 when `uv` is missing, and maps any exit of the guard other than 0 or 2
to 2, so a guard that cannot start, or dies before its own wrapper runs, denies.

## A timeout is an allow

Claude Code cancels a hook that runs past its `timeout` (600 seconds when the
entry names none), and a timed-out command hook does not block: the call
continues through the normal permission flow. The shell wrapper above never
sees an exit code to map. So a guard that input can slow down — a quadratic
parse of a padded command — fails open at its timeout
(agent-loopholes-793d7db7).

Two bounds close that, and the order between them is the rule:

- `_hooklib.guard_deadline` wraps each guard's `__main__` and exits 2 once the
  guard has run `GUARD_DEADLINE_SECONDS`. It uses SIGALRM, whose handler the
  regex engine runs mid-match, and exits with `os._exit` so no handler inside
  the guard can catch it. On expiry the restore guard denies too: an ask needs
  a complete JSON answer the interrupted run may not have.
- Every PreToolUse entry in `.claude/settings.json` names its `timeout`, at
  least half again above the deadline, so the guard's own deny always lands
  first, with room left for `uv` to start the interpreter.

The graphify guards `exec` an external binary, so they get the explicit
`timeout` but no internal deadline; past it they allow, like any hook.

## Enforcement

Partly gated. `tests/test_settings.py` fails when a PreToolUse entry has no
`timeout`, when a repo guard's timeout is under one and a half times
`GUARD_DEADLINE_SECONDS`, or when a repo guard's `__main__` does not run under
`guard_deadline`. The rest is author discipline: `tests/test_hooks.py` drives
the exception arm of the guards it has a test for, through a stdin stand-in
whose `read()` raises, and
`test_pretooluse_guards_fail_closed_on_an_unreadable_event` feeds each guard in
`PRETOOLUSE_GUARDS` an unreadable event; nothing requires a new guard to carry
the exception wrapper, the strict loader, or a place in that list.
