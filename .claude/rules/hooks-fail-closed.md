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

## Enforcement

Author discipline. `tests/test_hooks.py` drives the exception arm of the guards
it has a test for, through a stdin stand-in whose `read()` raises, and
`test_pretooluse_guards_fail_closed_on_an_unreadable_event` feeds each guard in
`PRETOOLUSE_GUARDS` an unreadable event; nothing requires a new guard to carry
the wrapper, the strict loader, or a place in that list.
