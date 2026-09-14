---
paths:
  - "skills/*/scripts/**"
---

# Editing a Shipped Tool Mid-Session

The MCP server imports every shipped module it depends on once at startup and
holds them for the life of the process. `_LOADED` in `mcp_server.py` is the
authoritative list; it includes the hyphen-named `process-sarif.py` and
`check-rules-anatomy.py`, which reach it through `_load_bundled` rather than a
plain import and are easy to overlook. **Editing any module on that list does
not change what the running server executes.** Worse, two servers are
registered: `.mcp.json` starts one from the working tree, and
`.claude-plugin/plugin.json` starts one from `${CLAUDE_PLUGIN_ROOT}` — the
installed copy under `~/.claude/plugins/cache/`, which reflects only the
installed version, at any age.

So after editing anything under `skills/*/scripts/`, drive the findings store
through `python3 skills/nitpicker/scripts/findings.py` for the rest of the
session; it loads fresh every invocation. Restarting the session picks up the
new code.

`mcp_server.py` records each module's mtime at import (its own file included)
and prefixes a `[warn]` line to the result of every tool that writes
(`np_new_finding`, `np_resolve_finding`, `np_write_index`) when the file has
since changed, or when it is serving a different copy than on disk. The read
tools carry no such prefix, so an edit to `process-sarif.py` or
`check-rules-anatomy.py` reaches you through the rule above and through nothing
else: `np_process_sarif` will consolidate a security scan with code that is not
on disk and say nothing. This is a backstop, not the control: the rule above is.

This is not hypothetical. A stale `redact()` wrote an unredacted credential into
`resolved.jsonl` during the audit that added the redaction, and only a
`detect-private-key` commit hook caught it — see `audit-9bc6eb39`.

## Enforcement

Agent discipline. The `[warn]` prefix covers the write tools only, and it
reports a stale server after the call has already run.
