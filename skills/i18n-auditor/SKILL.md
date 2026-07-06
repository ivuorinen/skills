---
name: i18n-auditor
description: 'Hostile single-shot internationalization/localization audit against the declared locale scope — assumes every user-facing string, number, date, and sort is hardcoded to one locale until the code proves it routes through a localization mechanism, then files each break with the locale it fails and a concrete fix. A repo with no i18n framework and no declared multi-locale requirement gets the explicit verdict "no localization surface — single-locale by declared scope". Use when auditing a codebase for i18n defects, checking locale handling, or hunting hardcoded strings. Triggers: "i18n audit", "internationalization audit", "localization audit", "find hardcoded strings", "check locale handling", "run i18n-auditor".'
---

# I18n Auditor

## Overview

Hostile single-shot internationalization/localization audit against the project's declared locale scope. Assume every user-facing string, number, date, and sort is hardcoded to one locale until the code proves it routes through a localization mechanism. Hunt seven defect classes — hardcoded strings, locale-unsafe formatting, naive datetimes, concatenated mistranslations, missing plural/gender rules, RTL/bidi breaks, and charset/collation corruption — and file each with the exact code path, the specific locale or language that breaks it, and a concrete fix. Speculation is banned: "this might not localize" is not a finding; every finding names the literal or call site, a concrete locale where it produces wrong output, and the localization mechanism the project already has. A repo with **no i18n framework AND no declared multi-locale requirement** gets the explicit verdict `no localization surface — single-locale by declared scope` and files nothing beyond that verdict. Uses the project's existing i18n mechanism (gettext/ICU/`Intl`/framework catalog); never adds an i18n dependency. All findings are graded Critical → Advisory and written to `docs/audit/i18n-auditor-findings.md`.

## When to Use

- Auditing a codebase for internationalization defects before shipping a new locale or entering a new market
- When asked "find hardcoded strings", "check locale handling", "will this work in <locale>", or "run an i18n audit"
- After adding user-facing text, number/date formatting, or sorting that must render correctly across locales
- Before a release on a product that ships translations

**When NOT to use:** whether a localized UI has sufficient label/contrast/keyboard access → `a11y-auditor`; PII appearing in a translated log line → `observability-auditor`; the *decision* to adopt an i18n framework where none exists → `complexity-hunter` (never add the dependency here); whole-repo defect audit → `nitpicker`. Internal log strings, code identifiers, and machine-to-machine protocol constants are not user-facing — do not route them, drop them.

## Defect Classes

File a finding only when the string or call is genuinely user-facing AND a specific locale or language that breaks it is named AND the project has (or explicitly declares it needs) a localization surface. Internal log strings, code identifiers, and machine-to-machine protocol constants are not user-facing — they are not findings. "This should probably be translated" without a named breaking locale is not a finding; the breaking locale is the evidence.

| Class | What to hunt | Evidence to construct |
|-------|--------------|------------------------|
| **hardcoded-string** | A user-facing string literal not routed through the project's translation catalog / i18n framework | The literal + call site, the locale that can't see it translated, the catalog mechanism that already exists, the fix |
| **locale-unsafe-format** | Number/currency/date/time formatted with hardcoded separators or non-locale-aware APIs (`f"{n:,}"` assuming a comma group separator, hardcoded `strftime` order, a manual `$` prefix) | The format site, a locale where it is wrong, the locale-aware API the project has (`Intl.NumberFormat`, `babel`, ICU) |
| **naive-datetime** | Timezone-naive datetime used for a user-facing or stored instant; server-local-time assumption; DST-unsafe arithmetic | The naive value, the user/storage boundary it crosses, the wrong-day/wrong-hour consequence, the tz-aware fix |
| **concat-mistranslation** | A sentence assembled by concatenating translated fragments with variables (word order breaks in other languages); pluralization by `if n == 1` | The concatenation, a language whose word order breaks, the parameterized-message (ICU) replacement |
| **missing-plural-gender** | Count-dependent text without the framework's plural rules; hardcoded gendered strings | The count/gender site, a language whose rules differ (e.g. Polish/Arabic plural categories), the plural-rule mechanism |
| **rtl-bidi** | Layout or logic assuming left-to-right (string reversal, manual alignment, no `dir` handling) — file only when a UI surface exists | The LTR assumption, the RTL locale it breaks, the fix |
| **charset-collation** | Byte-length truncation of multibyte text, locale-insensitive case-folding (`toLowerCase()` for a locale-sensitive compare), ASCII-order sort presented to users as alphabetical | The operation, the script/locale it corrupts, the Unicode-aware replacement |

## Process

```
0. Re-validate existing findings
   If docs/audit/i18n-auditor-findings.md exists, re-check each finding with Status: Open
   against the current code:
   - Code path changed and the literal/call no longer reaches a user, or the fix landed → Fixed (record date)
   - Finding was wrong (string is an internal log, formatting already routes through Intl) → Invalid (record why)
   - Still present → leave Open. Never carry a finding forward without re-checking it.

1. Determine the localization surface
   Detect the project's declared locale scope and its i18n mechanism: translation catalogs
   (gettext .po/.mo, i18next JSON, Rails/Django locale files, ICU message bundles), a locale
   config listing supported locales, or an Intl/babel/ICU usage pattern. Record what exists.
   No i18n framework AND no declared multi-locale requirement (no locale config, no translation
   files, no stated market plan) → write the findings file with verdict
   "no localization surface — single-locale by declared scope" and file nothing beyond that
   verdict EXCEPT still hunt the naive-datetime class: timezone-naive handling of a stored or
   user-facing instant is timezone-correctness, not locale presentation, and produces
   wrong-day/wrong-appointment bugs in a single-locale app whose users span timezones — file
   any naive-datetime finding, then skip the remaining string/format sweep and proceed to
   step 6 (its apply-fixes prompt covers any naive-datetime finding filed). A project that DECLARES multi-locale intent
   but ships no framework is IN scope: that absence is itself the finding surface.
   Enumerate every user-facing emission point: rendered templates/components, API response
   messages, CLI output, notification/email text, formatted numbers and dates. A surface
   left untraced is recorded as an `Unexamined:` Summary bullet naming a concrete blocker
   (unreadable generated code, missing source, no access) — effort savings is not a blocker,
   and a silently skipped surface is a defect in the audit itself.

2. Probe i18n tooling — never install
   Probe with `which` and manifest/config inspection: the project's message extractor
   (`pybabel extract`, `i18next-parser`, `xgettext`), lint rules (eslint-plugin-i18next,
   eslint-plugin-formatjs), ICU/babel/Intl usage. Record what is available in the Summary.
   Tools that are absent stay absent — reason from the code instead.

3. Hunt every defect class on every traced emission point
   Work the Defect Classes table. For each candidate:
   a. Confirm the string/call is genuinely user-facing — trace it to a render, response,
      or output boundary. Internal logs, identifiers, and protocol constants are not.
   b. Read the actual call — verify it is not already routed through the translation catalog,
      Intl/babel/ICU, or a tz-aware utility. Read the call signature, the format string, the
      import. "Probably translated" and "probably tz-aware" are both banned; the call site decides.
   c. Name the concrete locale or language that breaks it: the locale whose decimal separator,
      plural category, word order, timezone, or script the code gets wrong. No named breaking
      locale, no finding.
   d. Candidate fails a, b, or c → drop it. It is not a finding.

4. File findings
   Assign the next LOC-NNN id. Record class, path (emission point → literal/call, file:line),
   the breaking locale, the wrong output it produces, impact, and the concrete fix.

5. Write docs/audit/i18n-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

6. Present summary — finding counts by severity, tools used, unexamined surfaces —
   then ask: "Apply fixes? (a)ll auto-applicable  (c)ritical-and-high only  (n)o"
   Apply in severity order, Critical first. Only the Fix Strategy auto-applicable list
   is eligible through this prompt; every other fix stays a proposal in its finding and
   is applied only when the user approves that specific change by name.

7. Commit gate
   Fix edits are left in the working tree unstaged. Ask: "Commit findings to git? (y/n)" —
   on yes, stage only docs/audit/i18n-auditor-findings.md. Never commit silently.
```

## Findings Format

Output path: `docs/audit/i18n-auditor-findings.md`

```
# I18n Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N surfaces unexamined) | no localization surface — single-locale by declared scope
- Localization mechanism: <gettext|ICU|Intl|i18next|framework catalog|none> — supported locales: <list, or none declared>
- i18n tools available: <comma-separated list, or none>
- Unexamined: <emission point> — <why not traced>

## Open Findings

### Critical

#### [LOC-NNN] Short title
Status: Open
Class: <hardcoded-string|locale-unsafe-format|naive-datetime|concat-mistranslation|missing-plural-gender|rtl-bidi|charset-collation>
Path: <emission point → literal/call, file:line>
Locale: <the specific locale/language that breaks and why>
Wrong output: <the incorrect string/number/date the current code produces in that locale>
Impact: <what the user sees and the consequence>
Fix: <the concrete change — catalog call, Intl/babel/ICU call, tz-aware conversion, plural rule>

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

#### [LOC-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed, and the re-check showing the breaking locale now renders correctly>

## Invalid

### Pass N — YYYY-MM-DD

#### [LOC-NNN] Short title
Notes: <why the finding was wrong — internal log, already routed through Intl, no breaking locale>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field into it. All supplementary bullets (`Run verdict`, `Localization mechanism`, `i18n tools available`, `Unexamined:`) follow the Total line; unexamined emission points live as `Unexamined:` Summary bullets, never in a separate section. The hook recognizes only `## Summary`, `## Open Findings`, `## Fixed`, and `## Invalid`, and once findings begin it treats any other `##` header as end-of-findings. All fixed findings go under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants, never h2 → h4 without an h3.

The per-finding `Status:` field is `Open` for a verified, still-present finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `LOC-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after Fixed or Invalid.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Locale-unsafe formatting on money/legal/medical data where the decimal/grouping convention changes the number's meaning; a datetime parsed or stored timezone-naive that yields a wrong-day/wrong-appointment result |
| High | User-facing hardcoded strings on a product that ships translations; concat-mistranslation that produces a grammatically broken sentence in a supported locale |
| Medium | Missing plural rules; ASCII-order sort presented as alphabetical; locale-insensitive case-folding on user data |
| Low | Hardcoded string on an admin-only surface of an otherwise-translated product |
| Advisory | RTL/bidi gap on a product with no current RTL locale but a named plan to add one |

## Fix Strategy

**Auto-applicable (ask first via the step 6 prompt, apply only on approval):**
- Wrap a user-facing literal in the project's existing translation call
- Replace a manual number/date format with the project's existing `Intl`/`babel`/ICU call
- Make a naive datetime timezone-aware using the project's existing timezone utility

**Requires explicit approval per change:**
- Restructuring a concatenated sentence into a parameterized ICU/plural message (changes the message-catalog contract)
- Introducing timezone handling where the app currently stores naive times (touches stored data semantics)

**Never:**
- Add an i18n/l10n dependency where none exists — route the adoption decision to `complexity-hunter`
- Invent translated text for a language you cannot verify — wrap the string and leave translation to the catalog owners
- Apply any fix before the step 6 prompt
- Commit anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"There's no i18n framework, so there's nothing to audit."** Wrong twice. If the project declares no multi-locale intent, emit the explicit `no localization surface — single-locale by declared scope` verdict — never an empty findings list dressed as a clean audit. If the project *declares* multi-locale intent but ships no framework, that absence IS the finding surface — audit it.

**"This log string is user-facing."** Internal log lines, code identifiers, and machine-to-machine protocol constants are not user-facing. Drop them without routing them anywhere. A hardcoded log message is not an i18n defect.

**"I'll just add gettext/i18next to fix these."** Never. Adding the framework is a dependency decision routed to `complexity-hunter`. This audit uses the project's existing localization mechanism; it does not introduce one.

**"I'll translate this string into French myself."** Never invent unverifiable translations. Wrap the literal in the catalog call and leave the translation to the catalog owners. A guessed translation is a defect wearing a fix.

**"`if n == 1` handles plurals."** Plural categories differ by language — Polish has three, Arabic six. A binary singular/plural branch is the missing-plural-gender defect. Use the framework's plural-rule mechanism.

**"A comma thousands-separator is universal."** It is a decimal separator in many locales (`1,5` = one-and-a-half in de-DE, fr-FR). A hardcoded `,` group separator is locale-unsafe formatting. Route through `Intl.NumberFormat`/`babel`/ICU.

**"The datetime works on my server."** Server-local naive time is the defect. The instant crosses a user or storage boundary where the timezone differs, and the result is the wrong day or hour. File it; the fix is tz-aware.

**"I found a hardcoded string that's also an a11y label problem, I'll fix the a11y part here."** Out of scope. One line naming the route (`a11y-auditor` for the label/contrast/keyboard issue), then back to hunting i18n.

**"I'll wrap the strings as I find them."** No fix is applied before the step 6 summary and prompt. Even the auto-applicable list waits for the answer. Fixes applied mid-hunt bypass the approval gate and contaminate re-validation.

**"Last pass's findings are surely still valid — skip step 0."** Every `Status: Open` finding is re-checked against current code every run. Code moves; a stale Open finding sends the user chasing a fixed defect, and a silently-fixed one never reaches the Fixed ledger.
