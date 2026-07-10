# Commit Gate Integrity

The CI `Validate` job is the authoritative enforcement gate. PostToolUse hooks
fire only on Write/Edit and never on Bash edits (`sed -i`, redirection,
`git mv`), and pre-commit is skippable, so CI is the only check that binds every
change on its way into a protected branch.

Never pass `--no-verify` when committing changes to skill files, version
manifests, or the findings store — it skips the pre-commit validators that guard
them. Keep the `Validate` job a required status check on every protected branch;
a merge that bypasses it lands on `main` unvalidated.
