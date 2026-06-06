---
name: hooks-enforcer
description: Audits an agent project's hook coverage against its own evidence base — current hooks, audit-findings history, git history, and project memory — surfacing recurring failures that no hook guards and context-discipline gaps where large-output work bypasses a context-saving tool. Use when auditing which agent hooks a project should enforce, when asked to "enforce hooks", "harden hook coverage", or "make sure context-mode is used", and when invoked by nitpicker in loophole mode or by release-prep as a release gate.
---

# Hooks Enforcer

## Overview

Hostile audit of a project's *hook coverage*. It assumes every recurring failure is unguarded until a hook is proven to fire on it. It mines the project's own evidence base — current hook wiring, every `docs/audit/*-findings.md` pass, git history, and project memory — to find failure classes that recur and that a hook could have caught, then specifies the exact hook (event, matcher, command, fail-closed shape) in the host harness's correct format and, on approval, wires it and fires it on the evidence input to prove it now binds. It additionally enforces context-discipline: where a context-saving tool (e.g. context-mode's `ctx_*` tools) can do read/gather/process work off-context, raw `Bash`/`Read` that bloats the context window must be routed through it; only operations on the must-run-direct allowlist stay on `Bash`. Single-shot: re-validate existing findings, detect the harness, inventory current enforcement, mine the evidence base, file findings, optionally wire and prove, re-validate.

This is not `loophole-hunter`. That skill audits the *existing* enforcement surface for *evasion* — a constraint that can be bypassed. This skill audits the *evidence base* for *absence* — a recurring failure that has no hook at all, a hook shaped for the wrong harness, or large-output work that should be routed through a context-saving tool and is not. loophole-hunter asks "can this constraint be evaded?"; hooks-enforcer asks "what should be a hook and is not?" It never re-files loophole-hunter's classes (fail-open, matcher-gap, permission-contradiction); when an existing hook can be evaded, that belongs to loophole-hunter. `wrong-event` and `harness-mismatch` may touch an existing hook, but on the axis loophole-hunter does not analyze — event capability and harness fit; when such a hook also reads as a loophole-hunter warn-only/fail-open finding, file it once, here, with the harness-correct event/shape fix.

## When to Use

- Auditing which agent hooks a project should enforce given its history of recurring defects
- A pattern of repeated fixes, reverts, or audit findings keeps recurring with no automated guard
- When asked to "enforce hooks", "harden hook coverage", "add the hooks we keep needing", "make sure context-mode is used where it should be", or "stop large command output from bloating the context window"
- Before a release, to prove every evidence-backed, hook-preventable failure class is guarded
- Invoked by `nitpicker` in `loophole` mode, or by `release-prep` as a release gate

**When NOT to use:** To check whether an *existing* hook, rule, or permission can be bypassed, use `loophole-hunter`. For rule *quality and placement*, use `claude-rules-auditor`. For application-source security, use `security-auditor`.

## Harness Detection

Detect the host agent harness first; it dictates the enforcement mechanism and the best-practice ruleset. A hook written for the wrong harness enforces nothing.

| Signal present | Harness | Mechanism + best-practice source |
|----------------|---------|----------------------------------|
| `.claude/settings.json` or `.claude/settings.local.json` with a `hooks` key, or `.claude/` directory | Claude Code | `hooks` in `.claude/settings.json`; follow https://code.claude.com/docs/en/hooks-guide |
| `.github/copilot-instructions.md` and no `.claude/` hooks | GitHub Copilot | Copilot's own configuration/instruction mechanism and its documented best practices — never write Claude Code hook JSON here |
| `AGENTS.md` / `GEMINI.md` / other harness marker | That harness | That harness's documented hook/automation mechanism and best practices |

A project may run more than one harness. Audit each detected harness against its own mechanism. Record the detected harness(es) in the findings Summary. When the harness is Claude Code, every proposed hook must conform to the Claude Code Hook Best Practices below; for any other harness, fetch and follow that harness's published guidance and state which document you used.

### Claude Code Hook Best Practices (binding on every proposed Claude Code hook)

- **Pick the event by capability.** Only blocking-capable events block. `PreToolUse` blocks a tool call via `hookSpecificOutput.permissionDecision` (`deny`/`ask`); `UserPromptSubmit` and `Stop` block via exit code 2. `PostToolUse` **cannot** block — it only feeds `stderr`/`additionalContext` back after the tool already ran. A hook whose intent is to *prevent* an action must use a blocking-capable event.
- **Fail closed.** Exit non-zero (or emit the deny decision) on the violating input, on malformed input, and on the hook's own internal error. A hook that exits 0 on exception enforces nothing.
- **Validate and quote.** Validate/sanitize stdin, quote every shell variable (`"$VAR"`), reject `..` path traversal, use absolute paths via `${CLAUDE_PROJECT_DIR}`, and skip sensitive files (`.env`, `.git/`, keys).
- **Match the real input class.** The `matcher` must cover every tool and path form the intent claims to govern — extension variants, renames, new vs. edited files.
- **Hooks obey context-discipline too.** A hook that itself gathers or parses large output must route that work through the context-saving tool or keep its own output minimal; do not introduce a hook that re-bloats context.

## Evidence Base

Mine all of these every run. Never sample, and never substitute "the current hooks look fine" for mining the evidence.

| Source | What to extract |
|--------|-----------------|
| Current hooks | Every hook entry in `.claude/settings.json` and `.claude/settings.local.json` — event, matcher, command — and every hook script under any hooks directory (`scripts/hooks/`, `.claude/hooks/`) whether wired or not |
| Available context-saving tools | Every installed plugin/MCP/CLI that executes a shell command or fetch and returns only a derived/queried result rather than raw bytes to the conversation (context-mode `ctx_execute`/`ctx_execute_file`/`ctx_batch_execute`/`ctx_fetch_and_index` is the reference implementation). Record every candidate considered, including any rejected and why, in the Summary `context-tools N` count; the routing findings below require at least one qualifying tool |
| Audit-findings history | Every `docs/audit/*-findings.md` file, all passes (Open, Fixed, Invalid). A defect class that appears in two or more passes — or that a Fixed entry shows was hand-fixed — is a recurring, hook-preventable candidate |
| Git history | Repeated fix/revert commits touching the same concern (`git log` for `fix:`/`revert` clusters on one file or rule). A recurring manual fix is a missing automated guard |
| Project memory | Every `feedback`/`project` memory entry under the project memory directory that implies an automated guard the user expects. Absent memory is one empty source, recorded as empty — not a reason to skip the run |
| Project mandates | Every `.claude/rules/` mandate and CLAUDE.md convention. Flag only those with no hook AND an automatable shape — the violation is detectable by inspecting a file path, a file's text, or a tool name on stdin without running the project; do not re-file loophole-hunter's unenforced-rule evasion analysis |

Discover hook script paths from the settings wiring and the hooks directories, not from a hardcoded list — the wiring plus the directory together are the source of truth for what runs and what is dead.

## The Must-Run-Direct Allowlist

A `Bash` (or `Read`) invocation is **exempt** from context routing only when it is on this allowlist. Everything else that *gathers* or *processes* output belongs on a context-saving tool, and a project that routes such work through raw `Bash` with no hook redirecting it has a context-discipline gap.

Exempt (may run direct):
- State mutation: `git` commits/branches/merges, package installs, `mkdir`/`mv`/`rm`, file writes, migrations
- Build/test/lint runners whose pass/fail is the signal: `npm test`, `uv run pytest`, `make check`, compilers, servers
- Short fixed-output OBSERVE: `pwd`, `whoami`, `git status` on a clean tree, a one-line version check
- Interactive or stateful commands: logins, port-binding servers, anything holding a lock

Not exempt (route through the context tool): reading/summarizing/parsing files, `git log`/`git diff`, dependency-tree/coverage/log analysis, API responses, codebase statistics, doc fetches, and any read/gather/parse command (`grep`/`cat`/`find`/`ls -R`, or a pipeline feeding `head`/`tail`/`wc`) whose result will be analyzed rather than acted on. Classify by the command verb, not by output size — a `PreToolUse` hook decides before the command runs and cannot know output length.

## Required-Hook Classes

File a finding only with concrete evidence drawn from the evidence base. Each class names what *should* be a hook and is not.

| Class | Definition | Evidence to construct |
|-------|------------|------------------------|
| **coverage-gap** | A defect class recurring across two or more findings passes, Fixed entries, or git fix-commits, with no hook that would catch it on the path it recurs | The two-or-more occurrences and the hook (event + matcher + check) that would have blocked each |
| **context-discipline-gap** | A read/gather/process command that appears as a **mandated step in a project skill or workflow file**, routed through raw `Bash`/`Read` where a context-saving tool exists, with no hook redirecting it | The exact step and file, the available `ctx_*` equivalent, and the absence of a routing hook |
| **over-permissioned-bash** | A `Bash` pattern **permitted by a `permissions.allow` entry** (not a mandated workflow step), not on the must-run-direct allowlist, that could route through the context tool and is left unconstrained. If a command is both a mandated step and permission-allowed, file context-discipline-gap, never both | The allow entry, why it is not allowlist-exempt, and the narrowing hook/permission |
| **wrong-event** | An existing or proposed hook whose event cannot achieve its stated intent (e.g. a `PostToolUse` hook meant to *block*) | The intent, the chosen event's incapacity, and the blocking-capable event it must use |
| **harness-mismatch** | A hook shaped for the wrong harness, or a mandate expressed as prose where the detected harness supports an actual hook | The harness signal vs. the hook shape, and the correct mechanism |
| **unguarded-mandate** | A project mandate (rule/convention) with an automatable shape (detectable by inspecting a file path, a file's text, or a tool name on stdin without running the project) and no hook, that recurs in the evidence base | The mandate, the recurrence, and the exact hook that would enforce it |

## Process

```
0. Re-validate existing findings
   If docs/audit/hooks-enforcer-findings.md exists, re-validate each finding with
   Status: Open:
   - Hook now wired and fires on the evidence input → move to Fixed (record date)
   - Finding was wrong (the failure does not recur, or a hook already guards it) → Invalid
   - Still unguarded → leave Open

1. Detect the harness(es)
   Apply Harness Detection. Record every detected harness and the best-practice source
   you will hold each proposed hook to. If a harness is unknown, fetch its hook/automation
   docs before proposing any hook for it.

2. Inventory current enforcement
   List every hook wiring, every hook script (wired or dead), and every available
   context-saving tool. Record counts. This inventory is half the coverage checklist.

3. Mine the evidence base
   Read every source in the Evidence Base table in full. Build the recurrence ledger:
   each candidate failure class, where it recurs (cite the passes/commits/memory entries),
   and whether any hook guards it. An unmined source is an unfiled coverage gap; record
   any source you could not mine as an Unexamined Summary bullet and set verdict INCOMPLETE.

4. Audit context-discipline
   Enumerate the Bash/Read usage the project's own skills and workflows mandate or perform.
   Classify each against the Must-Run-Direct Allowlist: exempt, or should-route. For every
   should-route case, confirm whether a routing hook (PreToolUse, for Claude Code) enforces
   the redirect. An unconstrained should-route case with an available context tool is a
   context-discipline-gap (or over-permissioned-bash). If no context-saving tool exists in
   the project, record that and file no routing findings.

5. File findings
   For each gap, assign the next HE-NNN id and record class, evidence (the recurrence or the
   bloating command), impact, and the exact hook — event, matcher, command, and fail-closed
   shape — in the detected harness's format. No finding without evidence from the base and a
   concrete, harness-correct hook specification.

6. Write docs/audit/hooks-enforcer-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

7. Present summary — state the run verdict (COMPLETE only if every evidence source was mined
   and every should-route case classified) and the detected harness(es) — then ask:
   "Wire hooks? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   - `(a)ll` / `(c)ritical-and-high only`: apply the matching Auto-applicable fixes.
   - `(s)afe`: only wire an existing-but-dead hook script into settings and correct a
     wrong-event hook to its blocking-capable event. Add no brand-new hook, no new rule,
     no permission change.
   Apply in severity order (Critical first). After each, prove enforcement per "Proving
   Enforcement"; a hook is not enforced until proven. Move proven findings to Fixed.
   When invoked as a release gate (by release-prep, or by nitpicker in release-gate mode), do
   not auto-answer the prompt: report the verdict and every Open Critical/High finding, and
   fail the gate if the verdict is INCOMPLETE or any Open Critical/High finding remains.

8. Commit gate
   Fix edits to tracked files (`.claude/settings.json`, hook scripts) are left in the working
   tree unstaged — never stage or commit them silently. Then ask: "Commit findings to git?
   (y/n)" and, on yes, stage only docs/audit/hooks-enforcer-findings.md.
```

## Proving Enforcement

A proposed hook is "enforced" only after it is wired and fired on the evidence input and observed to behave as intended. A described hook is an Open finding, never Fixed.

- **Blocking hook** (PreToolUse deny/ask; UserPromptSubmit/Stop exit 2): feed the evidence input to the hook script on stdin and show it emits the deny decision / exits non-zero.
- **Feedback hook** (PostToolUse): feed the evidence input and show it writes the intended `stderr`/`additionalContext`. If the intent was to *block*, PostToolUse is wrong by definition — refile as wrong-event, do not mark Fixed.
- **Routing hook** (context-discipline): feed the should-route command to the wired PreToolUse hook and show it emits `permissionDecision: deny` with a message naming the `ctx_*` tool to use instead — the hook denies; the redirect is the agent's response to the deny, not a hook output. Feed an allowlist-exempt command and show it is allowed.
- **Wiring-only fix**: confirm the settings command path resolves to the script that exists and the matcher fires on the target input.

A finding for which enforcement cannot be demonstrated stays Open.

## Findings Format

Output path: `docs/audit/hooks-enforcer-findings.md`

```
# Hooks Enforcer Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N sources/cases unexamined)
- Harness detected: <claude-code|copilot|...> (best-practice source: <url/doc>)
- Evidence mined: hooks N | scripts N | findings-files N | git-clusters N | memory-entries N | context-tools N
- Context-discipline: should-route cases N | guarded N | gaps N
- Open-Unexamined: N
- Unexamined: <source or case> — <why not examined>

## Open Findings

### Critical

#### [HE-NNN] Short title
Status: Open
Class: <coverage-gap|context-discipline-gap|over-permissioned-bash|wrong-event|harness-mismatch|unguarded-mandate>
Harness: <claude-code|copilot|...>
Area: <file path, settings key, or workflow step>
Problem: <the recurring failure or routing gap that no hook guards>
Evidence: <the two-or-more recurrences, or the exact bloating command and its output>
Impact: <what stays unguarded / how much context is wasted>
Fix: <the exact hook — event, matcher, command, fail-closed shape — in the detected harness's format>

### High
[same structure]

### Medium
[same structure]

### Low
[same structure]

### Advisory
[same structure]

## Fixed

### Pass N — YYYY-MM-DD

#### [HE-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <the hook wired, and the firing on the evidence input that now binds>

## Invalid

### Pass N — YYYY-MM-DD

#### [HE-NNN] Short title
Notes: <why the failure does not recur, or which hook already guards it>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and
rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding
entries and re-emits the other `## Summary` bullets after it. Keep the Total line in the
`Total: N | Open: N | Fixed: N | Invalid: N` shape and insert no field between `Total:` and
`Invalid:`; the hook recomputes and rewrites this line from the actual finding counts, so any
value you type into it is overwritten. All supplementary bullets
(`Run verdict`, `Harness detected`, `Evidence mined`, `Context-discipline`, `Open-Unexamined`,
`Unexamined:`) follow the Total line. Unexamined sources live as `Unexamined:` Summary bullets,
never in a separate section. `Open-Unexamined` is not part of the Open/Fixed/Invalid totals.

The per-finding `Status:` field is `Open` for an examined, still-unguarded finding. On moving
a finding to Fixed or Invalid, drop the `Status:` line; only Open findings carry it. Step 0
re-validation re-checks every finding with `Status: Open`. Finding ID format: `HE-NNN`
(zero-padded to 3 digits). Assign sequentially; never reuse ids.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A safety/release-gate failure class recurs and is wholly unguarded — every release can reintroduce it; or a proposed/existing block-intent hook uses a non-blocking event so the guard never binds |
| High | A defect class recurs across two-or-more passes with no hook; a context-discipline-gap (a mandated should-route step) with a context tool available and no routing hook; a hook shaped for the wrong harness so it never runs |
| Medium | A single-occurrence automatable mandate with no hook; an over-permissioned-bash pattern (permission-allowed, not a mandated step) that could route through the context tool |
| Low | Redundant or near-duplicate proposed coverage; a routing gap on a command whose result is trivially small (a single value or one line) |
| Advisory | Defense-in-depth hook opportunity where no failure has yet recurred |

## Fix Strategy

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
- Marking a finding Fixed without firing the wired hook on its evidence input

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"The existing hooks look comprehensive, so no new ones are needed."** Coverage is measured against the evidence base, not against how the current set looks. A set that looks complete still misses the failure class that recurs in the findings history. Mine every source in step 3 before judging coverage.

**"I'll read settings.json and skip the findings history, git, and memory."** The evidence base is the input to this skill; skipping it is skipping the skill. Read every findings pass, the git fix-commit clusters, and every memory entry every run. An unmined source is an unfiled coverage gap and forces verdict INCOMPLETE.

**"Memory doesn't exist, so the run is not applicable."** Absent memory is one empty source, recorded as empty. Mine the other sources and produce a coverage verdict; the run still runs.

**"context-mode is a nice-to-have, I won't enforce routing."** Where a context-saving tool exists and a workflow routes large output through raw `Bash`/`Read`, that is a context-discipline-gap and is filed. Only the must-run-direct allowlist is exempt. Convenience is not exemption.

**"Bash is convenient, so allow it broadly."** Broad `Bash` that could route through the context tool is over-permissioned. Only state mutation, build/test runners, short fixed-output OBSERVE, and interactive commands are exempt; everything that gathers or processes is routed.

**"It's Claude Code, so I'll ignore the other harness."** Detect the harness first and hold every proposed hook to that harness's mechanism and best practices. A Claude Code hook written into a Copilot project, or vice versa, enforces nothing — that is a harness-mismatch finding against your own proposal.

**"I'll describe the hook I'd add and call it done."** A described hook is an Open finding. Enforcement counts only after the hook is wired and fired on the evidence input and observed to block or warn as intended.

**"PostToolUse can block the bad call."** PostToolUse cannot block; the tool already ran. Blocking enforcement uses PreToolUse (deny/ask) or an exit-2 event. Choosing an event that cannot achieve the intent is a wrong-event finding — never mark such a hook Fixed.

**"I'll enforce the rule with a quick Bash one-liner in the hook and move on."** A hook that gathers or parses large output must itself obey context-discipline and must fail closed. An unquoted, fail-open Bash hook reintroduces the gap it was meant to close.

**"Re-running the evidence input to prove the hook fires is overkill."** A hook not fired on its evidence input is unproven, and unproven is Open. Proof is the deny decision or non-zero exit on the exact input, not the assertion that it would.

**"This is loophole-hunter's job."** loophole-hunter audits existing constraints for evasion; it does not mine the evidence base for *missing* hooks or enforce context-discipline. Absence and routing are this skill's surface. Do not defer the coverage and routing analysis to loophole-hunter, and do not re-file its fail-open/matcher-gap classes here.

**"A truly exhaustive mine would take too long; the fast findings are the deliverable."** "All gaps" means every evidence source mined and every should-route case classified, not the subset found before the deadline. If time is genuinely insufficient, report the inventory with unmined sources marked Unexamined and verdict INCOMPLETE — never present a partial mine as COMPLETE.
