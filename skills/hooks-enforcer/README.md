# hooks-enforcer

Hostile audit of a project's *hook coverage*. Mines the project's own evidence base — current hook wiring, every `docs/audit/*-findings.md` pass, git history, and project memory — to find recurring, hook-preventable failures that no hook guards, plus context-discipline gaps where large-output work runs through raw `Bash`/`Read` instead of a context-saving tool. Specifies the missing hooks in the host harness's correct shape and, on approval, wires each and fires it on the evidence input to prove it now binds.

## When to Use

- "Enforce hooks" / "harden hook coverage" / "add the hooks we keep needing"
- "Make sure context-mode is used where it should be" / "stop large output bloating the context window"
- A pattern of repeated fixes, reverts, or audit findings recurs with no automated guard
- Before a release, to prove every evidence-backed, hook-preventable failure class is guarded
- When invoked by [nitpicker] in `loophole` mode or by `release-prep` as a release gate

**When NOT to use:**
- Whether an *existing* hook/rule/permission can be bypassed → use [loophole-hunter]
- Rule *quality and placement* → use [claude-rules-auditor]
- Application-source security → use [security-auditor]

## hooks-enforcer vs. loophole-hunter

| | hooks-enforcer | loophole-hunter |
|---|---|---|
| Question | "What should be a hook and is not?" | "Can this existing constraint be evaded?" |
| Input | The evidence base (findings history, git, memory, current hooks) | The declared enforcement surface |
| Output | Missing hooks specified + wired in harness-correct shape; context-discipline routing | Constructed bypasses of existing constraints, closed |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | `.claude/settings.json` + `.claude/settings.local.json` hooks; every hook script under hook dirs; every `docs/audit/*-findings.md`; git history (`fix:`/`revert` clusters); project memory; available context-saving tools (context-mode `ctx_*` or equivalent); harness markers (`.claude/`, `.github/copilot-instructions.md`, `AGENTS.md`) |
| **Writes** | `docs/audit/hooks-enforcer-findings.md` |

## How to Invoke

```
/hooks-enforcer
```

Detects the host harness first, then mines the full evidence base automatically. Holds every proposed Claude Code hook to the [Claude Code Hooks best practices](https://code.claude.com/docs/en/hooks-guide); for any other harness, follows that harness's published guidance.

## Required-Hook Classes

| Class | Definition |
|-------|------------|
| **coverage-gap** | A defect class recurring across two-or-more passes/commits with no hook to catch it |
| **context-discipline-gap** | A read/gather/process command mandated by a project skill/workflow file, on raw `Bash`/`Read` where a context-saving tool exists, with no routing hook |
| **over-permissioned-bash** | A `permissions.allow` Bash pattern (not a mandated step), non-allowlisted, that could route through the context tool, left unconstrained |
| **wrong-event** | A hook whose event cannot achieve its intent (e.g. `PostToolUse` meant to block) |
| **harness-mismatch** | A hook shaped for the wrong harness, or a mandate left as prose where a hook is supported |
| **unguarded-mandate** | A recurring, automatable project mandate with no hook |

## Process

```
0. Re-validate existing findings (fire each wired hook on its evidence input; closed → Fixed)
1. Detect the harness(es) and the best-practice source for each
2. Inventory current enforcement + available context-saving tools
3. Mine the evidence base in full — findings history, git, memory, current hooks — never sample
4. Audit context-discipline: classify every Bash/Read use against the must-run-direct allowlist
5. File findings — no finding without evidence and a concrete, harness-correct hook spec
6. Write docs/audit/hooks-enforcer-findings.md
7. Ask: "Wire hooks? (a)ll (c)ritical-and-high only (s)afe (n)o" — prove each hook fires
8. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A run is COMPLETE only when every evidence source is mined and every should-route case is
classified. Any unmined source is an `- Unexamined:` Summary bullet and forces verdict INCOMPLETE.

## The Must-Run-Direct Allowlist

`Bash`/`Read` is exempt from context routing only for: state mutation (`git`, installs, `mkdir`/`mv`/`rm`, writes); build/test/lint runners whose pass/fail is the signal; short fixed-output OBSERVE (`pwd`, `git status` on a clean tree); and interactive/stateful commands. Everything that *gathers* or *processes* large output routes through the context-saving tool.

## Findings Format

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
Fix: <the exact hook — event, matcher, command, fail-closed shape — in the harness's format>
```

Finding ID format: `HE-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | A safety/release-gate failure class recurs wholly unguarded, or a block-intent hook uses a non-blocking event so the guard never binds |
| High | A defect class recurs with no hook; a mandated should-route step bypasses an available context tool with no routing hook; a hook shaped for the wrong harness |
| Medium | A single-occurrence automatable mandate with no hook; a permission-allowed over-permissioned Bash pattern |
| Low | Redundant proposed coverage; a routing gap on a command whose result is trivially small |
| Advisory | Defense-in-depth hook opportunity where no failure has yet recurred |

## Related Skills

- [nitpicker] — invokes this skill in `loophole` mode and incorporates its open Critical/High findings
- [loophole-hunter] — audits existing constraints for *evasion*; this skill audits the evidence base for *missing* hooks
- [claude-rules-auditor] — checks rule *quality and placement*

---

[nitpicker]: ../nitpicker/README.md
[loophole-hunter]: ../loophole-hunter/README.md
[claude-rules-auditor]: ../claude-rules-auditor/README.md
[security-auditor]: ../security-auditor/README.md
