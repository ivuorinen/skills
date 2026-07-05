# a11y-auditor

Hostile single-shot accessibility audit of a codebase's UI layer against WCAG 2.2 AA. Assumes the interface is unusable without a mouse and a screen until the code proves otherwise. Detects the UI stack, enumerates every component/template/HTML/CSS file, runs the installed accessibility tools first (axe-core, eslint-plugin-jsx-a11y, pa11y — never installs anything), then performs the manual sweep tools cannot: focus-order reasoning, ARIA semantics, and contrast math computed from design tokens. Every finding names the file:line, quotes the markup, states which users are excluded, and gives the exact fix.

This skill verifies the floor [complexity-hunter] declares: accessibility basics are never simplified away — a11y-auditor is what proves they are actually present after any simplification pass.

## When to Use

- "a11y audit" / "accessibility audit" / "check WCAG" / "is this keyboard accessible"
- Before a release that ships any UI change
- A custom widget (modal, dropdown, tab panel) was added and keyboard/screen-reader support is unproven
- After [complexity-hunter] simplifies UI code, to prove the accessibility floor held

**When NOT to use:**
- Performance → use [perf-auditor]
- General correctness → use [adversarial-reviewer]
- Vulnerabilities and secrets → use [security-auditor]

## a11y-auditor vs. security-auditor

| | a11y-auditor | security-auditor |
|---|---|---|
| Question | "Who is excluded from using this UI?" | "What can an attacker exploit?" |
| Tool role | Tools seed the audit; the manual sweep (focus order, ARIA semantics, contrast math) is the audit | Tools are the audit; the skill orchestrates, parses, and consolidates |
| Surface | Components, templates, HTML, CSS/design tokens | Whole codebase, dependencies, git history, IaC |
| No-surface case | Explicit "no auditable UI surface" verdict — never an empty list dressed as clean | Not applicable — every repo has a security surface |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every component file (`.jsx`/`.tsx`/`.vue`/`.svelte`), server template, `.html` file, CSS/SCSS/design-token file, Tailwind config; installed tool output (axe-core, eslint-plugin-jsx-a11y, pa11y) |
| **Writes** | `docs/audit/a11y-auditor-findings.md` |

## How to Invoke

```
/a11y-auditor
```

Detects the UI stack first. A repo with no UI surface gets the explicit verdict "no auditable UI surface"; a partial UI surface (CLI emitting HTML reports, backend serving templates) is audited for those parts.

## Defect Classes

| Class | Definition |
|-------|------------|
| **missing-alternative** | Image, icon, or media without alt text or an accessible name — including icon-only buttons |
| **unlabeled-control** | Form input without a programmatic label; placeholder is not a label |
| **keyboard-unreachable** | Click/hover-only handlers on non-interactive elements; custom widgets without keyboard interaction |
| **focus-loss** | Modals that fail to trap/restore focus; focus outlines removed with no replacement |
| **aria-misuse** | Redundant roles, `aria-hidden` on focusable content, invalid combinations, ARIA where a native element does the job |
| **contrast-violation** | Ratios below WCAG AA, computed from tokens/CSS with the math shown; runtime-only colors marked Unverifiable |
| **structure-break** | Heading skips, faked lists, headerless tables, missing landmarks/`lang` |
| **motion-hazard** | Autoplaying/animated content with no `prefers-reduced-motion` path |

## Process

```
0. Re-validate existing findings against current code
1. Detect the stack and enumerate the UI surface — no UI surface → explicit verdict, skip to 7
2. Run installed tools (probe first, never install)
3. Manual sweep: every file against every class — focus order, ARIA, contrast math
4. File findings: AY-NNN, class, WCAG SC, file:line, quoted markup, excluded users, exact fix
5. Write docs/audit/a11y-auditor-findings.md
6. Ask: "Apply fixes? (a)ll (c)ritical-and-high only (s)afe (n)o" — color changes always per change
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A run is COMPLETE only when every enumerated file is examined. Unexamined files are `- Unexamined:` Summary bullets and force verdict INCOMPLETE.

## Findings Format

```
#### [AY-NNN] Short title
Status: Open
Class: <missing-alternative|unlabeled-control|keyboard-unreachable|focus-loss|aria-misuse|contrast-violation|structure-break|motion-hazard>
WCAG: <SC number(s), 2.2 AA>
Area: <file:line>
Problem: <what fails and for whom>
Evidence: <the quoted markup, handler, or computed contrast ratio with the math>
Excludes: <keyboard-only | screen reader | low-vision | motion-sensitive users>
Fix: <the exact attribute, element swap, handler, or color value to change>
```

Finding ID format: `AY-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | A core flow (login, checkout, primary navigation, form submission) cannot be completed by keyboard or screen reader at all |
| High | An entire component class or page region excluded for one user group; modal without focus trap; global outline removal; body-text contrast failure |
| Medium | A non-core flow or single component excluded; secondary-text contrast failure; aria-misuse misreporting a widget |
| Low | Defect with a working accessible sibling on the same element; redundant role; single heading skip |
| Advisory | Hardening with no current exclusion; reduced-motion on subtle transitions; native-element swap where ARIA currently works |

## Fix Strategy

Fixes never change visual design without approval. Attribute/semantics fixes (alt, labels, native-element swaps, key handlers) are auto-applicable on approval; color changes are always approved per change, never batched.

## Related Skills

- [complexity-hunter] — names accessibility basics as a never-simplify floor; this skill verifies that floor
- [security-auditor] — the closest tool-driven sibling; audits the attack surface where this skill audits the exclusion surface
- [perf-auditor] — performance defects routed there
- [adversarial-reviewer] — general correctness routed there

---

[complexity-hunter]: ../complexity-hunter/README.md
[security-auditor]: ../security-auditor/README.md
[perf-auditor]: ../perf-auditor/README.md
[adversarial-reviewer]: ../adversarial-reviewer/README.md
