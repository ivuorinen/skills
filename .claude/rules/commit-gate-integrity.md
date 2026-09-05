# Commit Gate Integrity

The CI `Validate` job is the authoritative enforcement gate. PostToolUse hooks
now cover both surfaces — `Write|Edit` validators on edited files, and
`post-bash-revalidate.py` on `Bash`, which re-runs the whole-tree gates when
`git status` shows a governed path dirty after a Bash edit (`sed -i`,
redirection, `git mv`). But a hook runs only inside an agent session and
pre-commit is skippable, so CI is still the only check that binds every change
on its way into a protected branch.

Never pass `--no-verify` when committing changes to skill files, version
manifests, or the findings store — it skips the pre-commit validators that guard
them. A PreToolUse hook (`deny-unsafe-git-hook.py`) denies the literal
`--no-verify` and `-n`, but treat it as a backstop rather than the binding gate:
it is bypassable through git aliases, `-c core.hooksPath=`, and stacked short
flags, so the prohibition still rests on discipline and on CI. Keep the `Validate` job a required status check on
every protected branch; a merge that bypasses it lands on `main` unvalidated —
that required check, not the local pre-commit run, is the binding gate.
