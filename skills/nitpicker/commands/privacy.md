# /nitpicker privacy — Data Privacy Auditor

Hostile single-shot data-privacy audit: assume every element of personal data is stored and transmitted without the control its data class requires until the code proves the control exists.

## When to use

- Auditing a codebase for data-privacy defects before a release, a new data collection feature, or a third-party integration
- After adding a path that stores, transmits, or shares user data — a new column, an analytics call, a third-party API integration
- When another command routes a data-handling concern here
- Triggers: "privacy audit", "PII audit", "data protection audit", "GDPR check", "find unprotected personal data"

Out of scope: whether plaintext personal data is _exploitable via a vulnerability_ (SQL injection reaching the column, an auth bypass exposing it) routes to `/nitpicker security` — file the at-rest fact here, route the exploit there, never double-file. Personal data appearing in a _log line_ routes to `/nitpicker observability` — it owns pii-in-logs; this command owns the store, third-party, and response sinks. A whole-repo defect sweep is `/nitpicker audit`.

## The identifiability bar

This audit is domain-heavy and false-positive-prone, so the bar is high: an element must be IDENTIFIABLY personal from the code — a field name (`email`, `ssn`, `dob`, `phone`, `address`, `name`, `card`, `password`), a type, a schema comment, or a source traced to user input — and never guessed. Guessing personalness is the primary failure mode of this audit and is banned. An ambiguously-named field with no evidence of being personal is not a finding — drop it, do not route it. A repo that handles no identifiable personal data gets the explicit verdict **"no personal-data surface"** and files nothing beyond it. Static analysis only; never add a dependency.

## Defect classes

File a finding only when the element is identifiably personal from concrete code evidence AND the specific absent control is named. No identified element, no finding.

| Class | What to hunt | Evidence to construct |
| --- | --- | --- |
| **pii-at-rest-unprotected** | PII/PHI/PCI/credentials persisted (DB column, file, cache) with no encryption/hashing/tokenization where the data class requires it — passwords not hashed, card PAN in plaintext, SSN/health data unencrypted | The identified element and its data class, the store site (file:line), the absent control, and the concrete protection to add |
| **pii-to-uncontrolled-sink** | Personal data flowing to a sink that should not receive it: analytics, a third-party API, an error tracker, a URL query string, a client-visible response field (a _log line_ routes to `/nitpicker observability`) | The element, the flow site + the sink, the control that is absent, and the redact/drop/gate fix |
| **excessive-collection** | Personal data collected and persisted with no code that consumes it for a legitimate use — a field captured and stored but never read (data minimization) | The collection/store site, the demonstrated absence of a consuming read, and the drop-or-justify fix |
| **missing-retention-deletion** | Personal data with no deletion/expiry path — no TTL, no user-delete, no anonymization job — growing forever | The stored element, the absent deletion path, and the retention/TTL/delete mechanism to add |
| **missing-consent-gate** | Processing/tracking/sharing personal data on a path with no consent check where the data class or jurisdiction requires one — analytics before consent, marketing without opt-in | The processing site, the absent gate, and the consent-check to add before the processing |
| **weak-anonymization** | "Anonymized" data that remains re-identifiable — an email hashed as a pseudo-ID, quasi-identifiers left joinable, reversible tokenization presented as anonymization | The anonymization site, the re-identification vector, and the stronger control that actually de-identifies |
| **cross-border-third-party-leak** | Personal data sent to a processor or region without the safeguard the code should carry — a region-pinning flag ignored, a processor called with no data-handling gate | The send site, the missing safeguard, and the region-pin/gate/agreement-flag fix |

## Process

1. **Inventory the personal-data elements the code actually handles.** Enumerate the persisted and transmitted data: schema/model fields, DB columns, cache keys, file writes, request/response bodies, third-party payloads. For each element, decide whether it is IDENTIFIABLY personal from concrete evidence and record its data class (credential, PHI/health, PCI/financial, government-id, PII, pseudonymous). An element with no such evidence is NOT personal for this audit — do not guess. If the repo handles NO identifiable personal data at all, report the explicit verdict "no personal-data surface" — an empty findings list implying a clean audit is forbidden — and stop.
2. **Map the sinks and controls each element already carries.** For every identified element, read the actual code: is it hashed/encrypted/tokenized at the store site, gated by a consent check, dropped or redacted before a third-party/response/analytics call, given a deletion/TTL path? Read the call signature, the schema definition, the migration. "Probably encrypted" and "probably gated" are both banned; the site decides.
3. **Hunt every defect class on every identified element.** For each candidate: (a) confirm the element is identifiably personal and name its data class; (b) confirm the specific control the data class requires is absent at the site — verify no existing hash, encryption, consent gate, redaction, or deletion path already neutralizes it; (c) name the consumer-visible consequence: what data is exposed, to whom, and the obligation. Candidate fails a, b, or c → drop it. A store/sink left untraced is reported by name in the summary with the concrete blocker and forces verdict INCOMPLETE.
4. **File findings** via the store protocol in `_conventions.md`, using `--auditor privacy`. The finding body records the class, the identified element and its data class with the evidence it is personal, the store/flow site (file:line), and the absent control; the Impact names what data is exposed, to whom, and the obligation — name the jurisdiction when it scopes severity; the Fix is the concrete change (hash, encrypt, redact, drop, gate, deletion path, region-pin). Route the exploit path (if any) to `/nitpicker security` and any log-line sink to `/nitpicker observability` in one line — never double-file.
5. **Summary and fix gate.** Present finding counts by severity, data classes found, and unexamined stores/sinks, then run the shared apply-fixes prompt. Only the Fix Strategy auto-applicable list is eligible through the prompt; every other fix — encryption at rest, a deletion job, a consent gate, any change to what data is collected — stays a proposal in its finding and is applied only when the user approves that specific change by name. Fix edits stay in the working tree unstaged.

## Severity guide

| Severity | Condition |
| --- | --- |
| Critical | Credentials stored recoverably (plaintext or reversible); regulated data (health, financial, government-id) persisted or sent to a third party with no protection |
| High | PII to an uncontrolled sink (analytics, error tracker, client response); no deletion path for regulated personal data |
| Medium | Excessive collection of identifiers; weak anonymization presented as anonymized; a consent gate missing on a tracking path |
| Low | Minor over-collection of low-sensitivity data with a plausible near-term purpose named |
| Advisory | A retention or consent gap on a path handling only pseudonymous low-risk data, with the compliance obligation named as jurisdiction-dependent |

## Fix strategy

Privacy fixes alter data semantics or product behavior and carry legal weight — bias toward approval-gated. Name every change.

**Auto-applicable:**

- Redact or drop a personal-data field before an EXISTING analytics or third-party telemetry call — a non-consumer-facing sink

**Requires explicit approval per change (most privacy fixes):**

- Hashing a credential field with the project's EXISTING password hasher — rehashing breaks every existing plaintext row and the login/verification path; it is a data migration, route it to `/nitpicker migrations`
- Redacting or dropping a personal-data field from a client response — a consumer-visible API contract change
- Adding encryption at rest — a schema/column change; route the migration to `/nitpicker migrations`
- Adding a retention/deletion job or TTL
- Adding a consent gate — business logic on the processing path
- Changing what data is collected or stored

Each of these changes data semantics or product behavior and carries legal weight — state the change in the finding.

**Never:**

- Change business logic silently
- Delete data the application legitimately needs — propose it, never delete unasked
- Weaken a control to silence a finding
- Add a crypto or compliance dependency — the fix is proposed in code the repo already carries
- Apply any fix before the fix prompt

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"This field is probably personal data, so I'll file it."** Guessing personalness is banned outright — it is the primary failure mode of this audit. A finding requires a field name, a type, a schema comment, or a source traced to user input proving the element is personal. No evidence, no finding — drop it, do not route it.
- **"There's user data somewhere, so I'll audit broadly and file what looks risky."** If the repo handles no identifiable personal data, emit the "no personal-data surface" verdict and file nothing beyond it. Manufacturing findings to look thorough trains users to ignore the report.
- **"PII in this log line is mine to fix."** Log lines are `/nitpicker observability`'s pii-in-logs class. Route it in one line; never double-file the same sink. This command owns the store, third-party, and response sinks.
- **"Plaintext PII here is really a SQL-injection issue, so I'll skip it."** The exploit is `/nitpicker security`'s; the at-rest-unprotected fact is this command's. File the finding for the element stored against its data class's requirement, and route the exploit — do not fold one into the other.
- **"I'll add AES encryption to this column right now."** Encryption at rest is a schema change with legal weight — approval-gated per change, and the migration routes to `/nitpicker migrations`. It never rides the auto-applicable prompt.
- **"Hashing the email anonymizes it, so I'll close the finding."** A hashed identifier is a stable pseudo-ID, still joinable and re-identifiable — that is the weak-anonymization class, not a remediation. File it; do not accept it as a control.
- **"I'll delete the excess data to fix the minimization finding."** Never delete data the application may need. The fix is to propose the drop or a justification for approval — deleting data unasked is a second defect, not a fix.
- **"This is only a GDPR issue in the EU, so I'll skip it."** Jurisdiction scopes severity, not existence. File the finding and name the obligation as jurisdiction-dependent — silence is approval of the exposure.
- **"I'll redact the obvious fields as I go."** No fix is applied before the summary and fix prompt. Even the auto-applicable list waits for the answer. Fixes applied mid-hunt bypass the approval gate and contaminate re-validation.
