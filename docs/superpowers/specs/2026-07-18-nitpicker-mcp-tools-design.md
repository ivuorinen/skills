# Design: `nitpicker-mcp` — stdio MCP server for skills + findings

**Date:** 2026-07-18
**Branch:** `feat/tools`
**Status:** Design complete — both open decisions resolved; ready for
implementation plan. Repo-meta tools dropped during implementation (444a84c);
not shipped.

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
3. **Tool surface:** three categories — skills list/read, findings read-only,
   findings mutate. (A fourth, repo meta, was dropped during implementation.)
4. **Distribution:** the MCP server ships **inside the plugin** and is
   installed/started automatically when the user installs the nitpicker plugin
   via `/plugins` — the owner runs this on multiple machines. This resolves
   former open decision D2 in favour of distribution (not repo-local only).
5. **Two roots by scope:** skill/command tools are scoped to the **plugin's
   own** bundled skills (owner's choice — introspect what nitpicker can do
   anywhere); findings tools are scoped to the **project being audited**. The
   two roots are resolved by different, independent mechanisms (see Root
   resolution).

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
    `glob(".claude/skills/*/SKILL.md")`, listing **all** discovered skills.
    No vendored-skip: `validate-skill.py`'s `VENDORED_SKILLS` governs
    *validation*, and duplicating that owner-governed set into a shipped file
    risks drift and is discouraged by `vendored-skills.md`; read-only listing
    of every installed skill (graphify included) is just accurate;
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

A plugin-bundled stdio server's **cwd and environment are unspecified by
Claude Code** (confirmed: the docs do not define them). So neither root may
depend on cwd. Two independent roots:

**Plugin root (skill/command tools) — derived from `__file__`.** The server
lives at `<plugin>/skills/nitpicker/scripts/mcp_server.py`, so the plugin root
is `Path(__file__).resolve().parents[3]` — deterministic, no cwd, no env, no
`${CLAUDE_PLUGIN_ROOT}` interpolation needed. `skill_catalog.py` globs
`<plugin>/skills/*/SKILL.md` and `<plugin>/.claude/skills/*/SKILL.md` under
that root. This is also how `mcp_server.py` locates its sibling modules
(`sys.path.insert(0, str(Path(__file__).resolve().parent))`).

**Project root (findings tools) — explicit arg first, then fallbacks.** The
findings store lives in the *audited* repo, which the server cannot reliably
infer from cwd. Resolution order, **per call**:

1. an optional `project_dir` argument on each findings tool — the calling
   agent always knows its absolute workspace path, so this is the reliable
   override that works regardless of how the server was launched;
2. `CLAUDE_PROJECT_DIR` env (passed through `.mcp.json` `env`, if Claude Code
   interpolates it — see Unknowns);
3. `findings.find_repo_root(cwd)` → cwd.

Resolving per call (not once at startup) means a stale binding can't outlive a
workspace change. `find_repo_root` returning the wrong tree is why the explicit
arg is first, not last.

### Registration (plugin distribution)

Claude Code auto-detects an **`.mcp.json` at the plugin root** (not inside
`.claude-plugin/`, and not in `plugin.json`). Because this repo *is* the
plugin, that file lives at the repo root and serves both installed users and
in-repo development:

```json
{
  "mcpServers": {
    "nitpicker": {
      "type": "stdio",
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/skills/nitpicker/scripts/mcp_server.py"],
      "env": {
        "CLAUDE_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}"
      }
    }
  }
}
```

- **Launch path** uses `${CLAUDE_PLUGIN_ROOT}` so it resolves in the installed
  plugin regardless of cwd. This variable's availability in `.mcp.json`
  `args` is **not officially documented** — see Unknowns; the implementation
  plan must verify it empirically and fall back to a relative path if needed.
- **`env`** forwards `CLAUDE_PROJECT_DIR` as fallback #2 for the project root.
  Interpolation here is also unconfirmed (Unknowns); the `project_dir` tool
  arg (fallback #1) is what makes correctness independent of it.
- **`python3` requirement.** The server is stdlib-only Python 3.11+, same
  assumption every shipped nitpicker tool already makes. If `python3` is
  absent the server fails to start — an existing, accepted constraint.
- **User approval on install.** A plugin-bundled MCP server prompts for consent
  on first install (launching a process), and may not surface that prompt in
  headless/CI. Documented, not a blocker.

The server is not portable to Copilot/pi — accepted trade-off.

### Unknowns to verify during implementation

Two Claude Code behaviours are not settled by the docs and must be confirmed on
a real install before the launch config is trusted; correctness does **not**
depend on either, because the `__file__`-derived plugin root and the
`project_dir` tool arg cover both:

1. Whether `${CLAUDE_PLUGIN_ROOT}` interpolates inside `.mcp.json` `args`.
   Fallback: relative path `./skills/nitpicker/scripts/mcp_server.py`.
2. Whether `${CLAUDE_PROJECT_DIR}` interpolates inside `.mcp.json` `env`.
   Fallback: rely on the `project_dir` tool arg (already fallback #1).

## Tool surface (10 tools)

Skill/command tools are **plugin-scoped** (plugin root, no root arg). Findings
tools are **project-scoped** and every one takes an optional `project_dir`
(fallback #1 for the project root, per Root resolution).

| Category | Tool | Args | Backed by |
| --- | --- | --- | --- |
| Skills | `list_skills` | — | `skill_catalog.py` (plugin root) |
| Skills | `read_skill` | `name` | `skill_catalog.py` (plugin root) |
| Skills | `read_command` | `command` | `skill_catalog.py` (plugin root) |
| Findings (read) | `list_findings` | `project_dir?`, `auditor?`, `severity?`, `status?`, `limit?` | `findings.iter_open` + `read_ledger` (server-side filter/merge) |
| Findings (read) | `show_finding` | `project_dir?`, `id` | `findings.show_finding` |
| Findings (read) | `findings_index` | `project_dir?` | `findings.build_index` |
| Findings (read) | `validate_store` | `project_dir?` | `findings.validate_store` |
| Findings (mutate) | `new_finding` | `project_dir?`, `auditor`, `severity`, `category`, `area`, `title`, `problem`, `evidence`, `impact`, `fix` | `findings.new_finding` (server assembles `body`) |
| Findings (mutate) | `resolve_finding` | `project_dir?`, `id`, `status`, `note` | `findings.resolve_finding` |
| Meta | `list_commands` | `skill?` | `skill_catalog.py` (plugin root) |

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

- `test_skill_catalog.py` — skill enumeration (incl. vendored skip),
  frontmatter parse, Commands-table parse (name + aliases), command-file read,
  unknown-name handling, and plugin-root derivation from `__file__`.
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

## Resolved decisions

Both design choices from the adversarial review are settled.

**D1 — Consent model for mutate tools (from H3) — RESOLVED: keep both.**
`_conventions.md` gates findings mutations in the `/nitpicker` flow behind
human prompts (Apply fixes? / Commit to git?). The MCP surface deliberately
sits **outside** that interactive model: both `new_finding` and
`resolve_finding` are exposed with no consent prompt. The safety net is git —
every mutation (`new_finding` writes an open file; `resolve_finding` unlinks it
and appends to the ledger) is a reviewable, revertible working-tree change and
nothing is ever pushed. `mcp_server.py`'s docstring and the SKILL.md MCP
section must state this non-interactive contract explicitly so it reads as
intent, not oversight. The consent prompts remain fully in force for the
`/nitpicker` command flow, which is unchanged.

**D2 — Root resolution & distribution scope (from M2) — RESOLVED.** The owner
distributes the server as part of the plugin and runs it on multiple machines,
so distribution is in scope. A plugin server's cwd/env are unspecified, so
root resolution does **not** rely on them: the plugin root is derived from
`__file__`, and the project root comes from an explicit `project_dir` tool arg
(with env/cwd fallbacks), resolved per call. See Root resolution and
Registration.

## Deferred (YAGNI)

- Wrappers for `fetch-pr-comments.py` / `process-sarif.py` — add when a
  workflow needs them over MCP.
- `baseline` / `migrate` / `migrate-resolved` tools — maintenance ops, not
  agent-loop tools; keep them CLI-only.

## Validation gates this must pass

`make check`: `check-stdlib-only.py` (new files stdlib-only), ruff
lint/format, pytest, `validate-json-hook` on `.mcp.json`, and the existing
skill/findings validators (unaffected).
