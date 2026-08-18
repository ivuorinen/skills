---
id: audit-9bc6eb39
auditor: audit
severity: medium
category: reliability
area: skills/nitpicker/scripts/mcp_server.py
status: open
found: 2026-08-18
---

# MCP server serves stale shipped-tool code for the life of the session

## Problem

The `nitpicker` MCP server is a long-lived process. It imports `findings.py`, `skill_catalog.py` and the PR providers once at startup and holds them in memory for the life of the session. Editing a shipped tool in the working tree does not change what the running server executes, and nothing in the tool results says so — an `np_*` call returns success either way.

Two registrations compound it. `.mcp.json` starts a project-scope server from the working tree, and `.claude-plugin/plugin.json` starts a plugin-scope server from `${CLAUDE_PLUGIN_ROOT}` — which resolves to the installed copy under `~/.claude/plugins/cache/`, pinned at the installed version. That second copy never reflects working-tree edits at all, no matter how long it has been running.

`_conventions.md` instructs every command to prefer the MCP tools over the CLI for store operations, so the default path is the stale one.

## Evidence

Observed during this session, immediately after extending `redact()` in `findings.py` and confirming the new patterns worked:

```text
$ ps -eo pid,etimes,cmd | grep mcp_server.py
 144238  166420  python3 ~/.claude/plugins/cache/ivuorinen-skills/.../3.0.0/skills/nitpicker/scripts/mcp_server.py
1934492  108681  python3 ./skills/nitpicker/scripts/mcp_server.py
1934498  108681  python3 ~/.claude/plugins/cache/ivuorinen-skills/.../3.0.0/skills/nitpicker/scripts/mcp_server.py
```

The project-scope server had been alive 108,681 seconds — about 30 hours — while the edit was 20 minutes old. Two further servers were running the 3.0.0 plugin cache copy.

`np_resolve_finding` then wrote a ledger record through the pre-edit `redact()`, leaving a PEM header in `resolved.jsonl` that the current redactor strips cleanly:

```text
line 504: id=audit-60923794 status=fixed
  body: '-----BEGIN … PRIVATE KEY-----'      (marker elided; see note below)

redact() applied to the same text today -> '[REDACTED PRIVATE KEY]'
```

The marker is elided above rather than quoted verbatim: the literal form trips this repo's own `detect-private-key` pre-commit hook, which is what makes the point — a finding that documents a credential shape cannot safely carry that shape.

The defect was caught only because pre-commit's `detect-private-key` and `gitleaks` hooks blocked the commit. Nothing in the MCP call itself indicated that a security control had been bypassed.

## Impact

Silent and general. Any fix to a shipped tool is inert for the rest of the session on the interface `_conventions.md` tells commands to prefer, and the tool result is indistinguishable from a correct one.

The redaction case is the sharp edge, because the write target is append-only: a secret written by a stale redactor is permanent, and the store's `linguist-generated` mark collapses it in PR review. Here the commit hooks caught it; a credential shape those hooks do not model — a GitLab or Bitbucket token, neither of which `detect-private-key` knows — would have landed silently.

It also undermines the audit loop itself. `/nitpicker audit` fixes a shipped tool, then resolves its own finding through the MCP tools, recording "fixed" via the code path that has not been fixed. That is the exact sequence that occurred.

## Fix

Documentation first, because the behaviour is inherent to a long-lived server and not a bug in the code:

1. Add a caveat to `_conventions.md` beside the tool-preference section: after editing anything under `skills/*/scripts/`, the MCP tools run the previous code until the server restarts — drive the store through `findings.py` for the remainder of that session. Note that the plugin-scope server serves the *installed* copy and never reflects working-tree edits.
2. Say the same in `CLAUDE.md` where the MCP server is described, since that is where a contributor editing a shipped tool is reading.

Then make it observable rather than inferred. `np_list_skills` already returns plugin metadata; have the server report the resolved path and mtime of the `findings.py` it loaded, so a caller can tell a working-tree server from a plugin-cache one and see when its code was loaded. A one-line divergence check against the on-disk mtime, warned on stderr at startup, would have surfaced this in the session that caused it.

Not proposed: auto-reloading modules on change. That trades a visible staleness problem for an invisible partial-reload one, and the server is cheap to restart.
