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
them. A PreToolUse hook (`deny-unsafe-git-hook.py`) denies `--no-verify` and
`-n` including stacked clusters (`-nm`) and abbreviations git accepts
(`--no-veri`), `-c core.hooksPath=` and `--config-env=`, the same assignment
made through `GIT_CONFIG_*` in the environment, and an alias body that resolves
to a denied call — including a `!`-prefixed body, which is a shell command
rather than a git subcommand. A command nested in `$(...)`, backticks or a
subshell is judged as its own stage, and so is a git call behind a wrapper
(`env`, `sudo`, `xargs`, …). Five bypasses of these shapes were closed together;
`tests/test_hooks.py::test_git_guard_denies_the_reopened_bypass_classes` holds
each one.

Treat it as a backstop rather than the binding gate. It judges the command's
**text**, so a request that carries no `git` token at all is outside it, and
those are not theoretical:

- an indirection that runs git from inside something else — a shell function or
  rc alias shadowing `git`, a script the hook sees only by its own name
  (`./deploy.sh`), `eval` on a string assembled at runtime
- a wrapper outside the list `_hooklib._WRAPPERS` names

Closing the spelled-out forms raised the cost of the rewrite; it did not turn
the guard into the gate. Keep the `Validate` job a required status check on
every protected branch; a merge that bypasses it lands on `main` unvalidated —
that required check, not the local pre-commit run, is the binding gate.
