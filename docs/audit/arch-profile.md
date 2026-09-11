# Architecture Profile

Generated: 2026-09-10

This repository has **two distinct architectures over the same tree**, and they
must be read separately or neither makes sense:

- an **instruction architecture** — markdown artifacts (`SKILL.md`,
  `commands/*.md`, `references/tools/*.md`, `.claude/rules/*.md`) dispatched and
  loaded by an agent at runtime, and
- a **code architecture** — the Python under `skills/*/scripts/`, `scripts/`,
  `scripts/hooks/` that those instructions invoke.

Every pattern below is tagged with which of the two it governs.

## Detected Patterns

### Plugin / Extension — High confidence

Governs: both layers.

Evidence:

- `.claude-plugin/plugin.json` declares the distributable unit (`name`,
  `version`, `keywords`) and registers a stdio MCP server under `mcpServers`
  resolved through `${CLAUDE_PLUGIN_ROOT}` — the plugin is the deployment
  boundary, not the repo.
- `.claude-plugin/marketplace.json` publishes the same unit for `/plugins`
  discovery; both manifests are schema-pinned against `schemas/plugin.schema.json`
  and `schemas/marketplace.schema.json`.
- `skills/<skill>/` is a self-contained extension unit: `SKILL.md` + `commands/`
  - `references/` + `scripts/` + `evals/`. `skills/nitpicker/` is the only
  shipped one; `.claude/skills/` holds five internal units of the same shape
  (`new-command`, `release-prep`, `skill-tester`, `skills`, `validate-skills`)
  plus the vendored `graphify`.
- `.claude/skills/nitpicker` is a symlink to `../../skills/nitpicker`, so the
  shipped extension is discovered by the same host mechanism as the internal
  ones without being copied.
- Dependency direction: extension units never import each other. Verified — no
  cross-skill import edge exists in the static graph.

### Microkernel (core + extension registry) — High confidence

Governs: the instruction layer.

Evidence:

- `skills/nitpicker/SKILL.md` is the kernel: it holds `## Dispatch` (parse the
  first word, resolve against the tables) and nothing else executable. Its own
  text states it "only dispatches; it never restates a command's flow".
- `skills/nitpicker/commands/` is the extension registry — 52 files, of which 6
  are `_`-prefixed shared references and the rest are individually dispatchable
  commands.
- The registry is **enforced 1:1**, not conventional:
  `scripts/validate-skill.py:611-617` errors both ways — a table row with no
  `commands/<cmd>.md`, and a `commands/*.md` absent from the table. Aliases,
  which have no file to check against, are enforced separately by
  `_alias_errors` (`:551`) against collision and duplication.
- Extension points are declared by `###` heading and are self-describing:
  SKILL.md states that each `###` heading *is* the category name and that
  `np_list_commands` filters on them, so adding a group makes it filterable in
  the same commit. No parallel category list is maintained.
- Trigger-loaded protocols are the kernel's lazy-load mechanism:
  `_findings-store`, `_committing`, `_documentation`, `_audit-coverage`,
  `_teach-formats` load on a stated trigger rather than at dispatch.

### Ports and Adapters (Hexagonal) — High confidence, subsystem-scoped

Governs: the code layer, in the PR-fetching subsystem only.

Evidence:

- **Driven port**: `pr_common.py` defines the domain type `Target` and the
  provider contract. Every adapter implements exactly two functions with an
  identical signature — `fetch_comments(target: pr_common.Target, pr_number: int)
  -> dict[str, Any]` and `fetch_status(...)` — verified at `pr_github.py:457,606`,
  `pr_gitlab.py:210,297`, `pr_bitbucket.py:199,284`.
- **Driven adapters**: `pr_github.py`, `pr_gitlab.py`, `pr_bitbucket.py`, one per
  platform. All three import `pr_common`; `pr_common` imports none of them.
- **Dependency inversion at the port is explicit and commented**:
  `pr_common.py:806` maps platform → module name as literal strings; resolution
  is deferred to `importlib.import_module` at `pr_common.py:863`, with the
  docstring stating the reason — "every provider imports this module, so a
  top-level import here would be a cycle."
- **Driving adapters** — two, each independent of the other and of the port's
  internals. `pr_cli.py` serves the command line: `fetch-pr-comments.py:83` and
  `fetch-pr-status.py:88` each reduce to
  `sys.exit(pr_cli.run_cli(__doc__, "<operation>", sys.argv[1:]))`.
  `mcp_server.py` serves the MCP client and exposes the same providers as
  `np_pr_comments` / `np_pr_status`. Both reach a provider only through
  `pr_common.provider_for`.
- **The port carries no delivery mechanism.** argv parsing, stdout rendering and
  exit codes live in `pr_cli.py` (`emit:35`, `parse_cli_args:70`, `run_cli:106`),
  never in `pr_common`, which all three providers and the MCP server import.
  `tests/test_pr_cli.py::TestPortStaysFreeOfDeliveryConcerns` pins the split,
  since nothing about it fails at runtime if it is undone.
- The port's value is a **single output shape**: a field a platform cannot supply
  is present and empty or null rather than absent, so a caller reads every key
  unconditionally instead of branching on which platform answered.

### Repository Pattern — High confidence

Governs: the code layer, for the findings store.

Evidence:

- `skills/nitpicker/scripts/findings.py` is the sole data-access module over
  `docs/audit/findings/**`. Its surface is a repository surface: `iter_open`,
  `read_ledger`, `append_ledger`, `write_ledger`, `resolved_records`,
  `new_finding`, `resolve_finding`, `show_finding`, `read_baseline`,
  `write_baseline`, `clear_baseline`, `store_lock`, `validate_store`.
- No other module opens store files. Verified by search: outside `findings.py`
  the only references to `resolved.jsonl` / `docs/audit/findings/` / `INDEX.md`
  are `mcp_server.py` tool *descriptions*, a path prefix in
  `post-bash-revalidate.py:45`, and `validate-audit-findings-hook.py`, which
  delegates back into `findings.py`.
- `skill_catalog.py` imports `findings`; the MCP findings tools go through it;
  `findings_export.py` is a downstream renderer, not a second access path
  (its own header: "the store's read/write primitives stay one concern and the
  renderers another").
- Identity is owned by the repository, not the caller: `finding_id()` content-
  hashes, so IDs are never hand-assigned or reused.
- Concurrency is owned by the repository: `store_lock()` and a `.lock` file in
  the store root.

### Ring dependency rule (Onion-shaped, informally) — High confidence as a rule, Medium as a named pattern

Governs: the code layer.

Evidence — three rings, verified acyclic and inward-only across the full static
import graph of 72 Python modules:

| Ring | Path | Runtime contract |
| --- | --- | --- |
| Inner | `skills/*/scripts/` (16 modules) | stdlib-only, `#!/usr/bin/env python3` |
| Middle | `scripts/` (11 modules) | uv, PEP-723 inline metadata |
| Outer | `scripts/hooks/` (14 modules) | uv, invoked by the harness |

- **No inner→outer edge exists.** The shipped ring imports nothing from
  `scripts/` or `scripts/hooks/`; its only non-stdlib imports are its own
  siblings (`md_fences`, `pr_common`, `pr_cli`, `findings`, `findings_export`,
  `context_pack`, `skill_catalog`).
- Outward rings depend inward: `scripts/bench-retrieval.py` imports
  `context_pack`; `scripts/common.py` and `scripts/validate-rules.py` reach
  `findings.py` and `check-rules-anatomy.py` by path.
- The inner ring's contract is **machine-enforced**, not conventional:
  `scripts/check-stdlib-only.py` walks `SHIPPED_GLOB = "skills/*/scripts/**/*.py"`,
  rejects any non-stdlib import root, rejects a shebang that is not
  `SHIPPED_SHEBANG`, rejects a PEP-723 block, and fails when the glob itself
  matches nothing (`check-stdlib-only.py:183,250,318`).
- The **direction** is enforced separately by `scripts/check-ring-deps.py`
  (`make ring-deps`, in `make check`), which builds the graph from `import`
  statements *and* from `spec_from_file_location` loads, and exits non-zero on
  an outward edge or on a module load it cannot resolve. It exists because
  `check-stdlib-only` reads imports only, and the edges most likely to cross a
  ring here are the ones no import statement expresses.
- Third-party imports appear in exactly one place — `tests/` (`pytest`, `yaml`,
  `bandit`) — which is outside all three rings.

### Shared Kernel — High confidence

Governs: the code layer.

Evidence — four deliberate shared modules, each with a stated single rule and
multiple consumers, none of which import each other's owners:

- `md_fences.py` — the markdown code-fence rule, defined once, consumed by
  `findings.py`, `skill_catalog.py`, `check-agent-instructions.py` and
  `check-rules-anatomy.py` (12 call sites total).
- `pr_common.py` — targets, HTTP transport, pagination, output envelope, for all
  three providers and both entry points.
- `scripts/hooks/_hooklib.py` — imported by all 13 hook modules and by nothing
  else.
- `scripts/common.py` — imported by `validate-skill.py` and `list-skills.py`.

### Hub-and-spoke with enforced depth-1 references — High confidence

Governs: the instruction layer.

Evidence:

- `scripts/validate-skill.py:538-560` enforces the Agent Skills File Reference
  Depth rule: every `commands/_*.md` shared reference must be named in `SKILL.md`
  itself, because a reference reachable only as `SKILL.md → command → ref` chains
  two levels deep and is rejected.
- The match is a token match on the stem with fences stripped first, so a name
  appearing only inside a code example does not satisfy the rule.
- The same shape governs the scanner references: SKILL.md names the
  `references/tools/<tool>.md` path directly so each is one hop from the router,
  and states the reason — "a host with two scanners installed loads two files
  rather than the ~160 lines all of them come to."
- The instruction layer carries a **budget**, enforced by
  `skills/nitpicker/scripts/check-agent-instructions.py` over the always-loaded
  set (`CLAUDE.md`, `AGENTS.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md`):
  fails above 150 directives, reports above 100.

### Append-only ledger with a derived projection — Low confidence (partial Event Sourcing)

Governs: the code layer, findings store only.

Evidence:

- `resolved.jsonl` is an append-only record log (`append_ledger`,
  `_ledger_line`), and `INDEX.md` is regenerated wholly from store state — the
  MCP tool `np_write_index` is the only one carrying `idempotentHint: true` for
  exactly that reason.
- `docs/audit/findings/.gitattributes` marks the whole store `linguist-generated`,
  treating it as derived output rather than authored source.

**Why only Low:** open findings are mutable one-file-per-finding documents, not
events, and current state is not reconstructed by replaying the ledger — the
ledger records only the resolution transition. This is a ledger-plus-projection
idiom, not Event Sourcing. It is listed so a later reader does not mistake the
append-only file for the real thing.

### Patterns explicitly NOT detected

DDD, Clean Architecture, Onion (as a named layering), Layered/N-Tier, CQRS,
Event Sourcing, Event-Driven, Saga/Process Manager, MVC, MVVM, MVP, Vertical
Slice, Modular Monolith, Microservices, Pipe and Filter, SOA.

Evidence: a full directory scan for the catalogue's structural signals
(`domain`, `adapters`, `ports`, `entities`, `use-cases`, `infrastructure`,
`application`, `presentation`, `repositories`, `commands`, `queries`,
`handlers`, `events`, `sagas`, `models`, `views`, `controllers`, `presenters`,
`viewmodels`, `features`, `plugins`, `core`, `pipeline`, `filters`,
`projections`) returns exactly four real hits, none of them architectural:
`.claude-plugin/` (a manifest directory), `.claude/skills/new-command/`,
`skills/nitpicker/commands/` (markdown instruction files, not command objects),
and `docs/audit/findings/review/` (a findings-store auditor bucket). Class-name
scan finds no `*Entity`, `*ValueObject`, `*Aggregate`, `*Repository`,
`*DomainService`, `*Port`, `*Adapter`, `*Handler`, `*ViewModel` or `*Presenter`
suffix anywhere — the only non-test classes in the tree are `UsageError`,
`TransportError`, `_TokenSafeRedirectHandler`, `_Result` and `_R`.

## Detected Combination

**Custom hybrid: Microkernel plugin host (instruction layer) over a stdlib-only
inner ring, with Ports-and-Adapters in the PR subsystem and a Repository over
the findings store.**

This is not any catalogued canonical combination. The closest catalogue entry is
*Plugin/Extension + Microkernel*, which covers the instruction layer only and
says nothing about the ring rule or the hexagonal subsystem.

## Inferred Structural Rules

These are what `/nitpicker arch` should validate against.

**Ring rule (code layer):**

1. No module under `skills/*/scripts/` may import from `scripts/` or
   `scripts/hooks/`, directly or by dynamic path load. The dependency arrow
   points inward only.
2. No module under `skills/*/scripts/` may import a non-stdlib package, carry a
   PEP-723 block, or use a shebang other than `#!/usr/bin/env python3`.
3. Internal tooling (`scripts/`, `scripts/hooks/`) uses `uv run --quiet` and a
   PEP-723 block; it may reach inward.
4. Third-party imports are confined to `tests/`.

**Microkernel rule (instruction layer):**

1. `SKILL.md` dispatches and never restates a command's behaviour. Behaviour
   lives in `commands/<command>.md`.
2. Every non-`_` file in `commands/` has exactly one row in a SKILL.md command
   table, and every table row has exactly one file.
3. Every `_`-prefixed shared reference is named in `SKILL.md` itself — never
   reachable only via a command file.
4. Content binding every command lives in `_conventions.md`; content binding
   some commands lives in a trigger-loaded protocol whose trigger is stated in
   both `_conventions.md` and `SKILL.md`. A command file never duplicates
   `_conventions.md`.
5. Only the router carries YAML frontmatter; command files carry none.

**Hexagonal rule (PR subsystem):**

 1. A provider module exposes exactly `fetch_comments(target, n)` and
    `fetch_status(target, n)` and nothing else the callers use.
 2. `pr_common` never statically imports a provider; resolution stays behind
    `_PROVIDER_MODULES` + deferred `importlib`.
 3. A new platform is a new `pr_<platform>.py` plus one `_PROVIDER_MODULES`
    entry — no edit to either entry point.
 4. Every field of the shared output shape is present for every platform, empty
    or null where unsupplied, never absent.
 5. `pr_common` holds no delivery mechanism: no argv parsing, no `print` of a
    result, no exit code. Those belong to a driving adapter — `pr_cli.py` for
    the command line, `mcp_server.py` for MCP.
 6. A driving adapter reaches a provider only through `pr_common.provider_for`,
    never by importing `pr_github`/`pr_gitlab`/`pr_bitbucket` directly.

**Repository rule (findings store):**

 1. Store files are read and written only through `findings.py`. A module that
    opens `docs/audit/findings/**` directly is a violation.
 2. IDs are content-hashed by `finding_id()` — never hand-assigned, never reused.
 3. Store mutation goes through `store_lock()`.
 4. `findings.py` reaches `findings_export` only from the `export` handler, so a
    caller importing the store as a library never loads the renderer.

**Shared Kernel rule:**

 1. A rule with more than one consumer lives in exactly one shared module
    (`md_fences`, `pr_common`, `_hooklib`, `common`). A second implementation of
    a shared rule is a violation, not a convenience.

**Plugin rule:**

 1. Extension units (`skills/<skill>/`, `.claude/skills/<skill>/`) do not import
    one another.
 2. The version is one value across `package.json`, `.claude-plugin/plugin.json`,
    `.claude-plugin/marketplace.json`, `.release-please-manifest.json`,
    `pyproject.toml` and `uv.lock`.

**Visibility rule:**

 1. Every module load resolves statically. A `spec_from_file_location` whose
    target cannot be determined — a computed path outside the module's own
    directory, a name assigned twice in one scope — fails `make ring-deps`
    rather than being passed over, because an unresolved load is a hidden edge
    and a hidden edge is how a ring violation gets in.

## Ambiguities and Contradictions

Five were found on the first pass. **Two were wrong** — recorded here with the
correction, because a retracted finding that leaves no trace gets re-filed by
the next run. Three were real and have been fixed; what remains is below them.

### Corrected — not defects

**The repository does not import its own renderer.** The first pass reported
`findings.py` → `findings_export.py` as a core-depends-on-presentation edge. It
does not exist: the import sits *inside* the `export` subcommand handler
(`findings.py:1959`), with a comment giving that exact reason — "`mcp_server`
imports it as a library and the PostToolUse hook shells out to it … pointing the
core at its own adapter made every one of those callers pay for the renderer".
The original scan walked function bodies and conflated a deferred import with a
module-level one. `make ring-deps` now distinguishes them.

**Hooks do not load their validators by path.** The first pass listed
`scripts/hooks/*` among the string-path importers. They use `subprocess`
(`validate-audit-findings-hook.py:79,99,119`). A process boundary is not an
import edge, is legitimately absent from a dependency graph, and cannot carry a
ring violation. The real string-path importers are three files, not four.

### Fixed

**The port module no longer carries a delivery mechanism.** `run_cli`,
`parse_cli_args`, `_split_flags` and `emit` moved to `pr_cli.py`; `pr_common`
keeps the port and gained `looks_like_pr_url` so the adapter need not reach for
a private regex. `pr_common` is imported by all three providers and by
`mcp_server.py`, none of which run as a CLI, and its docstring's claim to be "a
library, not a CLI" is now true.

**Cross-ring edges are no longer invisible.** `scripts/check-ring-deps.py`
resolves `spec_from_file_location` loads into the graph and prints them beside
ordinary imports, marked. It resolves through a variable binding (every real
case here assigns the path first) and scopes that resolution per function
(`mcp_server` binds `path` in two different functions; a module-flat scan
resolves neither). A load it cannot resolve is an error, not silence. The two
cross-ring string-path edges it recovers —
`scripts/common.py → skills/nitpicker/scripts/findings.py` and
`scripts/validate-rules.py → skills/nitpicker/scripts/check-rules-anatomy.py` —
are pinned by test, so the tool cannot quietly stop resolving them.

**Aliases are validated.** `table_aliases` and `_alias_errors`
(`scripts/validate-skill.py:530,551`) reject an alias that is also a command
name, one claimed by two commands, one listed twice, and one that aliases
itself. 31 aliases across 28 commands now pass a check rather than a reading.

**`check-context-tokens.py` was correctly placed; the prose was wrong.**
`commands/agent-rules.md:151` invokes it, so it is a shipped tool a shipped
command runs. SKILL.md described it as printing "a table for a person
maintaining the skill", which explained its CLI-only status by the wrong
property. Corrected to name the actual reason: its output is an estimate read
as-is, with no pass/fail for a tool to return.

### Still open

**`graphify-out/` is not an architecture source.** Asked "what is the overall
architecture", the knowledge graph returns `.claude-plugin/plugin.json` keyword
nodes — it has indexed manifest strings as architectural concepts, and surfaced
none of the patterns above. This is not a defect in this repo's architecture and
nothing here fixes it; `graphify` is vendored (`.claude/rules/vendored-skills.md`)
and its index is generated. Use `graphify query` as a locator, and read the
dependency graph from `make ring-deps` instead.

## Confidence

Overall: **High.** Every pattern claim above rests on a verified structural
signal — an import edge from the full AST-parsed graph, an enforced validator
line, or a directory/naming scan with its negative result stated. The one
Low-confidence entry (append-only ledger) is labelled as partial and explained.

Two first-pass findings did not survive re-reading the source and are recorded
as corrections rather than deleted. Both had the same cause: an AST walk that
descended into function bodies, so a deliberately deferred import read as a
module-level dependency. `make ring-deps` now separates the two, which is why
that distinction is a gate and not a habit.
