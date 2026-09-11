# Committing Protocol — load before creating any commit

Trigger: about to run `git commit`. Binding on every commit a command creates —
the findings commit gate, a fix's code commit, and any commit made while
carrying out extra instructions. A run that creates no commit never loads this.

## Read the staged set before every commit

`git diff --cached` *is* the commit. `git status` is not (it names files, not
hunks), and intent is not (you staged what you staged, not what you meant to).
Confirm every staged hunk belongs to the message about to be written; an
unrelated hunk means the stage is wrong, not that the message needs widening —
unstage it and commit it separately. This check is not optional on a "small"
commit: the recurring failure in this repo is a commit carrying edits that
belonged to a different one, and every instance came from staging by path
(`git add <file>`, worse `git add -A` or `git commit -a`) while the file held
two unrelated edits. The file is the wrong unit. The hunk is the unit.

## Grouping means splitting by hunk

When the user asks for "smart groups", "logical commits", "split this up",
"separate commits", "one commit per X", or names any grouping, split the working
tree into one commit per concern and stage each with hunk-level precision. Never
bundle two concerns because they share a file, and never split one concern
across two commits because it spans two files. State the planned grouping — one
line per commit, with its files — before creating the first commit.

## Staging tools

Preflight `command -v git-hunk` (per Execution in `_conventions.md`) and use
whichever is present:

- **`git-hunk`** — hunks are addressed by content hash, so staging is exact and
  scriptable: `git hunk list` enumerates them, `git hunk add <hash>` stages one
  (`<hash>:3-5,8` stages selected lines of it), `git hunk reset` unstages,
  `git hunk stash` sets aside what belongs to a later commit, `git hunk commit`
  commits named hunks directly, and `git hunk list --staged` verifies. Add
  `--file <path>` to scope, `--porcelain` for machine-readable output. Read
  `git hunk help <command>` for a command's own options — `git hunk --help`
  opens a man page instead of printing inline help.
- **plain git** — `git add --patch` to stage hunk by hunk, `git add --edit` for
  a split `--patch` refuses to make, and `git restore --staged <path>` (index
  only) to unstage. Never `git restore --worktree` or `git checkout --` to
  "clean up" the stage: both overwrite the working tree and delete the very
  edits being sorted into commits.

Both paths end identically: `git diff --cached` is read, then the commit runs
with a message naming exactly what that diff contains. A commit whose staged
diff was never read is an unverified commit.
