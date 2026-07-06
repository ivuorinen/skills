# data-privacy-auditor

Hostile single-shot data-privacy audit. Assumes every element of personal data is stored and transmitted without the control its data class requires until the code proves the control exists. Hunts seven defect classes — PII/PHI/PCI/credentials unprotected at rest, personal data flowing to an uncontrolled sink, excessive collection, missing retention/deletion, missing consent gate, weak anonymization, and cross-border third-party leaks. This audit is domain-heavy and false-positive-prone, so the bar is high: an element must be IDENTIFIABLY personal from the code — a field name (`email`, `ssn`, `dob`), a type, a schema comment, or a source traced to user input — and never guessed. Guessing personalness is the primary failure mode of this audit and is banned. A repo that handles no identifiable personal data gets the explicit verdict "no personal-data surface" and files nothing beyond it. Static analysis only; never adds a dependency.

## When to Use

- "run a privacy audit" / "PII audit" / "check data protection" / "GDPR check" / "find unprotected personal data"
- Before a release, a new data collection feature, or a third-party integration
- After adding a path that stores, transmits, or shares user data — a new column, an analytics call, a third-party API integration
- When another skill routes a data-handling concern here

**When NOT to use:**
- Whether plaintext personal data is exploitable via a vulnerability (SQL injection reaching the column, an auth bypass) → use [security-auditor]
- Personal data appearing in a log line → use [observability-auditor]
- Encryption-at-rest schema/column migrations → use [migration-auditor]
- Whole-repo defect sweep → use [nitpicker]

An ambiguously-named field with no evidence of being personal is not a finding — drop it, do not route it.

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Persisted and transmitted data (schema/model fields, DB columns, cache keys, file writes, request/response bodies, third-party payloads); the control each element carries at its store/flow site (hash, encryption, tokenization, consent gate, redaction, deletion/TTL path); call signatures, schema definitions, migrations |
| **Writes** | `docs/audit/data-privacy-auditor-findings.md` |

## How to Invoke

```
/data-privacy-auditor
```

A repo that handles no identifiable personal data gets the explicit verdict "no personal-data surface" — an empty findings list implying a clean audit is forbidden.

## Defect Classes

| Class | Definition |
|-------|------------|
| **pii-at-rest-unprotected** | PII/PHI/PCI/credentials persisted (DB column, file, cache) with no encryption/hashing/tokenization where the data class requires it — passwords not hashed, card PAN in plaintext, SSN/health data unencrypted |
| **pii-to-uncontrolled-sink** | Personal data flowing to a sink that should not receive it: analytics, a third-party API, an error tracker, a URL query string, a client-visible response field (a log line routes to [observability-auditor]) |
| **excessive-collection** | Personal data collected and persisted with no code that consumes it for a legitimate use — a field captured and stored but never read (data minimization) |
| **missing-retention-deletion** | Personal data with no deletion/expiry path — no TTL, no user-delete, no anonymization job — growing forever |
| **missing-consent-gate** | Processing/tracking/sharing personal data on a path with no consent check where the data class or jurisdiction requires one — analytics before consent, marketing without opt-in |
| **weak-anonymization** | "Anonymized" data that remains re-identifiable — an email hashed as a pseudo-ID, quasi-identifiers left joinable, reversible tokenization presented as anonymization |
| **cross-border-third-party-leak** | Personal data sent to a processor or region without the safeguard the code should carry — a region-pinning flag ignored, a processor called with no data-handling gate |

## Process

```
0. Re-validate existing findings against current code
1. Inventory the personal-data elements the code actually handles — IDENTIFIABLY personal from concrete evidence, never guessed; no personal data → "no personal-data surface" verdict, skip to 7
2. Map the sinks and controls each element already carries
3. Hunt every defect class on every identified element — confirm personal + data class, control absent at the site, name the consumer-visible consequence
4. File findings: DP-NNN, class, element + data class, site, absent control, impact, concrete fix
5. Write docs/audit/data-privacy-auditor-findings.md
6. Ask: "Apply fixes? (a)ll auto-applicable (c)ritical-and-high only (n)o" — most privacy fixes are approval-gated per change
7. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A store/sink left untraced is recorded as an `Unexamined:` Summary bullet naming a concrete blocker.

## Findings Format

```
#### [DP-NNN] Short title
Status: Open
Class: <pii-at-rest-unprotected|pii-to-uncontrolled-sink|excessive-collection|missing-retention-deletion|missing-consent-gate|weak-anonymization|cross-border-third-party-leak>
Element: <the identified personal-data element and its data class, with the evidence it is personal>
Site: <store/flow site, file:line>
Control absent: <the specific control the data class requires that is missing>
Impact: <what data is exposed, to whom, and the obligation — name the jurisdiction when it scopes severity>
Fix: <the concrete change — hash, encrypt, redact, drop, gate, deletion path, region-pin>
```

Finding ID format: `DP-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Credentials stored recoverably (plaintext or reversible); regulated data (health, financial, government-id) persisted or sent to a third party with no protection |
| High | PII to an uncontrolled sink (analytics, error tracker, client response); no deletion path for regulated personal data |
| Medium | Excessive collection of identifiers; weak anonymization presented as anonymized; a consent gate missing on a tracking path |
| Low | Minor over-collection of low-sensitivity data with a plausible near-term purpose named |
| Advisory | A retention or consent gap on a path handling only pseudonymous low-risk data, with the compliance obligation named as jurisdiction-dependent |

## Fix Strategy

Privacy fixes alter data semantics or product behavior and carry legal weight — the skill biases toward approval-gated. Only redacting/dropping a personal-data field before an EXISTING analytics or third-party telemetry call (a non-consumer-facing sink) rides the auto-applicable prompt. Hashing a credential field (rehashing breaks existing rows and the login/verification path — a data migration routed to [migration-auditor]), redacting a field from a client response (a consumer-visible contract change), adding encryption at rest (a schema change — route the migration to [migration-auditor]), a retention/deletion job, a consent gate, or any change to what data is collected each require explicit per-change approval with the change named. Never delete data the application legitimately needs (propose it), never weaken a control to silence a finding, and never add a crypto/compliance dependency.

## Related Skills

- [security-auditor] — exploitability of plaintext personal data routed there
- [observability-auditor] — PII in log lines routed there
- [migration-auditor] — encryption-at-rest schema/column migrations routed there
- [nitpicker] — invokes this skill in `privacy` mode

---

[security-auditor]: ../security-auditor/README.md
[observability-auditor]: ../observability-auditor/README.md
[migration-auditor]: ../migration-auditor/README.md
[nitpicker]: ../nitpicker/README.md
