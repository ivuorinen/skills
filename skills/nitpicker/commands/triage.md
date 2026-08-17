# /nitpicker triage — Audit Command Selector

Scans a repo (or the changed files) and emits a ranked run-plan of which
nitpicker commands to run, each justified by a cited repo signal. This is a
selector, not an auditor: it recommends commands, files no findings, and runs
nothing itself.

## When to use

- Starting an audit on an unfamiliar repo and choosing which commands are
  worth running
- "which nitpicker commands should I run", "what should I audit here",
  "triage this repo", "where do I start", "scope the audit"
- Before a release gate, to run the relevant subset instead of all of them or
  the catch-all `audit`

Like `arch-profile` and `teach`, this command overrides the **Findings store**
section of `_conventions.md` in full — no findings are filed, no store is
touched, the deliverable is the run-plan on stdout. Two `_conventions.md` rules
carry over: run the Process below as a task list (one tracker entry per step),
and preflight any external tool with `command -v` before invoking it.

## The three buckets — evidence or it is not recommended

Every public command in the `## Commands` table of `SKILL.md` (the **full
set**) lands in exactly one bucket, and each bucket demands proof. Enumerate
that set with `np_list_commands` when the session exposes it, else read the
table from `SKILL.md`; it parses every command table, so drop every row whose
`category` is `Internal commands` — triage never recommends an internal
command. Each row's `category` is the grouping to report in. The tool's
`category` argument narrows the listing, so it never substitutes for the sweep:
this command places the full set on every run, and a category named in the
extra instructions orders the output, never shortens it:

- **Recommended** — a trigger condition is present, cited with the concrete
  signal (a file, directory, dependency, config key, or code construct) at
  `file:path`. No citation, no recommendation.
- **Not applicable** — the trigger is provably absent **across the whole
  repository**, stated as an exhaustive negative (`no *.tsx/JSX/template files
  anywhere → a11y N/A`). Under the **changed-files** modifier the sweep sees
  only part of the tree, so it cannot assert a repo-wide negative: a command
  whose trigger is absent from the changed set but not disproven elsewhere is
  **Unprovable**, never Not applicable.
- **Unprovable** — the trigger cannot be settled from what was inspected: it is
  off-repo (a running service's alert wiring), or — under `changed-files` — a
  repo-wide trigger the narrowed sweep never covered. Named explicitly, never
  folded into the other two buckets.

A command that appears in no bucket is a coverage gap: the run-plan is
incomplete until every command in the full set is placed by name. Silence
means approval — an unplaced command is an unaudited decision.

## Selection rules

- **A trigger is present or absent on its own evidence — never on another
  tool's coverage.** "`make check` already runs ruff/pyright/pytest" does not
  make `security`, `tests`, or `types` Not-applicable: their triggers are the
  presence of the audited surface (code that executes, a test suite, typed
  source), not the absence of a gate. Note the overlap on the command's line;
  keep the command Recommended.
- **The recommended count is the number of distinct commands with at least one
  fired trigger — never a raw tally of signals, never a quota.** One command may
  fire several signals; it stays one recommendation, with every signal kept on
  its line. Not "a handful", not "the top five", not a number trimmed to fit a
  deadline or an instruction to pick a few. If 12 commands fire a trigger,
  recommend 12; if 2 fire, recommend 2. A request to cap the list is recorded in
  the output and refused.
- **`audit` is never a fallback.** It is the dump this command exists to
  replace. Recommend `audit` only when the ask is explicitly "run everything";
  never offer it as a safety net for a low-confidence triage. Low confidence on
  one command is a note on that command's line, never a repo-wide escalation.
  Its line in **Not applicable** is its only mention: never volunteer the
  `audit` pathway again in a closing note or summary — restating "the one case
  for `audit` is…" re-surfaces the dump the run-plan just refused.
- **Recommend only; never run.** Per the router rule, this command never chains
  into the commands it recommends — the user runs them.

## Sort key — total order for the Recommended bucket

Rank Recommended commands by these keys in strict order, each key breaking the
prior key's ties, down to a total order:

1. **Trigger strength: High before Medium before Low.** High = an unambiguous
   signal (a security-scanner config, a `migrations/` dir, JSX files). Medium =
   a plausible but partial signal. Low = a single weak signal.
2. **Severity ceiling: Critical-capable before High-only before lower.** Read
   the target command's own severity guidance; a command that can file Critical
   (e.g. `security`, `concurrency`, `migrations`, `reliability`) outranks one
   that cannot (e.g. `docs`, `commits`, `contributing`). A generative or meta
   command that files no findings (`plan`, `execute-plan`, `teach`,
   `arch-profile`, `baseline`, `release-gate`, `help`) has no ceiling — it
   ranks below every finding-filing command in this key, separated from other
   ceiling-less commands only by key 3.
3. **Command name, ASCII ascending.** Final tie-break — guarantees two runs on
   the same repo produce the identical order.

Print the key values on each line so the order is reproducible, not asserted.

## Process

1. **Sweep the surface once.** Inventory languages, top-level directories,
   manifests, config files, CI workflows, UI/template files, DB/migration
   dirs, LLM integration, infra-as-code, and any `.claude/` enforcement.
   Record `file:path` evidence for each surface found. With the
   **changed-files** modifier, sweep only the changed files and their direct
   dependencies, and say so in the output scope line. Absence observed in that
   narrowed sweep proves only scope-local absence — route any command whose
   repo-wide trigger the sweep could not cover to Unprovable, never Not
   applicable.
2. **Place every command.** Take each command's trigger from its row in the
   `## Commands` table of `SKILL.md` (the `purpose` field of
   `np_list_commands`), dropping to that command's own file and its
   `## When to use` only to resolve an ambiguous trigger — `np_read_command`
   when available, else a direct read. Put every command
   in the full set into Recommended, Not applicable, or Unprovable with its
   cited evidence or exhaustive negative. An unplaced command fails the run.
3. **Rank** the Recommended bucket by the total-order sort key; annotate each
   line with its key values.
4. **Emit the run-plan** (below). File nothing. Auto-run nothing.

## Output

Print to stdout:

```markdown
# Audit Triage — <repo> (<date>)
Scope: <whole repo | changed-files: N files>

## Run these, in order
1. /nitpicker <cmd>  [trigger: High, ceiling: Critical] — <cited signal at file:path>
2. /nitpicker <cmd>  [trigger: Medium, ceiling: High] — <cited signal at file:path>

## Not applicable (trigger proven absent)
- <cmd> — <exhaustive negative>
  (every non-recommended, provable command; all accounted for by name)

## Unprovable from this repo
- <cmd> — <the off-repo trigger that cannot be checked here>

## Coverage
<total>/<total> commands placed. Recommended: N. Not applicable: M. Unprovable: K.
```

`<total>` is the number of rows in the `## Commands` table of `SKILL.md`, counted
this run — never a memorized constant. Counted from `np_list_commands` it is the
number of returned rows whose `category` is not `Internal commands`. Recommended + Not applicable + Unprovable
must equal it. If they do not, the triage is incomplete — placing every command
is the deliverable, never a subset. Close with: this command recommends only;
run the listed commands yourself in the order given.

## Common mistakes

- **"A gate already runs ruff/pytest/pyright, so security/tests/types are
  covered — drop them."** A running linter is not an audit of that dimension.
  Those triggers are the presence of the audited surface, not the absence of a
  gate. Note the overlap, keep the command Recommended.
- **"The user asked for a handful, so stop at five."** The recommended count is
  the number of distinct commands with a fired trigger — never a quota set by a
  deadline, a mood, or an instruction to pick a few. Refuse the cap and record
  that it was asked.
- **"The order is obvious — highest signal first."** Obvious is not
  reproducible. Rank by the total-order sort key and print the key values, or
  two runs disagree.
- **"I listed the big skips; the rest are obviously N/A."** Every command in
  the full set is placed by name with a reason. "The rest" is a silent drop;
  the Coverage counts must sum to the table's row count.
- **"If unsure, just tell them to run audit."** `audit` is the dump this
  command replaces. Low confidence on a command is a note on that command's
  line, never a repo-wide escalation to the everything-option.
- **"I refused the dump, but I'll close by noting when audit would apply."**
  That closing courtesy re-surfaces the dump. `audit`'s Not-applicable line is
  its only mention unless the ask is explicitly "run everything".
