# Design: `nitpicker-mcp` — stdio MCP server for skills + findings

**Date:** 2026-07-18
**Branch:** `feat/tools`
**Status:** Design (awaiting review before implementation)

## Goal

Expose the repository's skill catalog and its audit-findings store to
agents as MCP tools. Today `findings.py` is a CLI an agent must shell out to
and there is no programmatic skill listing at all. An MCP server gives a
Claude-Code-native, discoverable tool surface for: listing/reading skills and
their commands, and reading + managing findings.

## Decisions already made

Three design forks were resolved with the repo owner during brainstorming:

1. **Form:** a real MCP server (stdio), not a CLI-only or CLI-first approach.
   Explicitly accepted that this is Claude-native and **not** portable to
   Copilot/pi the way the shipped skill is.
2. **Deps + placement:** stdlib-only, hand-rolled JSON-RPC loop, living under
   `skills/nitpicker/scripts/` (recommended over an `mcp`-SDK server under
   `scripts/`). Rationale below.
3. **Tool surface:** all four categories — skills list/read, findings
   read-only, findings mutate, repo meta.

## Architecture

### Placement & form

`skills/nitpicker/scripts/mcp_server.py` — a JSON-RPC 2.0 over stdio loop,
`#!/usr/bin/env python3`, stdlib-only (`json`, `sys`, `os` only). It implements
the three MCP methods a tool server needs: `initialize`, `tools/list`,
`tools/call`. No `mcp` SDK. Target ~150 lines.

**Why stdlib over the SDK:** the shipped-tool contract
(`.claude/rules/use-uv-runner.md`, enforced by `check-stdlib-only.py`) forbids
non-stdlib imports under `skills/*/scripts/`. The `mcp` SDK would break that
gate for what is, in substance, a dispatch table plus a JSON envelope. The
protocol surface we need is tiny and stable. The SDK-under-`scripts/`
alternative would make this a permanent dev-machine-only convenience rather
than a capability that ships with the skill — not worth the saved lines.

### Reuse, not rewrite

The server owns no findings or skills logic. Two backing modules, each also a
standalone stdlib CLI (mirroring `findings.py`'s library-plus-`main()` split):

- **`findings.py` — unchanged.** It already separates a library layer
  (`new_finding`, `resolve_finding`, `show_finding`, `validate_store`,
  `build_index`, `iter_open`, `read_ledger`, `resolved_records`,
  `parse_frontmatter` — all return data structures) from the thin `main()` CLI
  wrapper. The server imports the module and calls the library functions
  directly. Because those functions **return** rather than `print`, the
  JSON-RPC stdout channel is never polluted (warnings go to stderr via
  `_note`, which is safe).
- **`skills.py` — new** stdlib module + CLI under
  `skills/nitpicker/scripts/`. Responsibilities:
  - enumerate skills: `glob("skills/*/SKILL.md")` +
    `glob(".claude/skills/*/SKILL.md")`, skipping the `VENDORED_SKILLS`
    set (reuse the same names as `validate-skill.py`);
  - parse frontmatter (`name`, `description`) reusing
    `findings.parse_frontmatter`;
  - parse the nitpicker Commands table (canonical name + aliases + purpose),
    reusing the approach in `validate-skill.py:table_commands`;
  - read a SKILL.md or a `commands/<command>.md` file by name.
  - CLI subcommands: `list`, `read <skill>`, `commands [skill]`,
    `read-command <command>`.

### Root resolution

`findings.py` addresses its store as cwd-relative `docs/audit/findings`. The
server resolves the workspace root once at startup in this order:
`CLAUDE_PROJECT_DIR` env → `findings.find_repo_root(cwd)` → cwd. That root is
passed explicitly into every backing call; no per-tool cwd guessing.

### Registration

`.mcp.json` at repo root:

```json
{
  "mcpServers": {
    "nitpicker": {
      "command": "python3",
      "args": ["skills/nitpicker/scripts/mcp_server.py"]
    }
  }
}
```

Wiring into plugin distribution (so `/plugins` installs the server) is a
follow-up, noted here but out of scope for this spec. The server is not
portable to Copilot/pi — accepted trade-off.

## Tool surface (10 tools)

| Category | Tool | Args | Backed by |
| --- | --- | --- | --- |
| Skills | `list_skills` | — | `skills.py` |
| Skills | `read_skill` | `name` | `skills.py` |
| Skills | `read_command` | `command` | `skills.py` |
| Findings (read) | `list_findings` | `auditor?`, `severity?`, `status?` | `findings.iter_open` + `read_ledger` |
| Findings (read) | `show_finding` | `id` | `findings.show_finding` |
| Findings (read) | `findings_index` | — | `findings.build_index` |
| Findings (read) | `validate_store` | — | `findings.validate_store` |
| Findings (mutate) | `new_finding` | `auditor`, `severity`, `category`, `area`, `title`, `problem`, `evidence`, `impact`, `fix` | `findings.new_finding` |
| Findings (mutate) | `resolve_finding` | `id`, `status`, `note` | `findings.resolve_finding` |
| Meta | `list_commands` | `skill?` | `skills.py` |

Each tool declares a JSON Schema `inputSchema` in `tools/list`. Read tools
return text/JSON content; mutate tools return the created id / ledger record.

## Data flow

```text
agent → tools/call (JSON-RPC over stdio)
      → mcp_server.py dispatch table
      → skills.py  |  findings.py  (library functions, return data)
      → JSON result envelope → agent
```

## Error handling

- Protocol / unknown-method / malformed-frame failures → JSON-RPC `error`
  objects with standard codes.
- Tool-level failures (unknown finding id, validation error, unknown skill) →
  a normal tool result with `isError: true` and the message in text content,
  so the model sees it and can recover rather than the whole call faulting.
- The read loop tolerates and skips blank lines; a decode error on one frame
  does not kill the server.

## Testing

Under `tests/` (uv-run, pytest — internal tooling, not shipped):

- `test_skills_py.py` — skill enumeration (incl. vendored skip), frontmatter
  parse, Commands-table parse (name + aliases), command-file read, unknown-name
  handling.
- `test_mcp_server.py` — drive the loop with crafted `initialize`,
  `tools/list`, and `tools/call` frames over an in-memory pipe; assert framing
  and payloads. Include one mutate round-trip (`new_finding` → `list_findings`
  → `resolve_finding`) against a temp store to prove the wiring end to end.

`mcp_server.py` and `skills.py` must remain stdlib-only (gated by
`check-stdlib-only.py`); tests may use uv.

## Docs

- A short "MCP server" section in `skills/nitpicker/SKILL.md` (what it exposes,
  how to register).
- A README row/note.
- Module docstring in `mcp_server.py` enumerating the 10 tools.
- No `_conventions.md` change (server adds no audit-command behavior).

## Deferred (YAGNI)

- Wrappers for `fetch-pr-comments.py` / `process-sarif.py` — add when a
  workflow needs them over MCP.
- `baseline` / `migrate` / `migrate-resolved` tools — maintenance ops, not
  agent-loop tools; keep them CLI-only.
- Plugin-distribution wiring of the server — separate follow-up.

## Validation gates this must pass

`make check`: `check-stdlib-only.py` (new files stdlib-only), ruff
lint/format, pytest, `validate-json-hook` on `.mcp.json`, and the existing
skill/findings validators (unaffected).
