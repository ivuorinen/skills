# loophole-hunter

Hostile audit of a Claude Code project's enforcement surface — `.claude/rules/`, hook scripts, `.claude/settings.json` wiring, permissions, and skills. Assumes every constraint is bypassable until its enforcement path is traced end-to-end and proven to bind, then closes each loophole and re-runs the bypass to prove it is gone.

## When to Use

- "Close the loopholes" / "harden the Claude Code setup" / "find ways our rules can be bypassed"
- After adding a rule, hook, skill, or settings change, to confirm it actually binds
- Before a release, to prove the enforcement surface has no silent gaps
- When invoked by [nitpicker] in `loophole` mode

**When NOT to use:**
- Rule *quality and placement* (kebab-case, grab-bags, misplaced CLAUDE.md rules) → use [claude-rules-auditor]
- Application source security (CVEs, secrets, dependencies) → use [security-auditor]
- General codebase audit → use [nitpicker]

## What It Reads / Writes

| | |
|---|---|
| **Reads** | `.claude/rules/**`; every hook script referenced by settings plus any hooks directory; `.claude/settings.json` and `.claude/settings.local.json` (hooks, permissions, `claudeMdExcludes`); every `SKILL.md` under `skills/` and `.claude/skills/` |
| **Writes** | `docs/audit/loophole-hunter-findings.md` |

## How to Invoke

```
/loophole-hunter
```

Enumerates the full enforcement surface automatically. Reuses `check-rules-anatomy.py` (from [claude-rules-auditor]) and `check-audit-consistency.py` (from [nitpicker]) for programmatic first passes; proceeds and records the gap if either is absent.

## Loophole Classes

| Class | Definition |
|-------|------------|
| **unenforced-rule** | A `.claude/rules/` mandate no hook, validator, or CI step blocks |
| **fail-open-hook** | A hook that exits 0 (allow) on its own error or unexpected input |
| **matcher-gap** | A settings matcher that misses inputs the paired rule claims to govern |
| **permission-contradiction** | A `permissions.allow` entry that permits what a rule forbids |
| **unwired-hook** | A hook script no settings entry runs, or an entry pointing to a missing script |
| **excluded-rule** | A rule file silenced by `claudeMdExcludes` or a disable flag |
| **rationalizable-step** | A hedged/optional skill step an agent can skip, or a mode combo that bypasses a safety step |
| **warn-only** | A hook that warns and exits 0 where the rule implies a hard block |
| **bypassable-mechanism** | A constraint enforced only by a skippable path (e.g. `--no-verify`) with no rule forbidding the skip |
| **self-exempting** | A rule or hook with an exception broad enough to swallow it |
| **semantic-gap** | A validator that checks structure but not the property the rule requires |

## Process

```
0. Re-validate existing findings (re-run each bypass; move closed → Fixed)
1. Enumerate the full enforcement surface — never sample
2. Trace every enforcement path (existence of a same-named hook is not proof)
3. Read every hook script line by line; confirm fail-closed and matcher coverage
4. Cross-check rule×permission, rule×hook, hook-script×wiring matrices
5. Read every skill body in full, including recognized ones
6. File findings — no finding without a constructed bypass
7. Write docs/audit/loophole-hunter-findings.md
8. Ask: "Close loopholes? (a)ll (c)ritical-and-high only (s)afe (n)o" — prove each closure
9. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A run is COMPLETE only when every enumerated element is examined. Any element left
unexamined is listed as an `- Unexamined:` bullet in the Summary and forces run verdict
INCOMPLETE.

## Findings Format

```
# Loophole Hunter Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements Open-Unexamined)
- Surface enumerated: rules N | hook scripts N | hook wirings N | permissions N | skills N
- Examined: rules N | hook scripts N | hook wirings N | permissions N | skills N
- Open-Unexamined: N
- Unexamined: <surface element path> — <why not examined>

## Open Findings

### Critical

#### [LH-NNN] Short title
Status: Open
Class: <loophole class>
Area: <file path or settings key>
Problem: <what constraint fails to bind>
Evidence: <the concrete bypass>
Impact: <what the bypass allows>
Fix: <exact change>
```

Finding ID format: `LH-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | A security, safety, or release-gate constraint can be silently bypassed |
| High | An enforcement constraint does not bind at all (unenforced, unwired, matcher-gap, warn-only) |
| Medium | Rationalizable mandatory step; bypassable-via-skip mechanism; semantic validator gap |
| Low | Redundant enforcement; narrow matcher with low blast radius |
| Advisory | Hardening opportunity where no current bypass exists |

## Related Skills

- [nitpicker] — invokes this skill in `loophole` mode and incorporates its open Critical/High findings
- [claude-rules-auditor] — checks rule *quality and placement*; this skill checks rule *enforceability*
- [security-auditor] — application-source security; complementary surface

---

[skill-source]: SKILL.md
[nitpicker]: ../nitpicker/README.md
[claude-rules-auditor]: ../claude-rules-auditor/README.md
[security-auditor]: ../security-auditor/README.md
