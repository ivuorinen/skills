# /nitpicker x-findings-migrator — v1 Findings Migration

Migrates legacy 1.x single-document findings files
(`docs/audit/<name>-findings.md`) into the per-finding store, preserving
every piece of information the old format held. Internal command: it is not
advertised in the public command listing, but dispatches like any other.

## When to use

Run directly ("migrate the old findings", "convert 1.x findings") or when
any nitpicker command detects v1 findings files during its pre-flight check
(see `_conventions.md`) **and the user has explicitly approved migrating**.

## Consent is mandatory — no exceptions

Detection of v1 files is a **consent gate**: it blocks migration, never the
invoking audit. Migration touches many tracked files and can badly pollute
an in-flight branch or PR, so the user decides _when_ it happens, never the
agent — that decision rule holds even when the working tree is clean.

- Ask before doing anything:
  `Legacy 1.x findings files detected: <list>. Migrate them to docs/audit/findings/ now? This changes tracked files and will show up in your current diff. (y/n)`
- Wait for an explicit answer. **This overrides autonomous, goal, and
  non-interactive modes** — a `/goal` directive, a standing "work
  autonomously" instruction, or "the user asked for an audit, so migration
  is implied" is NOT consent. If no answer can be obtained, do not migrate;
  record the detection in the run summary and continue without migrating.
- Consent is per-run. Approval in an earlier session, an earlier run, or a
  memory file does not carry over.
- "n" / "later" is a normal outcome, not a failure: leave the v1 files
  untouched, note in the run summary that migration is pending, and proceed
  with the invoking command using the v2 store for new findings.
- **Silence defaults to "n"** — for this question and for every y/n prompt
  in the Process below. Declaring the user unreachable is never a path to
  "yes".
- Re-filing a v1 finding's content into the v2 store by hand (via
  `findings.py new` or file writes) **is** migration and sits behind the
  same gate — "I didn't run `migrate`" is not a defense.

## Process

```text
1. Enumerate v1 files: everything matching docs/audit/*-findings.md — the
   glob is authoritative, a partially-structured match is still v1.
   docs/audit/arch-profile.md is a profile, not findings — never migrate it.
2. Confirm with the user (see above). Stop here without consent.
3. Run the bundled tool:
     python3 "${CLAUDE_SKILL_DIR}/scripts/findings.py" migrate docs/audit/*-findings.md
   (non-Claude agents resolve the path relative to this skill's directory)
4. Verify nothing was lost:
     python3 findings.py validate
     Compare each v1 file's Summary counts (Total/Open/Fixed/Invalid)
     against the migrated per-file count the tool printed and the store
     (findings.py list). Any mismatch: report it, do not delete anything.
5. Ask separately: "Remove the migrated v1 files? (y/n)" — deletion is its
   own consent, never bundled with step 2. On yes: git rm the v1 files.
6. Ask: "Commit the migration to git? (y/n)" — never commit silently.
   Recommend a standalone commit (chore: migrate v1 findings) so the
   migration never mixes into an unrelated PR diff.
```

## What migration preserves

Everything the v1 format recorded, mapped losslessly:

| v1                                | v2                                                          |
| --------------------------------- | ----------------------------------------------------------- |
| `[ID]` (e.g. `N-042`)             | Same ID, kept as filename and `id:` (legacy IDs stay valid) |
| Severity h3 (open findings)       | `severity:` frontmatter                                     |
| `Category:` / `Area:`             | `category:` / `area:` frontmatter                           |
| `Problem/Evidence/Impact/Fix`     | The same `##` sections in the body                          |
| `Fixed:` date / pass date         | `resolved:` frontmatter                                     |
| `Notes:`                          | `## Resolution` body                                        |
| `### Pass N — date` + source file | Provenance line: `Migrated from v1 <file> (Pass N, date).`  |
| `Generated:` date                 | `found:` frontmatter                                        |

File-level `Last validated:` has no per-finding equivalent and is the only
v1 datum not carried into individual findings — state this in the summary.

## Common mistakes

- Migrating because "the goal says keep working without asking" — the
  consent rule above overrides goal mode by design, and the no-answer
  default ("n") means asking never deadlocks the goal.
- Re-filing v1 contents as "new" v2 findings to avoid the word "migrate" —
  covert migration, same gate.
- Migrating "quietly to be helpful" without surfacing the question —
  detection without the question is a defect in the run itself.
- Migrating but "not committing, so it doesn't count" — an untracked pile
  of store files still pollutes the working tree and diff; consent first.
- Deleting v1 files in the same breath as migrating — separate consent.
- Skipping the count verification because the tool exited 0.
- Treating `arch-profile.md` or any non-findings file under `docs/audit/`
  as migratable.
