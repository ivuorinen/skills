# Plan: Keep the findings store out of PR-review noise (resolved ledger + generated mark)

Date: 2026-07-10
Status: IMPLEMENTED (chosen over the SQLite pivot; see rejection note)

## Goal

Stop audit runs from flooding PR review with finding files, without giving up
the git-native properties (diff, blame, merge, grep) of the flat-file store.
Chosen approach = **A + B**:

- **A.** Resolving a finding appends a record to an append-only
  `docs/audit/findings/resolved.jsonl` ledger and deletes the open `.md`, so the
  tree only ever holds the handful of *open* findings as files plus one ledger.
- **B.** An in-store `docs/audit/findings/.gitattributes` marks the store
  `linguist-generated`, so GitHub collapses it in PR diffs. findings.py writes
  that file itself (its own domain — it never touches the repo-root
  `.gitattributes`), and skips it when the store is gitignored.

## Why not a single SQLite database

SQLite's only real advantage — querying at scale — is unused at ~250 findings,
and it would trade away exactly the properties that matter: a binary `.db` is
not git-diffable, not line-reviewable, cannot be git-merged (parallel worktrees
would conflict), and is not byte-reproducible for the `git diff --exit-code`
gate. The ledger keeps all of those (JSONL = one text file, line-diffable,
mergeable, greppable).

## What was built

- `findings.py`: `resolve` → ledger + delete open file; `new`/`list`/`show`/
  `validate`/`index` read open files + the ledger; INDEX counts come from both;
  new subcommands `show <id>` (print an open or resolved finding) and
  `migrate-resolved` (fold a legacy `<auditor>/resolved/*.md` tree into the
  ledger). `resolved.jsonl` records are `sort_keys` JSON for stable diffs.
- Review hygiene: `ensure_store_gitattributes` self-writes the in-store mark on
  every `index`; `check_review_hygiene` warns on `validate` if the store is
  neither marked nor gitignored; both are stdlib-only (read `.gitattributes` /
  `.gitignore` text, no `git` shell-out).
- This repo's 249 resolved `.md` files migrated into the ledger; `resolved/`
  dirs removed.
- The PostToolUse findings hook now also store-validates + reindexes on a
  `resolved.jsonl` edit.
- Tests rewritten for the ledger (`test_findings.py`, 62 tests); docs updated
  (`_conventions.md`, `CLAUDE.md`, `AGENTS.md`, `README.md`, nitpicker README,
  copilot-instructions).

## Adversarial hardening

- **complexity:** One JSONL ledger + open files; no DB, no schema framework, no
  extra tables. The ledger record is self-contained (full body) so `show`
  reconstructs without git history.
- **review:** Edge cases covered — legacy `N-<n>` ids, preserved unknown
  frontmatter keys (`extra`), fenced pseudo-headings, `--force` re-resolve
  (replaces the ledger line, no duplicate), an id that is both an open file and
  a ledger record (validate flags it), malformed ledger JSON (validate flags).
- **security:** JSONL is written with the stdlib `json` module (no injection
  surface); no SQL. `.gitattributes`/`.gitignore` are read, never executed.
- **errors/leaks:** ledger append uses a context-managed handle; `write_ledger`
  is a tmp+replace atomic write; `ensure_store_gitattributes` and the rmdir of
  emptied `resolved/` dirs swallow only `OSError`.
- **concurrency:** append-only ledger minimizes merge conflicts (new lines at
  end); still one text file, so git can line-merge — the property SQLite loses.
- **contract:** `findings.py` keeps every existing subcommand signature; adds
  `show`/`migrate-resolved`. `INDEX.md` summary + open-list format unchanged
  (open findings still link to their files; resolved counts come from the
  ledger). The hook's `validate <path>` per-file form still works for open
  findings.
- **arch:** stdlib-only preserved (`check-stdlib-only` passes). The store stays
  git-native and reviewable; `.gitattributes` collapses noise without hiding
  content.
- **tests/docs:** full suite green; the migrate round-trip and hygiene checks
  are covered; docs describe the ledger model.

## Rollback / abort

- The change is uncommitted; `git checkout` restores the flat-file store and the
  249 resolved `.md` files.
- After commit: `git revert`, then re-materialize resolved files from the ledger
  if needed (a `resolved.jsonl` line carries the full finding, so a small
  exporter reconstructs the old tree).

## Open questions & accepted risks

- **ACCEPTED:** resolved findings are no longer individual reviewable files;
  they are one collapsed, generated ledger (this is the point).
- **OPEN:** consumers with a pre-existing `<auditor>/resolved/*.md` tree must run
  `findings.py migrate-resolved` once to upgrade; documented, not automatic.
