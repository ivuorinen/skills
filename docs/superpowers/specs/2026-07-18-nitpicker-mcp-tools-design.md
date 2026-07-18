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
- **`skill_catalog.py` — new** stdlib module + CLI under
  `skills/nitpicker/scripts/`. **Named `skill_catalog.py`, not `skills.py`:**
  the repo root contains a `skills/` directory (a namespace package on the
  import path), so `import skills` from `mcp_server.py` could bind to that
  directory instead of the sibling module depending on launch method. A
  distinct module name removes the ambiguity entirely. Responsibilities:
  - enumerate skills: `glob("skills/*/SKILL.md")` +
    `glob(".claude/skills/*/SKILL.md")`, skipping the `VENDORED_SKILLS`
    set (reuse the same names as `validate-skill.py`);
  - parse frontmatter (`name`, `description`) reusing
    `findings.parse_frontmatter`;
  - parse the nitpicker Commands table (canonical name + aliases + purpose),
    reusing the approach in `validate-skill.py:table_commands`;
  - resolve a skill or command **only by exact match against the enumerated
    set** — never by building a path from the raw input (see Security below);
  - read a SKILL.md or a `commands/<command>.md` file by validated name.
  - CLI subcommands: `list`, `read <skill>`, `commands [skill]`,
    `read-command <command>`.

### Root resolution

`findings.py` addresses its store as cwd-relative `docs/audit/findings`. The
server resolves the workspace root in this order: `CLAUDE_PROJECT_DIR` env →
`findings.find_repo_root(cwd)` → cwd, and passes it explicitly into every
backing call. Per Open decision D2 the recommendation is to resolve **per
call** (not once at startup) so a stale binding can't outlive a workspace
change, and to scope this iteration to a repo-local `.mcp.json`.

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

This iteration is **scoped to repo-local `.mcp.json`** (see Open decision D2).
Plugin-distribution wiring (so `/plugins` installs the server) is deferred —
it interacts with root resolution and is a separate follow-up. The server is
not portable to Copilot/pi — accepted trade-off.

## Tool surface (10 tools)

| Category | Tool | Args | Backed by |
| --- | --- | --- | --- |
| Skills | `list_skills` | — | `skill_catalog.py` |
| Skills | `read_skill` | `name` | `skill_catalog.py` |
| Skills | `read_command` | `command` | `skill_catalog.py` |
| Findings (read) | `list_findings` | `auditor?`, `severity?`, `status?`, `limit?` | `findings.iter_open` + `read_ledger` (server-side filter/merge) |
| Findings (read) | `show_finding` | `id` | `findings.show_finding` |
| Findings (read) | `findings_index` | — | `findings.build_index` |
| Findings (read) | `validate_store` | — | `findings.validate_store` |
| Findings (mutate) | `new_finding` | `auditor`, `severity`, `category`, `area`, `title`, `problem`, `evidence`, `impact`, `fix` | `findings.new_finding` (server assembles `body`) |
| Findings (mutate) | `resolve_finding` | `id`, `status`, `note` | `findings.resolve_finding` |
| Meta | `list_commands` | `skill?` | `skill_catalog.py` |

Each tool declares a JSON Schema `inputSchema` in `tools/list`. Read tools
return text/JSON content; mutate tools return the created id / ledger record.

**`new_finding` body assembly (H1).** `findings.new_finding` takes a single
`body: str`, not four section fields. The tool exposes the four fields
(`problem`/`evidence`/`impact`/`fix`) for agent ergonomics and to enforce the
store's required sections at the boundary; the server joins them into the
`## Problem … ## Evidence … ## Impact … ## Fix` markdown that `new_finding`
expects before the call. The tool signature and the function signature are
different by design — the server bridges them.

**`list_findings` merge/filter (M1).** `iter_open` returns *all* open findings
with no filtering, and the resolved ledger is separate. The server does the
work: `status=open` → `iter_open`; `status∈{fixed,invalid}` → `read_ledger`;
no `status` → both merged. `auditor` and `severity` are filtered in Python
after collection. `limit` truncates the result (default reasonable cap) so a
large store cannot flood model context.

## Data flow

```text
agent → tools/call (JSON-RPC over stdio)
      → mcp_server.py dispatch table
      → skill_catalog.py | findings.py  (library functions, return data)
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

## Security

The tool arguments are model-controlled and may carry prompt-injected content
from the repository under audit. Two boundaries must hold:

- **No path construction from raw input.** `read_skill` / `read_command` /
  `list_commands(skill)` resolve their name argument only by exact match
  against the enumerated skill/command set that `list_skills` / `list_commands`
  already build. Anything not in the set returns an `isError` result. A path is
  never built as `base / f"{name}/SKILL.md"` from the raw argument — that would
  make `read_command("../../../../etc/passwd")` an arbitrary-file-read
  primitive.
- **Import isolation.** The server module imports `findings` and
  `skill_catalog` by distinct names (never `skills`, which collides with the
  repo-root `skills/` namespace package). `mcp_server.py` prepends its own
  directory to `sys.path` so the sibling modules resolve deterministically
  regardless of launch cwd.

## Testing

Under `tests/` (uv-run, pytest — internal tooling, not shipped):

- `test_skills_py.py` — skill enumeration (incl. vendored skip), frontmatter
  parse, Commands-table parse (name + aliases), command-file read, unknown-name
  handling.
- `test_mcp_server.py` — drive the loop with crafted `initialize`,
  `tools/list`, and `tools/call` frames over an in-memory pipe; assert framing
  and payloads. Include one mutate round-trip (`new_finding` → `list_findings`
  → `resolve_finding`) against a temp store to prove the wiring end to end.
- **stdout-cleanliness test (M3) — load-bearing.** The stdio design rests on
  backing functions never writing to stdout. Assert it directly: run a
  `tools/call` (including a mutate, which writes files and refreshes the index)
  and assert stdout contains **only** the JSON-RPC response frame(s) — zero
  extra bytes. This pins the property the whole transport depends on so a
  future stray `print` fails a test instead of silently corrupting the stream.
- **Path-traversal test (C1).** `read_command("../../etc/passwd")` and an
  unknown skill name both return `isError`, not file contents.

`mcp_server.py` and `skill_catalog.py` must remain stdlib-only (gated by
`check-stdlib-only.py`); tests may use uv.

## Docs

- A short "MCP server" section in `skills/nitpicker/SKILL.md` (what it exposes,
  how to register).
- A README row/note.
- Module docstring in `mcp_server.py` enumerating the 10 tools.
- No `_conventions.md` change (server adds no audit-command behavior).

## Open decisions (owner call)

These two came out of the adversarial review as genuine design choices, not
mechanical fixes. Recommendations given; not yet locked.

**D1 — Consent model for mutate tools (from H3).** `_conventions.md` gates
every findings mutation behind human prompts (Apply fixes? / Commit to git?)
that explicitly override autonomous mode. The MCP `new_finding` /
`resolve_finding` tools sit outside that interactive flow — an agent can create
and resolve findings (resolve deletes the open file + appends the ledger)
without a prompt.

- **Recommended:** keep both mutate tools, and document that the MCP surface is
  intentionally outside the interactive consent model — git is the safety net
  (every mutation is a reviewable, revertible working-tree change; nothing is
  pushed). The consent prompts remain in force for the `/nitpicker` command
  flow.
- **Alternative:** expose `new_finding` only and keep `resolve_finding`
  CLI-only, since resolution is the destructive half (unlink + ledger append).

**D2 — Root resolution & distribution scope (from M2).** Resolving the repo
root once at startup binds the whole session to one tree; with a global
install it can `find_repo_root` the *wrong* tree.

- **Recommended:** scope this iteration to a repo-local `.mcp.json` (cwd is the
  project) and resolve the root **per call** rather than once at startup — cheap
  hardening that also lets a future global install pass an explicit root. Drop
  plugin-distribution wiring to Deferred.
- **Alternative:** commit to distribution now and add an explicit `root` arg to
  every findings tool. More surface, more to validate; not worth it until the
  repo-local version proves out.

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
