---
name: migration-auditor
description: 'Hostile single-shot audit of database schema and data migrations — assumes every migration eats production until proven safe: destructive ops with no rollout story, irreversible downs, long-lock operations, missing FK indexes, schema-model drift, unbatched data migrations, deploy-order breaks, duplicate versions. Use when auditing pending migrations before a deploy or reviewing schema changes. Triggers: "audit the migrations", "is this migration safe", "review the schema changes".'
---

# Migration Auditor

## Overview

Hostile audit of database schema and data migrations. It assumes every migration eats production until proven safe: it locates every migration system in the repo, enumerates every migration newer than the last audit (all of them on the first run), reads each end-to-end — up and down — and cross-checks ORM models against the sum of migrations and the committed schema dump. Every finding names the migration file:line, the database engine, and the concrete failure scenario: which lock blocks which traffic, which deploy order corrupts which rows, which data is unrecoverable. Static analysis only — it never runs a migration against any database. It writes `docs/audit/migration-auditor-findings.md` and, on approval, fixes findings — editing only migrations not yet applied to any shared environment; the fix for an applied migration is always a new migration. Single-shot: re-validate existing findings, enumerate, read, cross-check, file new findings, optionally fix, re-validate. Out of scope: SQL injection and access control in migrations (route to `security-auditor`); query performance outside migration files (route to `perf-auditor`).

## When to Use

- Auditing pending migrations before a deploy or release, or reviewing a PR that adds or edits schema or data migrations
- After a migration incident — a lock storm, a lost column, a failed rollback — to find its siblings before they fire
- When asked to "audit the migrations", "is this migration safe", or "review the schema changes"

**When NOT to use:** For SQL injection or permission grants inside migrations, use `security-auditor`. For slow queries in application code, use `perf-auditor`.

## Process

Check every audit-set migration against every defect class. A finding is filed only with the migration file:line, the engine, and a concrete failure scenario.

| Class | Definition | Scenario to construct |
|-------|------------|------------------------|
| **destructive-op** | `DROP TABLE`/`DROP COLUMN`, `TRUNCATE`, or an `ALTER` narrowing a type, with no backfill, backup step, or staged rollout recorded in the migration or its accompanying change | The rows or values destroyed and the absence of any recovery path |
| **irreversible** | No down-migration, or a down that cannot restore the data the up destroyed (a down that recreates an empty column is not a rollback) | The up's data change versus what the down actually restores |
| **locking-op** | An operation holding a long table lock under load: Postgres `CREATE INDEX` without `CONCURRENTLY`, `SET NOT NULL` or narrowing `ALTER TYPE` (ACCESS EXCLUSIVE + rewrite), `ADD COLUMN` with a volatile default on pre-11 Postgres; MySQL `ALTER TABLE` forcing a table copy instead of `ALGORITHM=INPLACE`/`INSTANT`. The fix names the engine-specific safe form | The lock taken, its duration driver (table size), and the reads/writes it blocks |
| **missing-fk-index** | A new foreign key with no index on the referencing column | The parent-side `DELETE`/`UPDATE` that full-scans the child table per row |
| **schema-model-drift** | ORM models/entities disagree with the sum of migrations or the committed schema dump | The field/column pair that differs and which side production actually has |
| **unbatched-data-migration** | `UPDATE`/`DELETE` over an unbounded row set in one transaction or statement | The row-count driver, the lock/undo/WAL growth, and the replication lag it causes |
| **deploy-order-break** | Migration and code that must deploy atomically under a rolling deploy: enum value removal old code still writes, `NOT NULL` on a column old code omits, a renamed column with no dual-write window | The old-code/new-schema (or new-code/old-schema) window and the writes that fail or corrupt inside it |
| **ordering-conflict** | Duplicate or branching migration version numbers/timestamps across merged branches | The two colliding migrations and what the runner does: fail, skip, or apply out of order |

**Evidence rule.** Every finding names the migration file:line, the engine, and the concrete failure scenario. A table-size claim cites evidence (seed data, fixtures, the domain) or states its growth assumption explicitly — "the table is small" is an assumption, not a defense; file the finding and record the assumption in the Scenario.

```
0. Re-validate existing findings
   If docs/audit/migration-auditor-findings.md exists, re-validate each Status: Open finding:
   - Defect corrected (safe form used, new corrective migration added, down restores) → Fixed
   - Finding was wrong (recovery path exists, lock is instant on this engine version) → Invalid
   - Still unsafe → leave Open

1. Locate every migration system
   Django (*/migrations/*.py), Alembic (versions/), Rails (db/migrate/), Flyway (V*__*.sql),
   Liquibase (changelogs), Prisma (prisma/migrations/), knex, and raw SQL migration
   directories — a repo may hold several; audit each. Detect the engine (Postgres, MySQL,
   SQLite, SQL Server) from config, connection strings, or dialect imports.

2. Enumerate the audit set
   Every migration newer than the "Audited through:" marker in the findings Summary;
   on the first run, every migration. The marker bounds per-file reads only — the drift,
   deploy-order, and ordering-conflict cross-checks always use the full migration history.
   Record counts. Never sample; any unread audit-set migration is an Unexamined bullet → INCOMPLETE.

3. Read every audit-set migration end-to-end
   Up and down both — including the down of a data-destroying up. Classify each statement against every defect class; for locking-op, name the exact lock and the safe form.

4. Cross-check models vs schema
   Diff every ORM model/entity against the sum of all migrations and any committed schema
   dump (schema.rb, structure.sql, schema.prisma); every disagreement is schema-model-drift.

5. Determine applied status per migration
   A migration on the default branch, in a released tag, reflected in the committed schema
   dump, or stated by the user to have run on any shared environment is applied; only
   migrations introduced by the current unmerged branch and never deployed anywhere shared
   are unapplied. When in doubt, treat as applied.

6. File findings
   Assign the next MG-NNN id; record class, engine, applied status, area, problem, scenario,
   and the exact fix. Apply the Evidence rule to every entry.

7. Write docs/audit/migration-auditor-findings.md
   Update "Last validated" to today; advance "Audited through:" to the newest migration
   examined per system — never past a migration listed in an Unexamined bullet.
   "Generated" is the first-run date; never change it.

8. Present summary — state the run verdict (COMPLETE only if zero audit-set elements are
   unexamined) — then ask: "Fix migrations? (a)ll  (c)ritical-and-high only  (s)afe  (n)o"
   - (a)ll / (c)ritical-and-high only: apply the matching Auto-applicable fixes.
   - (s)afe: edits to unapplied migrations that change no final schema outcome only — swap in
     the engine-safe locking form, write a missing down, add batching bounds.
   Apply in severity order (Critical first). Verify each fix by re-reading the edited migration
   against its defect class plus the system's offline checks when present (a validate/check
   command that connects to nothing) — never by running the migration. Move verified fixes to Fixed.

9. Commit gate
   Fix edits to migration, model, and schema-dump files stay in the working tree
   unstaged — never stage or commit them silently. Then ask: "Commit findings to git?
   (y/n)" and, on yes, stage only docs/audit/migration-auditor-findings.md.
```

## Findings Format

Output path: `docs/audit/migration-auditor-findings.md`

```
# Migration Auditor Findings
Generated: YYYY-MM-DD
Last validated: YYYY-MM-DD

## Summary
- Total: N | Open: N | Fixed: N | Invalid: N
- Run verdict: COMPLETE | INCOMPLETE (N elements unexamined)
- Systems detected: <django|alembic|rails|flyway|liquibase|prisma|knex|raw-sql> (engine: <postgres|mysql|...>)
- Audit set: migrations N | examined N | models cross-checked N | schema dumps N
- Audited through: <system>: <newest migration identifier examined>
- Open-Unexamined: N
- Unexamined: <migration path> — <why not examined>

## Open Findings

### Critical

#### [MG-NNN] Short title
Status: Open
Class: <destructive-op|irreversible|locking-op|missing-fk-index|schema-model-drift|unbatched-data-migration|deploy-order-break|ordering-conflict>
Engine: <postgres|mysql|sqlite|...> (version assumption if lock behavior depends on it)
Applied: <yes|no — shared-environment status per step 5>
Area: <migration file:line>
Problem: <the unsafe operation>
Scenario: <the concrete failure — which lock blocks what, which deploy order corrupts what, which data is unrecoverable>
Fix: <the exact change; for an applied migration, the new corrective migration>

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

#### [MG-NNN] Short title
Fixed: YYYY-MM-DD
Notes: <the change made, and the re-read/offline check that verified it>

## Invalid

### Pass N — YYYY-MM-DD

#### [MG-NNN] Short title
Notes: <why the failure scenario does not hold>
```

`validate-audit-findings-hook.py` runs on every write of this file: it recomputes and rewrites the
`Total: N | Open: N | Fixed: N | Invalid: N` line from the actual finding entries and re-emits the other
`## Summary` bullets after it — keep that line in exactly that shape and insert no field between `Total:`
and `Invalid:`. All supplementary bullets (`Run verdict`, `Systems detected`, `Audit set`, `Audited
through`, `Open-Unexamined`, `Unexamined:`) follow the Total line; unexamined migrations live as
`Unexamined:` Summary bullets, never in a separate section, and `Open-Unexamined` equals their count — it
is not part of the Open/Fixed/Invalid totals. The per-finding `Status:` field is `Open` for an examined,
still-unsafe finding; on moving a finding to Fixed or Invalid, drop the `Status:` line. Step 0 re-checks
every `Status: Open` finding. Finding ID format: `MG-NNN` (zero-padded to 3 digits); assign sequentially and never reuse ids.

## Severity Guide

| Severity | Condition |
|----------|-----------|
| Critical | Unrecoverable data loss, or a full-table lock, in a migration not yet applied to production: destructive-op with no recovery path; irreversible down on a data-destroying up; locking-op that blocks writes for the duration of a table scan or rewrite |
| High | deploy-order-break with a concrete corruption/failure window; unbatched-data-migration over an unbounded set; ordering-conflict the runner will fail or misorder on; the same Critical-shape defect in an already-applied migration (the damage window has passed but the corrective migration is still owed) |
| Medium | missing-fk-index; schema-model-drift; missing down on a non-destructive up |
| Low | locking-op on a table proven bounded and tiny (evidence cited); hygiene defects in migration naming or ordering that the runner tolerates |
| Advisory | Hardening with no current failure scenario: batching pattern for a still-small table, backup step before a guarded destructive op |

## Fix Strategy

Every migration edit happens only on approval through the step 8 gate. A migration applied to any shared environment (step 5) is never edited — its fix is a new migration.

**Auto-applicable (ask first, apply only on approval; unapplied migrations only):**
- Swap a locking op for the engine-specific safe form (`CREATE INDEX CONCURRENTLY` outside a transaction; `ALGORITHM=INPLACE, LOCK=NONE`; `NOT VALID` + `VALIDATE`)
- Write the missing down-migration that restores what the up changes
- Add batching bounds to an unbatched data migration
- Add the missing index on a new foreign key's referencing column

**Requires explicit approval per change:**
- Authoring a new corrective migration for a defect in an applied migration
- Renumbering migrations to resolve an ordering-conflict, or splitting one migration into schema + backfill + cleanup stages for a deploy-order fix
- Editing ORM models or the schema dump to resolve schema-model-drift

**Never auto-apply:**
- Editing a migration applied to any shared environment — in-place edits desync environments and break checksum/state tracking; the fix is a new migration
- Running any migration or connecting to any database (`migrate`, `db:migrate`, `alembic upgrade`, `flyway migrate`, `prisma migrate`) — this skill is static analysis
- Deleting a migration file
- Marking a finding Fixed without re-reading the change against its defect class

## Common Mistakes

These are the rationalizations this skill exists to defeat. Each one is forbidden.

- **"It already ran in staging, so it's safe."** Staging proves the SQL parses; it proves nothing about production locks or loss. A lock that is instant on staging's ten thousand rows blocks writes for minutes on production's hundred million. Audit every migration against production-shaped assumptions, applied-to-staging or not.
- **"The ORM generated it, so it's correct."** Generators emit the naive form: non-concurrent index creation, in-place type narrowing, table-rewriting defaults. The generator optimizes for schema equality, never for lock behavior or data safety. Generated migrations get the same end-to-end read as hand-written ones.
- **"Down-migrations are never used, skip checking them."** The down is the rollback story, read exactly when production is on fire. A down that drops the column the up backfilled destroys data at the worst possible moment. Read every down and verify it restores what the up changed.
- **"This table is small now, so the lock doesn't matter."** Size at audit time is not size at deploy time or a year later. File the locking-op; a bounded-and-tiny defense requires cited evidence and lands at Low, not silence.
- **"I'll only read the newest migration; the older ones already shipped."** Drift and deploy-order checks need the sum of all migrations against the models — a defect in the sum is invisible from one file. The "Audited through:" marker bounds per-file reads only, never the cross-checks.
- **"I'll fix the applied migration file in place."** In-place edits to applied migrations desync every environment that already ran the old version and break checksum tracking (Flyway fails validation; Alembic and Rails silently diverge). The fix for an applied migration is always a new migration.
- **"Adding a column is always safe."** `ADD COLUMN` with a volatile default rewrites the table on pre-11 Postgres; `NOT NULL` without a default breaks every insert from old code during the rolling deploy. Additive is not automatically safe — check the lock and the deploy window.
- **"I'll run the migration locally to verify."** This skill never runs migrations against any database. Verification is the end-to-end read plus the migration system's offline checks. Running it proves the local case and silently skips the production scenario the finding is about.
- **"It's raw SQL with no down framework, so reversibility is out of scope."** The framework's silence waives nothing. A destructive up without a written recovery path — companion down script, backup step, or restore procedure — is irreversible; file it.
- **"Too many migrations, I'll sample the recent ones."** Sampling is how the table-rewriting ALTER ships. Read the entire audit set; genuine time exhaustion produces `Unexamined:` bullets and verdict INCOMPLETE, never a silent sample presented as done.
