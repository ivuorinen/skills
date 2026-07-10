# /nitpicker migrations — Migration Auditor

Hostile single-shot audit of database schema and data migrations: assume every migration eats production until proven safe.

## When to use

- Auditing pending migrations before a deploy or release, or reviewing a PR that adds or edits schema or data migrations
- After a migration incident — a lock storm, a lost column, a failed rollback — to find its siblings before they fire
- Triggers: "audit the migrations", "is this migration safe", "review the schema changes"

Run standalone or by the `/nitpicker` default audit flow.

Out of scope: SQL injection and access control inside migrations route to `/nitpicker security`; query performance outside migration files routes to `/nitpicker perf`.

## Mindset

Locate every migration system in the repo, enumerate every migration, read each end-to-end — up and down — and cross-check ORM models against the sum of migrations and the committed schema dump. Every finding names the migration file:line, the database engine, and the concrete failure scenario: which lock blocks which traffic, which deploy order corrupts which rows, which data is unrecoverable. Static analysis only — never run a migration against any database. Fixes edit only migrations not yet applied to any shared environment; the fix for an applied migration is always a new migration.

## Defect classes

Check every audit-set migration against every class. A finding is filed only with the migration file:line, the engine, and a concrete failure scenario.

| Class                        | Definition                                                                                                                                                                                                                                                                                                                                                        | Scenario to construct                                                                                 |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **destructive-op**           | `DROP TABLE`/`DROP COLUMN`, `TRUNCATE`, or an `ALTER` narrowing a type, with no backfill, backup step, or staged rollout recorded in the migration or its accompanying change                                                                                                                                                                                     | The rows or values destroyed and the absence of any recovery path                                     |
| **irreversible**             | No down-migration, or a down that cannot restore the data the up destroyed (a down that recreates an empty column is not a rollback)                                                                                                                                                                                                                              | The up's data change versus what the down actually restores                                           |
| **locking-op**               | An operation holding a long table lock under load: Postgres `CREATE INDEX` without `CONCURRENTLY`, `SET NOT NULL` or narrowing `ALTER TYPE` (ACCESS EXCLUSIVE + rewrite), `ADD COLUMN` with a volatile default on pre-11 Postgres; MySQL `ALTER TABLE` forcing a table copy instead of `ALGORITHM=INPLACE`/`INSTANT`. The fix names the engine-specific safe form | The lock taken, its duration driver (table size), and the reads/writes it blocks                      |
| **missing-fk-index**         | A new foreign key with no index on the referencing column                                                                                                                                                                                                                                                                                                         | The parent-side `DELETE`/`UPDATE` that full-scans the child table per row                             |
| **schema-model-drift**       | ORM models/entities disagree with the sum of migrations or the committed schema dump                                                                                                                                                                                                                                                                              | The field/column pair that differs and which side production actually has                             |
| **unbatched-data-migration** | `UPDATE`/`DELETE` over an unbounded row set in one transaction or statement                                                                                                                                                                                                                                                                                       | The row-count driver, the lock/undo/WAL growth, and the replication lag it causes                     |
| **deploy-order-break**       | Migration and code that must deploy atomically under a rolling deploy: enum value removal old code still writes, `NOT NULL` on a column old code omits, a renamed column with no dual-write window                                                                                                                                                                | The old-code/new-schema (or new-code/old-schema) window and the writes that fail or corrupt inside it |
| **ordering-conflict**        | Duplicate or branching migration version numbers/timestamps across merged branches                                                                                                                                                                                                                                                                                | The two colliding migrations and what the runner does: fail, skip, or apply out of order              |

**Evidence rule.** Every finding names the migration file:line, the engine, and the concrete failure scenario. A table-size claim cites evidence (seed data, fixtures, the domain) or states its growth assumption explicitly — "the table is small" is an assumption, not a defense; file the finding and record the assumption in the scenario.

## Process

1. **Locate every migration system.** Django (`*/migrations/*.py`), Alembic (`versions/`), Rails (`db/migrate/`), Flyway (`V*__*.sql`), Liquibase (changelogs), Prisma (`prisma/migrations/`), knex, and raw SQL migration directories — a repo may hold several; audit each. Detect the engine (Postgres, MySQL, SQLite, SQL Server) from config, connection strings, or dialect imports.
2. **Enumerate the audit set.** Every migration, unless the extra instructions or the `changed-files` modifier narrow it. The drift, deploy-order, and ordering-conflict cross-checks always use the full migration history regardless of scope. Never sample; report any unread audit-set migration as unexamined in the summary and declare the run INCOMPLETE.
3. **Read every audit-set migration end-to-end.** Up and down both — including the down of a data-destroying up. Classify each statement against every defect class; for locking-op, name the exact lock and the safe form.
4. **Cross-check models vs schema.** Diff every ORM model/entity against the sum of all migrations and any committed schema dump (`schema.rb`, `structure.sql`, `schema.prisma`); every disagreement is schema-model-drift.
5. **Determine applied status per migration.** A migration on the default branch, in a released tag, reflected in the committed schema dump, or stated by the user to have run on any shared environment is applied; only migrations introduced by the current unmerged branch and never deployed anywhere shared are unapplied. When in doubt, treat as applied.
6. **File findings** via the store protocol in `_conventions.md`, using `--auditor migrations`. The finding body records the class, the engine (with a version assumption when lock behavior depends on it), and the applied status; the failure scenario is the Evidence; the Fix names the exact change — for an applied migration, the new corrective migration.
7. **Summary and fix gate.** State the run verdict (COMPLETE only if zero audit-set elements are unexamined), then run the shared apply-fixes prompt. `(s)afe` means edits to unapplied migrations that change no final schema outcome: swap in the engine-safe locking form, write a missing down, add batching bounds. Verify each fix by re-reading the edited migration against its defect class plus the migration system's offline checks when present (a validate/check command that connects to nothing) — never by running the migration. Fix edits to migration, model, and schema-dump files stay in the working tree unstaged.

## Severity guide

| Severity | Condition                                                                                                                                                                                                                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Critical | Unrecoverable data loss, or a full-table lock, in a migration not yet applied to production: destructive-op with no recovery path; irreversible down on a data-destroying up; locking-op that blocks writes for the duration of a table scan or rewrite                                                       |
| High     | deploy-order-break with a concrete corruption/failure window; unbatched-data-migration over an unbounded set; ordering-conflict the runner will fail or misorder on; the same Critical-shape defect in an already-applied migration (the damage window has passed but the corrective migration is still owed) |
| Medium   | missing-fk-index; schema-model-drift; missing down on a non-destructive up                                                                                                                                                                                                                                    |
| Low      | locking-op on a table proven bounded and tiny (evidence cited); hygiene defects in migration naming or ordering that the runner tolerates                                                                                                                                                                     |
| Advisory | Hardening with no current failure scenario: batching pattern for a still-small table, backup step before a guarded destructive op                                                                                                                                                                             |

## Fix strategy

Every migration edit happens only on approval through the fix gate. A migration applied to any shared environment (step 5) is never edited — its fix is a new migration.

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
- Running any migration or connecting to any database (`migrate`, `db:migrate`, `alembic upgrade`, `flyway migrate`, `prisma migrate`) — this command is static analysis
- Deleting a migration file
- Marking a finding fixed without re-reading the change against its defect class

## Common mistakes

These are the rationalizations this command exists to defeat. Each one is forbidden.

- **"It already ran in staging, so it's safe."** Staging proves the SQL parses; it proves nothing about production locks or loss. A lock that is instant on staging's ten thousand rows blocks writes for minutes on production's hundred million. Audit every migration against production-shaped assumptions.
- **"The ORM generated it, so it's correct."** Generators emit the naive form: non-concurrent index creation, in-place type narrowing, table-rewriting defaults. Generated migrations get the same end-to-end read as hand-written ones.
- **"Down-migrations are never used, skip checking them."** The down is the rollback story, read exactly when production is on fire. A down that drops the column the up backfilled destroys data at the worst possible moment. Read every down and verify it restores what the up changed.
- **"This table is small now, so the lock doesn't matter."** Size at audit time is not size at deploy time or a year later. File the locking-op; a bounded-and-tiny defense requires cited evidence and lands at Low, not silence.
- **"I'll only read the newest migration; the older ones already shipped."** Drift and deploy-order checks need the sum of all migrations against the models — a defect in the sum is invisible from one file. A narrowed scope bounds per-file reads only, never the cross-checks.
- **"I'll fix the applied migration file in place."** In-place edits to applied migrations desync every environment that already ran the old version and break checksum tracking (Flyway fails validation; Alembic and Rails silently diverge). The fix for an applied migration is always a new migration.
- **"Adding a column is always safe."** `ADD COLUMN` with a volatile default rewrites the table on pre-11 Postgres; `NOT NULL` without a default breaks every insert from old code during the rolling deploy. Additive is not automatically safe — check the lock and the deploy window.
- **"I'll run the migration locally to verify."** Never run migrations against any database. Verification is the end-to-end read plus the migration system's offline checks. Running it proves the local case and silently skips the production scenario the finding is about.
- **"It's raw SQL with no down framework, so reversibility is out of scope."** The framework's silence waives nothing. A destructive up without a written recovery path — companion down script, backup step, or restore procedure — is irreversible; file it.
- **"Too many migrations, I'll sample the recent ones."** Sampling is how the table-rewriting ALTER ships. Read the entire audit set; genuine time exhaustion produces named unexamined migrations and verdict INCOMPLETE, never a silent sample presented as done.
