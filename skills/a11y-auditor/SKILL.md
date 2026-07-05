---
name: a11y-auditor
description: 'Hostile single-shot accessibility audit of the UI layer against WCAG 2.2 AA — assumes the interface is unusable without a mouse and screen until the code proves otherwise, then finds every exclusion with evidence and the exact fix. Use when auditing UI code for accessibility, checking WCAG compliance, verifying keyboard or screen-reader usability, or before a UI release. Triggers: "a11y audit", "accessibility audit", "check WCAG", "is this keyboard accessible", "run a11y-auditor".'
---

# A11y Auditor

## Overview

Hostile single-shot accessibility audit of a codebase's UI layer. It assumes the interface is unusable without a mouse and a screen until the code proves otherwise. The named bar is WCAG 2.2 AA. It detects the UI stack, enumerates every component and template file, runs the installed accessibility tools first, then performs the manual sweep tools cannot: focus-order reasoning, ARIA semantics, and contrast math computed from design tokens and CSS. Every finding names the file:line, quotes the markup or handler, states which users are excluded (keyboard-only, screen reader, low-vision), and gives the exact fix. Findings go to `docs/audit/a11y-auditor-findings.md`. This skill verifies the floor `complexity-hunter` declares: accessibility basics are never simplified away — this audit is what proves they are present. Single-shot: re-validate existing findings, enumerate the surface, run tools, sweep manually, file findings, optionally fix, re-validate.

## When to Use

- Auditing UI code — components, templates, raw HTML, CSS — for accessibility defects
- Before a release that ships any UI change
- A custom widget (modal, dropdown, tab panel, drag handle) was added and keyboard/screen-reader support is unproven
- When asked to "check accessibility", "audit for WCAG", or "verify this works without a mouse"
- After `complexity-hunter` simplifies UI code, to prove the accessibility floor held

**When NOT to use:** For performance, use `perf-auditor`. For general correctness, use `adversarial-reviewer`. For vulnerabilities and secrets, use `security-auditor`.

## Process

### UI Surface

Detect the stack first, then enumerate every file in it. Enumerate project-maintained source only — build output (`dist/`, `build/`, vendored bundles) is out of scope; its defects are fixed at the source. A repo with **no UI surface at all** (no components, templates, HTML, or UI-emitting code) gets the explicit Summary verdict `no auditable UI surface` — the findings file is still written; an empty findings list implying a clean audit is forbidden. A **partial** UI surface (a CLI that emits HTML reports, a backend serving templates, an error page) is IN scope for those parts.

| Stack signal | Surface to enumerate |
|--------------|----------------------|
| React/Preact (`.jsx`/`.tsx`) | Every component file |
| Vue (`.vue`) / Svelte (`.svelte`) | Every single-file component |
| Server templates (Jinja/ERB/Blade/Twig/Handlebars/templ) | Every template file |
| Plain HTML | Every `.html`/`.htm` file, including generated-report templates |
| Styling | Every CSS/SCSS file, design-token file, CSS variable definition, Tailwind config |

### Tool Pass

Probe each tool with `which` (or a config/dependency check for the lint plugin) before use. Run only what is installed — **never install anything**. Record every tool as Available, Not available, or Errored in the report. Tools: `axe-core` (via an existing project test/script that invokes it), `eslint-plugin-jsx-a11y` (run the project's own eslint when the plugin is configured), `pa11y` (against locally served or static HTML). Tool output seeds findings; it never bounds them — the manual sweep below covers what no tool sees.

### Defect Classes

Check every enumerated file against every applicable class.

| Class | Definition | WCAG |
|-------|------------|------|
| **missing-alternative** | Image, icon, or media without alt text or an accessible name — including icon-only buttons | 1.1.1, 4.1.2 |
| **unlabeled-control** | Form input without a programmatic label (`<label for>`, `aria-labelledby`, or wrapping label). Placeholder is not a label | 1.3.1, 3.3.2 |
| **keyboard-unreachable** | Click/hover-only handler on a non-interactive element with no key handler and no `tabindex`; custom widget without keyboard interaction | 2.1.1 |
| **focus-loss** | Modal/drawer that fails to trap focus while open or restore it on close; `outline: none`/`:focus { outline: 0 }` with no visible replacement | 2.4.3, 2.4.7 |
| **aria-misuse** | Redundant role on a native element, `aria-hidden` on focusable content, invalid role/attribute combination, ARIA where a native element does the job — the first rule of ARIA is don't use ARIA | 4.1.2 |
| **contrast-violation** | Text below 4.5:1 (3:1 for large text ≥ 24px, or ≥ 18.66px bold) or UI component below 3:1, computed from tokens/variables/hardcoded colors | 1.4.3, 1.4.11 |
| **structure-break** | Heading levels skipping, lists faked with divs, data tables without `<th>`/scope, missing landmarks or `lang` attribute | 1.3.1, 2.4.1, 3.1.1 |
| **motion-hazard** | Autoplaying or animated content with no `prefers-reduced-motion` path and no pause/stop control | 2.2.2, 2.3.3 |

### Contrast Math

Compute, do not eyeball. Relative luminance `L = 0.2126R + 0.7152G + 0.0722B` with each channel linearized (`c/12.92` when `c ≤ 0.04045`, else `((c+0.055)/1.055)^2.4`); ratio `= (Llighter + 0.05) / (Ldarker + 0.05)`. Resolve token and CSS-variable chains to their static values and show the math in the finding (`#767676 on #FFFFFF = 4.54:1`). A color pair that resolves only at runtime (theme injected from an API, user-configured palette) is skipped and recorded as an `Unverifiable:` Summary bullet with the reason — never guessed, never silently dropped.

### Steps

```
0. Re-validate: if docs/audit/a11y-auditor-findings.md exists, re-check each finding
   with Status: Open against current code — defect gone → Fixed (record date); finding
   was wrong → Invalid (record reason); still present → leave Open.
1. Detect the stack and enumerate the UI surface per the table. Record counts. No UI
   surface → write the findings file with verdict "no auditable UI surface", then skip
   to step 7. Partial surface → audit those parts in full.
2. Run the Tool Pass. Parse tool output into candidate findings.
3. Manual sweep: every enumerated file against every defect class — focus order traced
   handler by handler, ARIA validated against the spec, contrast computed per Contrast
   Math. Never sample; an unexamined file is an Unexamined Summary bullet and forces
   verdict INCOMPLETE.
4. File findings: next AY-NNN id, class, WCAG SC, file:line, quoted markup/handler,
   excluded users, exact fix (the attribute, element swap, or handler to add).
5. Write docs/audit/a11y-auditor-findings.md. Update "Last validated" to today;
   "Generated" is the first-run date and never changes.
6. Present summary — verdict, counts by severity, Unverifiable list — then ask:
   "Apply fixes? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   (s)afe applies only the attribute/semantics set in Fix Strategy; every item on the
   per-change list is asked per change regardless of the answer. Apply in severity order;
   after each fix, re-check the quoted markup and move to Fixed only when the defect is gone.
7. Commit gate: fix edits stay unstaged — never staged or committed silently. Ask:
   "Commit findings to git? (y/n)"; on yes, stage only docs/audit/a11y-auditor-findings.md.
```

## Findings Format

Output path: `docs/audit/a11y-auditor-findings.md`

```
# A11y Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N files unexamined) | no auditable UI surface
- Stack detected: <react|vue|svelte|templates|plain-html|none> — components N | templates N | html N | css/token files N
- Tool coverage: available <list> | not available <list> | errored <tool>: <error>
- Unverifiable: <file:line> — <color pair resolved only at runtime, reason>
- Unexamined: <file> — <why not examined>

## Open Findings

### Critical

#### [AY-NNN] Short title
Status: Open
Class: <missing-alternative|unlabeled-control|keyboard-unreachable|focus-loss|aria-misuse|contrast-violation|structure-break|motion-hazard>
WCAG: <SC number(s), 2.2 AA>
Area: <file:line>
Problem: <what fails and for whom>
Evidence: <the quoted markup, handler, or computed contrast ratio with the math>
Excludes: <keyboard-only | screen reader | low-vision | motion-sensitive users>
Fix: <the exact attribute, element swap, handler, or color value to change>

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

#### [AY-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed and the re-check showing the defect is gone>

## Invalid

### Pass N — YYYY-MM-DD

#### [AY-NNN] Short title
Notes: <why the finding was wrong>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field into it. All supplementary bullets (`Run verdict`, `Stack detected`, `Tool coverage`, `Unverifiable:`, `Unexamined:`) follow the Total line and are preserved. Keep Unverifiable and Unexamined items as Summary bullets, never as separate `##` sections: the hook recognizes only `## Summary`, `## Open Findings`, `## Fixed`, and `## Invalid`, and once findings begin it treats any other `##` header as end-of-findings. All fixed findings live under one `## Fixed` h2 and all invalid under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants, never skipped header levels.

Finding ID format: `AY-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse ids. Only Open findings carry the `Status:` line; step 0 re-validation re-checks every finding with `Status: Open`.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | A core flow (login, checkout, primary navigation, form submission) cannot be completed by keyboard or screen reader at all: keyboard-unreachable submit action, focus-trapped-nowhere modal blocking the page, unlabeled required field in a core form |
| High | An entire component class or page region excluded for one user group: icon-only buttons with no accessible name across the app, modal without focus trap/restore, focus outline removed globally with no replacement, contrast failure on body text |
| Medium | A non-core flow or single component excluded: one unlabeled filter input, contrast failure on secondary text, aria-misuse that misreports a widget's role or state, data table without headers |
| Low | Defect with a working accessible sibling on the same element: decorative image with a noisy alt, redundant role on a native element, single heading-level skip |
| Advisory | Hardening with no current exclusion: missing `prefers-reduced-motion` on a subtle transition, landmark refinement, native-element swap where ARIA currently works |

## Fix Strategy

Fixes never change visual design without approval. Semantics and attributes change the accessibility tree, not the pixels.

**Auto-applicable on approval (the `(s)afe` set):**
- Add `alt`, accessible names, `<label for>`/`aria-labelledby`, `lang`, `<th>`/`scope`
- Swap a fake interactive element for the native one (`div onClick` → `<button>`) preserving existing classes and styles
- Remove redundant/invalid ARIA; replace ARIA with the native element it imitates
- Add key handlers and `tabindex="0"` to a custom widget mirroring its click behavior

**Requires explicit approval per change:**
- Any color value change (contrast fixes) — always per change, never batched
- Focus trap/restore wiring on a modal (behavior change beyond attributes)
- Restoring or restyling focus outlines (visible design change)
- Structural rewrites that change rendering (div-list → `<ul>`, heading re-leveling)
- Adding a `prefers-reduced-motion` block or pause/stop control

**Never auto-apply:**
- Installing any dependency or tool
- Spraying `aria-label`/`role` across elements instead of fixing semantics
- Removing functionality (deleting the animation, hiding the widget) to silence a finding
- Marking a finding Fixed without re-checking the quoted markup

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"The eslint a11y plugin passes, so it's accessible."** Linters see static JSX attributes. They cannot trace focus order across a modal open/close, validate ARIA against actual widget behavior, or compute a contrast ratio from a token chain. The tool pass seeds the audit; the manual sweep is the audit.

**"This is an internal tool, a11y doesn't apply."** The bar is WCAG 2.2 AA and it does not move with the audience. Internal users are keyboard-only and screen-reader users too. Audit at full severity.

**"The design team owns contrast, skip it."** Contrast is computable from the code in front of you. Resolve the tokens, run the math, show it in the finding. Only a color pair that resolves at runtime is skipped — and it is recorded as Unverifiable, never silently dropped.

**"aria-label everywhere fixes it."** ARIA-spraying is the aria-misuse defect class, not a remediation. The first rule of ARIA is don't use ARIA: a native `<button>`, `<label>`, or `<nav>` beats a labeled div every time. A fix that adds ARIA where a native element exists is itself a finding.

**"No UI framework detected, done."** Server templates, raw HTML, error pages, and HTML reports emitted by a CLI are all UI surface. Only a repo with no UI-emitting code of any kind gets the "no auditable UI surface" verdict — and it gets that verdict explicitly, never an empty findings list dressed as a clean audit.

**"Keyboard users can use the other path."** The flagged flow itself must work. An alternate route is not a fix; WCAG 2.1.1 requires the functionality, not a detour. File the finding against the broken flow.

**"It renders fine, so screen readers will cope."** Visual rendering proves nothing about the accessibility tree. A pixel-perfect div-soup form is invisible to a screen reader. Audit the semantics, not the screenshot.

**"It's a well-known component library, accessibility is handled."** A library is accessible only as used: an icon-only library button still needs an accessible name, a library modal still needs its focus props wired, a themed library still fails contrast. Audit the usage in this codebase, not the library's reputation.

**"Proper fixes would change the design, so I'll skip filing them."** Semantics and attributes never change pixels — file and fix them. Color and focus-outline changes do change pixels — file them anyway and route the fix through per-change approval. Skipping the finding because the fix needs approval is silence, and silence is approval of the exclusion.

**"I audited the components; templates and CSS are someone else's layer."** The surface table is the scope: components, templates, HTML, and CSS/token files, every one enumerated and examined. An unexamined file is an Unexamined Summary bullet and forces verdict INCOMPLETE — never a quiet omission.
