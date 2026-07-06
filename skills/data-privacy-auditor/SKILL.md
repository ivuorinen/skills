---
name: data-privacy-auditor
description: 'Hostile single-shot data-privacy audit — hunts personal data stored or transmitted without the control its data class requires: PII/PHI/PCI/credentials unprotected at rest, personal data flowing to uncontrolled sinks, excessive collection, missing retention/deletion, missing consent gates, weak anonymization, and cross-border third-party leaks, each finding naming the identified element, the absent control, and a concrete fix. A repo handling no identifiable personal data gets the explicit verdict "no personal-data surface". Use when auditing a codebase for privacy defects, checking data protection, or verifying GDPR obligations. Triggers: "privacy audit", "PII audit", "data protection audit", "GDPR check", "find unprotected personal data", "run data-privacy-auditor".'
---

# Data Privacy Auditor

## Overview

Hostile single-shot data-privacy audit. Assume every element of personal data is stored and transmitted without the control its data class requires until the code proves the control exists. Hunt seven defect classes — PII/PHI/PCI/credentials unprotected at rest, personal data flowing to an uncontrolled sink, excessive collection, missing retention/deletion, missing consent gate, weak anonymization, and cross-border third-party leaks — and file each with the identified element, its data class, the exact code site, the absent control, and a concrete fix. This audit is domain-heavy and false-positive-prone, so the bar is high: an element must be IDENTIFIABLY personal from the code — a field name (`email`, `ssn`, `dob`), a type, a schema comment, or a source traced to user input — and never guessed. Guessing personalness is the primary failure mode of this audit and is banned. A repo that handles no identifiable personal data gets the explicit verdict "no personal-data surface" and files nothing beyond it. Static analysis only; never adds a dependency. All findings are graded Critical → Advisory and written to `docs/audit/data-privacy-auditor-findings.md`.

## When to Use

- Auditing a codebase for data-privacy defects before a release, a new data collection feature, or a third-party integration
- When asked "run a privacy audit", "PII audit", "check data protection", "GDPR check", or "find unprotected personal data"
- After adding a path that stores, transmits, or shares user data — a new column, an analytics call, a third-party API integration
- When another skill routes a data-handling concern here

**When NOT to use:** Whether plaintext personal data is *exploitable via a vulnerability* (SQL injection reaching the column, an auth bypass exposing it) → `security-auditor`; you own that it is stored or flowed against its data class's requirement, security owns the exploit — file the at-rest fact here, route the exploit there, do not double-file. Personal data appearing in a *log line* → `observability-auditor`; it owns PII-in-logs, you own the store, third-party, and response sinks — do not double-file the same log line. Whole-repo defect sweep → `nitpicker`.

## Defect Classes

File a finding only when the element is identifiably personal from concrete code evidence AND the specific absent control is named. An ambiguously-named field with no evidence of being personal is not a finding — drop it, do not route it. No identified element, no finding.

| Class | What to hunt | Evidence to construct |
|-------|--------------|------------------------|
| **pii-at-rest-unprotected** | PII/PHI/PCI/credentials persisted (DB column, file, cache) with no encryption/hashing/tokenization where the data class requires it — passwords not hashed, card PAN in plaintext, SSN/health data unencrypted | The identified element and its data class, the store site (file:line), the absent control, and the concrete protection to add |
| **pii-to-uncontrolled-sink** | Personal data flowing to a sink that should not receive it: analytics, a third-party API, an error tracker, a URL query string, a client-visible response field (a *log line* is `observability-auditor`'s — route it) | The element, the flow site + the sink, the control that is absent, and the redact/drop/gate fix |
| **excessive-collection** | Personal data collected and persisted with no code that consumes it for a legitimate use — a field captured and stored but never read (data minimization) | The collection/store site, the demonstrated absence of a consuming read, and the drop-or-justify fix |
| **missing-retention-deletion** | Personal data with no deletion/expiry path — no TTL, no user-delete, no anonymization job — growing forever | The stored element, the absent deletion path, and the retention/TTL/delete mechanism to add |
| **missing-consent-gate** | Processing/tracking/sharing personal data on a path with no consent check where the data class or jurisdiction requires one — analytics before consent, marketing without opt-in | The processing site, the absent gate, and the consent-check to add before the processing |
| **weak-anonymization** | "Anonymized" data that remains re-identifiable — an email hashed as a pseudo-ID, quasi-identifiers left joinable, reversible tokenization presented as anonymization | The anonymization site, the re-identification vector, and the stronger control that actually de-identifies |
| **cross-border-third-party-leak** | Personal data sent to a processor or region without the safeguard the code should carry — a region-pinning flag ignored, a processor called with no data-handling gate | The send site, the missing safeguard, and the region-pin/gate/agreement-flag fix |

## Process

```
0. Re-validate existing findings
   If docs/audit/data-privacy-auditor-findings.md exists, re-check each finding with
   Status: Open against the current code:
   - The store/flow changed and the element no longer reaches it, or the control landed → Fixed (record date)
   - Finding was wrong (element is not personal, control already existed) → Invalid (record why)
   - Still present → leave Open. Never carry a finding forward without re-checking it.

1. Inventory the personal-data elements the code actually handles
   Enumerate the persisted and transmitted data: schema/model fields, DB columns, cache keys,
   file writes, request/response bodies, third-party payloads. For each element, decide whether
   it is IDENTIFIABLY personal from concrete evidence — a field name (email, ssn, dob, phone,
   address, name, card, password), a type, a schema comment, or a source you traced to user
   input — and record its data class (credential, PHI/health, PCI/financial, government-id, PII,
   pseudonymous). An element with no such evidence is NOT personal for this audit — do not guess.
   If the repo handles NO identifiable personal data at all, write the findings file with the
   explicit Summary verdict "no personal-data surface" — an empty findings list implying a clean
   audit is forbidden — then skip to step 7.

2. Map the sinks and controls each element already carries
   For every identified element, read the actual code: is it hashed/encrypted/tokenized at the
   store site, gated by a consent check, dropped or redacted before a third-party/response/analytics
   call, given a deletion/TTL path? Read the call signature, the schema definition, the migration.
   "Probably encrypted" and "probably gated" are both banned; the site decides.

3. Hunt every defect class on every identified element
   Work the Defect Classes table. For each candidate:
   a. Confirm the element is identifiably personal (step 1 evidence) and name its data class.
   b. Confirm the specific control the data class requires is absent at the site — verify no
      existing hash, encryption, consent gate, redaction, or deletion path already neutralizes it.
   c. Name the consumer-visible consequence: what data is exposed, to whom, and the obligation.
   d. Candidate fails a, b, or c → drop it. It is not a finding. A guessed-personal field is never a finding.

4. File findings
   Assign the next DP-NNN id. Record class, element + data class, site (file:line), the absent
   control, the impact, and the concrete fix. Route the exploit path (if any) to security-auditor
   and any log-line sink to observability-auditor in one line — never double-file.

5. Write docs/audit/data-privacy-auditor-findings.md
   Update "Last validated" to today. "Generated" is the first-run date; never change it.

6. Present summary — finding counts by severity, data classes found, unexamined stores/sinks —
   then ask: "Apply fixes? (a)ll auto-applicable  (c)ritical-and-high only  (n)o"
   Apply in severity order, Critical first. Only the Fix Strategy auto-applicable list is eligible
   through this prompt; every other fix — encryption at rest, a deletion job, a consent gate,
   any change to what data is collected — stays a proposal in its finding and is applied only
   when the user approves that specific change by name.

7. Commit gate
   Fix edits are left in the working tree unstaged. Ask: "Commit findings to git? (y/n)" —
   on yes, stage only docs/audit/data-privacy-auditor-findings.md. Never commit silently.
```

## Findings Format

Output path: `docs/audit/data-privacy-auditor-findings.md`

```
# Data Privacy Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N stores/sinks unexamined) | no personal-data surface
- Data classes found: <comma-separated: credential, PHI, PCI, government-id, PII, pseudonymous — or none>
- Unexamined: <store/sink> — <why not traced>

## Open Findings

### Critical

#### [DP-NNN] Short title
Status: Open
Class: <pii-at-rest-unprotected|pii-to-uncontrolled-sink|excessive-collection|missing-retention-deletion|missing-consent-gate|weak-anonymization|cross-border-third-party-leak>
Element: <the identified personal-data element and its data class, with the evidence it is personal>
Site: <store/flow site, file:line>
Control absent: <the specific control the data class requires that is missing>
Impact: <what data is exposed, to whom, and the obligation — name the jurisdiction when it scopes severity>
Fix: <the concrete change — hash, encrypt, redact, drop, gate, deletion path, region-pin>

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

#### [DP-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <what changed, and the re-check showing the element now carries its required control>

## Invalid

### Pass N — YYYY-MM-DD

#### [DP-NNN] Short title
Notes: <why the finding was wrong — element not personal, control already present, dead path>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the `Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other `## Summary` bullets after it. Keep the Total line in exactly that shape and insert no field into it. All supplementary bullets (`Run verdict`, `Data classes found`, `Unexamined:`) follow the Total line; unexamined stores/sinks live as `Unexamined:` Summary bullets, never in a separate section. The hook recognizes only `## Summary`, `## Open Findings`, `## Fixed`, and `## Invalid`, and once findings begin it treats any other `##` header as end-of-findings. All fixed findings go under one `## Fixed` h2 and all invalid findings under one `## Invalid` h2, sub-divided by `### Pass N — YYYY-MM-DD` h3 headers — never `## Fixed — pass N` variants, never h2 → h4 without an h3.

The per-finding `Status:` field is `Open` for a verified, still-present finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-validation re-checks every finding with `Status: Open`. Finding ID format: `DP-NNN` (zero-padded to 3 digits). Assign sequentially from the highest existing ID; never reuse an ID, even after Fixed or Invalid.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Credentials stored recoverably (plaintext or reversible); regulated data (health, financial, government-id) persisted or sent to a third party with no protection |
| High | PII to an uncontrolled sink (analytics, error tracker, client response); no deletion path for regulated personal data |
| Medium | Excessive collection of identifiers; weak anonymization presented as anonymized; a consent gate missing on a tracking path |
| Low | Minor over-collection of low-sensitivity data with a plausible near-term purpose named |
| Advisory | A retention or consent gap on a path handling only pseudonymous low-risk data, with the compliance obligation named as jurisdiction-dependent |

## Fix Strategy

Privacy fixes alter data semantics or product behavior and carry legal weight — bias toward approval-gated. Name every change.

**Auto-applicable (ask first via the step 6 prompt, apply only on approval):**
- Redact or drop a personal-data field before an EXISTING analytics or third-party telemetry call — a non-consumer-facing sink

**Requires explicit approval per change (most privacy fixes):**
- Hashing a credential field with the project's EXISTING password hasher — rehashing breaks every existing plaintext row and the login/verification path; it is a data migration, route it to `migration-auditor`
- Redacting or dropping a personal-data field from a client response — a consumer-visible API contract change
- Adding encryption at rest — a schema/column change; route the migration to `migration-auditor`
- Adding a retention/deletion job or TTL
- Adding a consent gate — business logic on the processing path
- Changing what data is collected or stored
Each of these changes data semantics or product behavior and carries legal weight — state the change in the finding.

**Never:**
- Change business logic silently
- Delete data the application legitimately needs — propose it, never delete unasked
- Weaken a control to silence a finding
- Add a crypto or compliance dependency — the fix is proposed in code the repo already carries
- Apply any fix before the step 6 prompt
- Commit anything silently

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

**"This field is probably personal data, so I'll file it."** Guessing personalness is banned outright — it is the primary failure mode of this audit. A finding requires a field name, a type, a schema comment, or a source traced to user input proving the element is personal. No evidence, no finding — drop it, do not route it.

**"There's user data somewhere, so I'll audit broadly and file what looks risky."** If the repo handles no identifiable personal data, emit the "no personal-data surface" verdict and file nothing beyond it. Manufacturing findings to look thorough trains users to ignore the report.

**"PII in this log line is mine to fix."** Log lines are `observability-auditor`'s pii-in-logs class. Route it in one line; never double-file the same sink. You own the store, third-party, and response sinks.

**"Plaintext PII here is really a SQL-injection issue, so I'll skip it."** The exploit is `security-auditor`'s; the at-rest-unprotected fact is yours. File the finding for the element stored against its data class's requirement, and route the exploit — do not fold one into the other.

**"I'll add AES encryption to this column right now."** Encryption at rest is a schema change with legal weight — approval-gated per change, and the migration routes to `migration-auditor`. It never rides the auto-applicable prompt.

**"Hashing the email anonymizes it, so I'll close the finding."** A hashed identifier is a stable pseudo-ID, still joinable and re-identifiable — that is the weak-anonymization class, not a remediation. File it; do not accept it as a control.

**"I'll delete the excess data to fix the minimization finding."** Never delete data the application may need. The fix is to propose the drop or a justification for approval — deleting data unasked is a second defect, not a fix.

**"This is only a GDPR issue in the EU, so I'll skip it."** Jurisdiction scopes severity, not existence. File the finding and name the obligation as jurisdiction-dependent — silence is approval of the exposure.

**"Last pass's findings are surely still valid — skip step 0."** Every `Status: Open` finding is re-checked against current code every run. Code moves; a stale Open finding sends the user chasing a fixed exposure, and a silently-fixed one never reaches the Fixed ledger.

**"I'll redact the obvious fields as I go."** No fix is applied before the step 6 summary and prompt. Even the auto-applicable list waits for the answer. Fixes applied mid-hunt bypass the approval gate and contaminate re-validation.
