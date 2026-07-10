# /nitpicker agent-hooks — Hooks Enforcer

Hostile audit of a project's hook _coverage_ against its own evidence base: assume every recurring failure is unguarded until a hook is proven to fire on it, specify the missing hook in the host harness's correct shape, and on approval wire it and fire it on the evidence input to prove it binds.

## When to use

- Auditing which agent hooks a project should enforce given its history of recurring defects
- A pattern of repeated fixes, reverts, or audit findings keeps recurring with no automated guard
- When asked to "enforce hooks", "harden hook coverage", "add the hooks we keep needing", "make sure context-mode is used where it should be", or "stop large command output from bloating the context window"
- Before a release, to prove every evidence-backed, hook-preventable failure class is guarded
- Run standalone or by the `/nitpicker` default audit flow

Not for checking whether an _existing_ hook, rule, or permission can be evaded — that is `/nitpicker agent-loopholes`. Not for rule quality and placement — that is `/nitpicker agent-rules`. Not for application-source security — that is `/nitpicker security`.

`/nitpicker agent-loopholes` audits the existing enforcement surface for _evasion_; this command audits the evidence base for _absence_ — a recurring failure with no hook at all, a hook shaped for the wrong harness, or large-output work not routed through a context-saving tool. Never re-file loopholes classes (fail-open, matcher-gap, permission-contradiction) here. `wrong-event` and `harness-mismatch` may touch an existing hook, but on the axis loopholes does not analyze — event capability and harness fit; when such a hook also reads as a warn-only/fail-open loophole, file it once, here, with the harness-correct event/shape fix.

## Harness detection

Detect the host agent harness first; it dictates the enforcement mechanism and the best-practice ruleset. A hook written for the wrong harness enforces nothing.

| Signal present                                                                                       | Harness        | Mechanism + best-practice source                                                                                             |
| ---------------------------------------------------------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `.claude/settings.json` or `.claude/settings.local.json` with a `hooks` key, or `.claude/` directory | Claude Code    | `hooks` in `.claude/settings.json`; follow https://code.claude.com/docs/en/hooks-guide                                       |
| `.github/copilot-instructions.md` and no `.claude/` hooks                                            | GitHub Copilot | Copilot's own configuration/instruction mechanism and its documented best practices — never write Claude Code hook JSON here |
| `AGENTS.md` / `GEMINI.md` / other harness marker                                                     | That harness   | That harness's documented hook/automation mechanism and best practices                                                       |

A project may run more than one harness. Audit each detected harness against its own mechanism and record the detected harness(es) in the summary. For a non-Claude-Code harness, fetch and follow its published guidance and state which document you used.

### Claude Code hook best practices (binding on every proposed Claude Code hook)

- **Pick the event by capability.** Only blocking-capable events block. `PreToolUse` blocks a tool call via `hookSpecificOutput.permissionDecision` (`deny`/`ask`); `UserPromptSubmit` and `Stop` block via exit code 2. `PostToolUse` **cannot** block — it only feeds `stderr`/`additionalContext` back after the tool already ran. A hook whose intent is to _prevent_ an action must use a blocking-capable event.
- **Fail closed.** Exit non-zero (or emit the deny decision) on the violating input, on malformed input, and on the hook's own internal error. A hook that exits 0 on exception enforces nothing.
- **Validate and quote.** Validate/sanitize stdin, quote every shell variable (`"$VAR"`), reject `..` path traversal, use absolute paths via `${CLAUDE_PROJECT_DIR}`, and skip sensitive files (`.env`, `.git/`, keys).
- **Match the real input class.** The `matcher` must cover every tool and path form the intent claims to govern — extension variants, renames, new vs. edited files.
- **Hooks obey context-discipline too.** A hook that itself gathers or parses large output must route that work through the context-saving tool or keep its own output minimal.

## Evidence base

Mine all of these every run. Never sample, and never substitute "the current hooks look fine" for mining the evidence.

| Source                         | What to extract                                                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Current hooks                  | Every hook entry in `.claude/settings.json` and `.claude/settings.local.json` — event, matcher, command — and every hook script under any hooks directory (`scripts/hooks/`, `.claude/hooks/`) whether wired or not                                                                                                                                                                                        |
| Available context-saving tools | Every installed plugin/MCP/CLI that executes a shell command or fetch and returns only a derived result rather than raw bytes to the conversation (context-mode `ctx_execute`/`ctx_execute_file`/`ctx_batch_execute`/`ctx_fetch_and_index` is the reference implementation). Record every candidate considered, including rejects and why; the routing findings below require at least one qualifying tool |
| Findings history               | Every finding in the store (`findings.py list`, all auditors and statuses) plus any legacy `docs/audit/*-findings.md` files. A defect class that recurs — or that a fixed entry shows was hand-fixed — is a recurring, hook-preventable candidate                                                                                                                                                          |
| Git history                    | Repeated fix/revert commits touching the same concern (`git log` for `fix:`/`revert` clusters on one file or rule). A recurring manual fix is a missing automated guard                                                                                                                                                                                                                                    |
| Project memory                 | Every `feedback`/`project` memory entry under the project memory directory that implies an automated guard the user expects. Absent memory is one empty source, recorded as empty — not a reason to skip the run                                                                                                                                                                                           |
| Project mandates               | Every `.claude/rules/` mandate and CLAUDE.md convention. Flag only those with no hook AND an automatable shape — the violation is detectable by inspecting a file path, a file's text, or a tool name on stdin without running the project; do not re-file the loopholes unenforced-rule evasion analysis                                                                                                  |

Discover hook script paths from the settings wiring and the hooks directories, not from a hardcoded list.

## The must-run-direct allowlist

A `Bash` (or `Read`) invocation is **exempt** from context routing only when it is on this allowlist. Everything else that _gathers_ or _processes_ output belongs on a context-saving tool, and a project that routes such work through raw `Bash` with no hook redirecting it has a context-discipline gap.

Exempt (may run direct):

- State mutation: `git` commits/branches/merges, package installs, `mkdir`/`mv`/`rm`, file writes, migrations
- Build/test/lint runners whose pass/fail is the signal: `npm test`, `uv run pytest`, `make check`, compilers, servers
- Short fixed-output OBSERVE: `pwd`, `whoami`, `git status` on a clean tree, a one-line version check
- Interactive or stateful commands: logins, port-binding servers, anything holding a lock

Not exempt (route through the context tool): reading/summarizing/parsing files, `git log`/`git diff`, dependency-tree/coverage/log analysis, API responses, codebase statistics, doc fetches, and any read/gather/parse command (`grep`/`cat`/`find`/`ls -R`, or a pipeline feeding `head`/`tail`/`wc`) whose result will be analyzed rather than acted on. Classify by the command verb, not by output size — a `PreToolUse` hook decides before the command runs and cannot know output length.

## Required-hook classes

File a finding only with concrete evidence drawn from the evidence base. Each class names what _should_ be a hook and is not.

| Class                      | Definition                                                                                                                                                                                                                                                                                                    | Evidence to construct                                                                           |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **coverage-gap**           | A defect class recurring across two or more findings-history entries or git fix-commits, with no hook that would catch it on the path it recurs                                                                                                                                                               | The two-or-more occurrences and the hook (event + matcher + check) that would have blocked each |
| **context-discipline-gap** | A read/gather/process command that appears as a **mandated step in a project skill or workflow file**, routed through raw `Bash`/`Read` where a context-saving tool exists, with no hook redirecting it                                                                                                       | The exact step and file, the available `ctx_*` equivalent, and the absence of a routing hook    |
| **over-permissioned-bash** | A `Bash` pattern **permitted by a `permissions.allow` entry** (not a mandated workflow step), not on the must-run-direct allowlist, that could route through the context tool and is left unconstrained. If a command is both a mandated step and permission-allowed, file context-discipline-gap, never both | The allow entry, why it is not allowlist-exempt, and the narrowing hook/permission              |
| **wrong-event**            | An existing or proposed hook whose event cannot achieve its stated intent (e.g. a `PostToolUse` hook meant to _block_)                                                                                                                                                                                        | The intent, the chosen event's incapacity, and the blocking-capable event it must use           |
| **harness-mismatch**       | A hook shaped for the wrong harness, or a mandate expressed as prose where the detected harness supports an actual hook                                                                                                                                                                                       | The harness signal vs. the hook shape, and the correct mechanism                                |
| **unguarded-mandate**      | A project mandate with an automatable shape and no hook, that recurs in the evidence base                                                                                                                                                                                                                     | The mandate, the recurrence, and the exact hook that would enforce it                           |

## Process

1. Detect the harness(es) and record the best-practice source each proposed hook
   will be held to. If a harness is unknown, fetch its hook/automation docs
   before proposing any hook for it.
2. Inventory current enforcement: every hook wiring, every hook script (wired or
   dead), every available context-saving tool. Record counts.
3. Mine the evidence base. Read every source in the table in full and build the
   recurrence ledger: each candidate failure class, where it recurs (cite the
   entries/commits/memory), and whether any hook guards it. An unmined source
   forces run verdict INCOMPLETE — name it in the summary.
4. Audit context-discipline. Enumerate the Bash/Read usage the project's own
   skills and workflows mandate or perform; classify each against the allowlist
   as exempt or should-route. For every should-route case, confirm whether a
   routing hook (PreToolUse, for Claude Code) enforces the redirect. If no
   context-saving tool exists in the project, record that and file no routing
   findings.
5. File findings via the store protocol in `_conventions.md`, using
   `--auditor agent-hooks`. Each finding records the class, the evidence (the
   recurrence or the bloating command), and the exact hook — event, matcher,
   command, fail-closed shape — in the detected harness's format.
6. Present the summary with the run verdict (COMPLETE only if every evidence
   source was mined and every should-route case classified) and the detected
   harness(es), then follow the apply-fixes prompt from `_conventions.md`. For
   this command, `(s)afe` means: only wire an existing-but-dead hook script into
   settings and correct a wrong-event hook to its blocking-capable event — no
   brand-new hook, no new rule, no permission change. After each fix, prove
   enforcement per Proving Enforcement. Fix edits to tracked files stay unstaged.

## Proving enforcement

A proposed hook is "enforced" only after it is wired and fired on the evidence input and observed to behave as intended. A described hook is an open finding, never fixed.

- **Blocking hook** (PreToolUse deny/ask; UserPromptSubmit/Stop exit 2): feed the evidence input to the hook script on stdin and show it emits the deny decision / exits non-zero.
- **Feedback hook** (PostToolUse): feed the evidence input and show it writes the intended `stderr`/`additionalContext`. If the intent was to _block_, PostToolUse is wrong by definition — refile as wrong-event, do not mark fixed.
- **Routing hook** (context-discipline): feed the should-route command to the wired PreToolUse hook and show it emits `permissionDecision: deny` with a message naming the `ctx_*` tool to use instead — the redirect is the agent's response to the deny, not a hook output. Feed an allowlist-exempt command and show it is allowed.
- **Wiring-only fix**: confirm the settings command path resolves to a script that exists and the matcher fires on the target input.

## Severity guide

| Severity | Condition                                                                                                                                                                                                                    |
| -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Critical | A safety/release-gate failure class recurs and is wholly unguarded — every release can reintroduce it; or a block-intent hook uses a non-blocking event so the guard never binds                                             |
| High     | A defect class recurs across the evidence base with no hook; a context-discipline-gap (a mandated should-route step) with a context tool available and no routing hook; a hook shaped for the wrong harness so it never runs |
| Medium   | A single-occurrence automatable mandate with no hook; an over-permissioned-bash pattern that could route through the context tool                                                                                            |
| Low      | Redundant or near-duplicate proposed coverage; a routing gap on a command whose result is trivially small (a single value or one line)                                                                                       |
| Advisory | Defense-in-depth hook opportunity where no failure has yet recurred                                                                                                                                                          |

## Fix strategy

**Auto-applicable (ask first, apply only on approval):**

- Wire an existing-but-dead hook script into the detected harness's settings
- Correct a wrong-event hook to its blocking-capable event (PostToolUse→PreToolUse for block-intent)
- Add a fail-closed wrapper to a proposed hook so it exits non-zero on error/unexpected input

**Requires explicit approval per change:**

- Adding a brand-new enforcement hook and its script
- Adding a PreToolUse Bash-deny/routing hook that changes day-to-day tool behavior
- Narrowing a `permissions.allow` Bash entry
- Adding a new rule to back a proposed hook

**Never auto-apply:**

- Writing Claude Code hook JSON into a non-Claude harness, or vice versa
- Weakening, disabling, or removing any existing enforcement to resolve a finding
- Editing `.claude/settings.local.json` (gitignored, machine-specific) — propose it and let the user apply
- Marking a finding fixed without firing the wired hook on its evidence input

## Common mistakes

- **"The existing hooks look comprehensive, so no new ones are needed."** Coverage is measured against the evidence base, not against how the current set looks. Mine every source before judging coverage.
- **"I'll read settings.json and skip the findings history, git, and memory."** The evidence base is the input to this command; skipping it is skipping the command. An unmined source forces verdict INCOMPLETE.
- **"Memory doesn't exist, so the run is not applicable."** Absent memory is one empty source, recorded as empty. The run still runs.
- **"context-mode is a nice-to-have, I won't enforce routing."** Where a context-saving tool exists and a workflow routes large output through raw `Bash`/`Read`, that is a filed context-discipline-gap. Only the must-run-direct allowlist is exempt.
- **"It's Claude Code, so I'll ignore the other harness."** Detect first; hold every proposed hook to its harness's mechanism. A hook in the wrong harness's format is a harness-mismatch finding against your own proposal.
- **"PostToolUse can block the bad call."** It cannot; the tool already ran. Blocking enforcement uses PreToolUse (deny/ask) or an exit-2 event.
- **"I'll enforce the rule with a quick Bash one-liner in the hook."** A hook that gathers or parses large output must itself obey context-discipline and must fail closed. An unquoted, fail-open one-liner reintroduces the gap it was meant to close.
- **"Re-firing the evidence input to prove the hook fires is overkill."** Unfired is unproven, and unproven is open. Proof is the deny decision or non-zero exit on the exact input.
- **"This is the loopholes command's job."** `/nitpicker agent-loopholes` audits existing constraints for evasion; absence and routing are this command's surface. Do not defer here, and do not re-file its fail-open/matcher-gap classes.
