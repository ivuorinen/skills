# migration-auditor

Hostile single-shot audit of database schema and data migrations. Assumes every migration eats production until proven safe: locates every migration system in the repo, enumerates every migration newer than the last audit (all on the first run), reads each end-to-end — up and down — and cross-checks ORM models against the sum of migrations and the committed schema dump. Every finding names the migration file:line, the engine, and the concrete failure scenario: which lock blocks which traffic, which deploy order corrupts which rows, which data is unrecoverable. Static analysis only — it never runs a migration. On approval it fixes findings, editing only migrations not yet applied to any shared environment; the fix for an applied migration is always a new migration.

## When to Use

- "Audit the migrations" / "is this migration safe" / "review the schema changes"
- Auditing pending migrations before a deploy or release, or reviewing a PR that adds schema/data migrations
- After a migration incident — a lock storm, a lost column, a failed rollback — to find its siblings before they fire

**When NOT to use:**
- SQL injection or permission grants inside migrations → use [security-auditor]
- Slow queries in application code → use [perf-auditor]

## migration-auditor vs. security-auditor vs. perf-auditor

| | migration-auditor | security-auditor | perf-auditor |
|---|---|---|---|
| Question | "Does this migration destroy data, lock production, or break a rolling deploy?" | "Is the code vulnerable or leaking secrets?" | "Does this code path degrade as data grows?" |
| Surface | Migration files, ORM models, committed schema dumps | Whole codebase, dependencies, git history | Entry points and the code paths they reach |
| Method | Static read of every migration + model/schema cross-check; never runs a migration | Runs installed scanners and parses their output | Reads code paths; uses installed measurement tools |
| Output | `docs/audit/migration-auditor-findings.md` | `docs/audit/security-findings.md` | `docs/audit/perf-auditor-findings.md` |

## What It Reads / Writes

| | |
|---|---|
| **Reads** | Every migration file per detected system (Django, Alembic, Rails, Flyway, Liquibase, Prisma, knex, raw SQL dirs); ORM models/entities; committed schema dumps (schema.rb, structure.sql, schema.prisma); engine config/connection strings; git branch/tag state for applied-status |
| **Writes** | `docs/audit/migration-auditor-findings.md` |

## How to Invoke

```
/migration-auditor
```

Locates every migration system and the database engine first, then audits every migration newer than the `Audited through:` marker in the findings file — the drift, deploy-order, and ordering-conflict cross-checks always use the full migration history.

## Defect Classes

| Class | Definition |
|-------|------------|
| **destructive-op** | `DROP TABLE`/`DROP COLUMN`, `TRUNCATE`, or type-narrowing `ALTER` with no backfill, backup, or staged rollout story |
| **irreversible** | No down-migration, or a down that cannot restore the data the up destroyed |
| **locking-op** | Long table lock under load — non-`CONCURRENTLY` index on Postgres, table-copying `ALTER` on MySQL, volatile-default `ADD COLUMN` on old Postgres; the fix names the engine-specific safe form |
| **missing-fk-index** | New foreign key with no index on the referencing column |
| **schema-model-drift** | ORM models disagree with the sum of migrations or the committed schema dump |
| **unbatched-data-migration** | `UPDATE`/`DELETE` over an unbounded set in one transaction |
| **deploy-order-break** | Migration and code that must deploy atomically under a rolling deploy — enum removal, `NOT NULL` old code omits, rename with no dual-write window |
| **ordering-conflict** | Duplicate or branching migration version numbers across merged branches |

## Process

```
0. Re-validate existing findings (defect corrected → Fixed; scenario wrong → Invalid)
1. Locate every migration system and detect the engine — lock behavior is engine-specific
2. Enumerate the audit set: everything newer than the "Audited through:" marker — never sample
3. Read every audit-set migration end-to-end, up and down both
4. Cross-check every ORM model against the sum of migrations and the schema dump
5. Determine applied status per migration (default branch / released tag / schema dump → applied)
6. File findings — MG-NNN with file:line, engine, and concrete failure scenario
7. Write docs/audit/migration-auditor-findings.md
8. Ask: "Fix migrations? (a)ll (c)ritical-and-high only (s)afe (n)o" — unapplied migrations only
9. Ask: "Commit findings to git? (y/n)" — never commit silently
```

A run is COMPLETE only when every audit-set migration is read and every model cross-checked. Any
unread migration is an `- Unexamined:` Summary bullet and forces verdict INCOMPLETE.

## Findings Format

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

## Open Findings

### Critical

#### [MG-NNN] Short title
Status: Open
Class: <destructive-op|irreversible|locking-op|missing-fk-index|schema-model-drift|unbatched-data-migration|deploy-order-break|ordering-conflict>
Engine: <postgres|mysql|sqlite|...>
Applied: <yes|no>
Area: <migration file:line>
Problem: <the unsafe operation>
Scenario: <which lock blocks what, which deploy order corrupts what, which data is unrecoverable>
Fix: <the exact change; for an applied migration, the new corrective migration>
```

Finding ID format: `MG-NNN` (zero-padded to 3 digits). IDs are assigned sequentially and never reused.

## Severity Guide

| Level | Meaning |
|-------|---------|
| Critical | Unrecoverable data loss, or a full-table lock, in a migration not yet applied to production |
| High | deploy-order-break with a concrete failure window; unbatched data migration over an unbounded set; ordering-conflict the runner fails or misorders on; a Critical-shape defect in an already-applied migration |
| Medium | missing-fk-index; schema-model-drift; missing down on a non-destructive up |
| Low | locking-op on a table proven bounded and tiny (evidence cited); hygiene the runner tolerates |
| Advisory | Hardening with no current failure scenario |

## Related Skills

- [security-auditor] — SQL injection, secrets, and access control; migration *security* routes there
- [perf-auditor] — query performance outside migration files routes there
- [silent-failure-hunter] — swallowed errors in application code, including around migration runners

---

[security-auditor]: ../security-auditor/README.md
[perf-auditor]: ../perf-auditor/README.md
[silent-failure-hunter]: ../silent-failure-hunter/README.md
