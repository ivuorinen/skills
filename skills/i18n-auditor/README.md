# i18n-auditor

Hostile single-shot internationalization/localization audit against the project's declared locale scope. Assumes every user-facing string, number, date, and sort is hardcoded to one locale until the code proves it routes through a localization mechanism. Hunts seven defect classes — hardcoded strings, locale-unsafe formatting, naive datetimes, concatenated mistranslations, missing plural/gender rules, RTL/bidi breaks, and charset/collation corruption. Speculation is banned: every finding names the literal or call site, a concrete locale where it produces wrong output, and the localization mechanism the project already has. A repo with no i18n framework AND no declared multi-locale requirement gets the explicit verdict `no localization surface — single-locale by declared scope` and files nothing beyond that verdict. Uses the project's existing i18n mechanism (gettext/ICU/`Intl`/framework catalog); never adds an i18n dependency.

## When to Use

- "i18n audit" / "internationalization audit" / "localization audit" / "find hardcoded strings" / "check locale handling"
- Before shipping a new locale or entering a new market
- After adding user-facing text, number/date formatting, or sorting that must render correctly across locales
- Before a release on a product that ships translations

**When NOT to use:**
- Whether a localized UI has sufficient label/contrast/keyboard access → use [a11y-auditor]
- PII appearing in a translated log line → use [observability-auditor]
- The decision to adopt an i18n framework where none exists → use [complexity-hunter] (never add the dependency here)
- Whole-repo defect audit → use [nitpicker]

Internal log strings, code identifiers, and machine-to-machine protocol constants are not user-facing — do not route them, drop them.

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Translation catalogs (gettext `.po`/`.mo`, i18next JSON, Rails/Django locale files, ICU message bundles); locale config; every user-facing emission point (rendered templates/components, API response messages, CLI output, notification/email text, formatted numbers and dates); installed extractor/lint output (`pybabel extract`, `i18next-parser`, `xgettext`, eslint-plugin-i18next, eslint-plugin-formatjs) |
| **Writes** | `docs/audit/i18n-auditor-findings.md` |

## How to Invoke

```
/i18n-auditor
```

A repo with no i18n framework and no declared multi-locale requirement gets the explicit verdict "no localization surface — single-locale by declared scope" and files nothing beyond it EXCEPT naive-datetime findings — timezone-naive handling of a stored or user-facing instant is timezone-correctness, not locale presentation, and still bites a single-locale app whose users span timezones. A project that declares multi-locale intent but ships no framework is IN scope — that absence is itself the finding surface.

## Defect Classes

| Class | Definition |
|-------|------------|
| **hardcoded-string** | A user-facing string literal not routed through the project's translation catalog / i18n framework |
| **locale-unsafe-format** | Number/currency/date/time formatted with hardcoded separators or non-locale-aware APIs (`f"{n:,}"`, hardcoded `strftime` order, a manual `$` prefix) |
| **naive-datetime** | Timezone-naive datetime used for a user-facing or stored instant; server-local-time assumption; DST-unsafe arithmetic |
| **concat-mistranslation** | A sentence assembled by concatenating translated fragments with variables (word order breaks in other languages); pluralization by `if n == 1` |
| **missing-plural-gender** | Count-dependent text without the framework's plural rules; hardcoded gendered strings |
| **rtl-bidi** | Layout or logic assuming left-to-right (string reversal, manual alignment, no `dir` handling) — file only when a UI surface exists |
| **charset-collation** | Byte-length truncation of multibyte text, locale-insensitive case-folding, ASCII-order sort presented to users as alphabetical |

## Process

```
0. Re-validate existing findings against current code
1. Determine the localization surface — no framework AND no declared multi-locale requirement → explicit verdict, still hunt naive-datetime, then step 6
2. Probe i18n tooling (probe first, never install)
3. Hunt every defect class on every traced emission point — confirm user-facing, not already routed, name the breaking locale
4. File findings: LOC-NNN, class, path, breaking locale, wrong output, impact, concrete fix
5. Write docs/audit/i18n-auditor-findings.md
6. Ask: "Apply fixes? (a)ll auto-applicable (c)ritical-and-high only (n)o"
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A surface left untraced is recorded as an `Unexamined:` Summary bullet naming a concrete blocker.

## Findings Format

```
#### [LOC-NNN] Short title
Status: Open
Class: <hardcoded-string|locale-unsafe-format|naive-datetime|concat-mistranslation|missing-plural-gender|rtl-bidi|charset-collation>
Path: <emission point → literal/call, file:line>
Locale: <the specific locale/language that breaks and why>
Wrong output: <the incorrect string/number/date the current code produces in that locale>
Impact: <what the user sees and the consequence>
Fix: <the concrete change — catalog call, Intl/babel/ICU call, tz-aware conversion, plural rule>
```

Finding ID format: `LOC-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Locale-unsafe formatting on money/legal/medical data where the convention changes the number's meaning; a datetime stored timezone-naive that yields a wrong-day/wrong-appointment result |
| High | User-facing hardcoded strings on a product that ships translations; concat-mistranslation that produces a grammatically broken sentence in a supported locale |
| Medium | Missing plural rules; ASCII-order sort presented as alphabetical; locale-insensitive case-folding on user data |
| Low | Hardcoded string on an admin-only surface of an otherwise-translated product |
| Advisory | RTL/bidi gap on a product with no current RTL locale but a named plan to add one |

## Fix Strategy

Auto-applicable fixes (approval-gated via the step 6 prompt) reuse the project's existing localization mechanism — wrapping a literal in the existing translation call, replacing a manual format with the existing `Intl`/`babel`/ICU call, making a naive datetime tz-aware with the existing timezone utility. Restructuring a concatenated sentence into a parameterized ICU/plural message, or introducing timezone handling where the app stores naive times, each require explicit per-change approval. Never add an i18n dependency (route the adoption decision to [complexity-hunter]) and never invent unverifiable translated text — wrap the string and leave translation to the catalog owners.

## Related Skills

- [a11y-auditor] — localized-UI label/contrast/keyboard access routed there
- [observability-auditor] — PII in translated log lines routed there
- [complexity-hunter] — the decision to adopt an i18n framework routed there
- [nitpicker] — invokes this skill in `i18n` mode

---

[a11y-auditor]: ../a11y-auditor/README.md
[observability-auditor]: ../observability-auditor/README.md
[complexity-hunter]: ../complexity-hunter/README.md
[nitpicker]: ../nitpicker/README.md
