# Commit Gate Integrity

The CI `Validate` job is the authoritative enforcement gate. PostToolUse hooks
now cover both surfaces — `Write|Edit` validators on edited files, and
`post-bash-revalidate.py` on Bash and the context-mode shell tools, which
re-runs the whole-tree gates when `git status` shows a governed path dirty after
a shell edit (`sed -i`, redirection, `git mv`). But a hook runs only inside an agent session and
pre-commit is skippable, so CI is still the only check that binds every change
on its way into a protected branch.

Never pass `--no-verify` when committing changes to skill files, version
manifests, or the findings store — it skips the pre-commit validators that guard
them. A PreToolUse hook (`deny-unsafe-git-hook.py`) denies `--no-verify` and
`-n` including stacked clusters (`-nm`) and abbreviations git accepts
(`--no-veri`) — on `git commit` and `git am`, and in its long forms on `merge`,
`pull`, `rebase` and `cherry-pick`, where `-n` means something else — and
`git commit-tree`, which writes a commit no hook sees
(agent-loopholes-4e3689a1). Plain `git am` stays allowed. It also denies
`-c core.hooksPath=` and `--config-env` in either form, the same
assignment made through `GIT_CONFIG_*` in the environment, a `git config` write
to `core.hooksPath` or `alias.*`, and an alias body that resolves to a denied
call — spelled in the command or already in git config, and including a
`!`-prefixed body, which is a shell command rather than a git subcommand. When
git config cannot be read, a subcommand that is not a git command is denied,
since it may be an alias nobody could judge (agent-loopholes-92626f23). It
also denies `SKIP=` or a `PRE_COMMIT_*` variable on `git commit` and the other
commit-making subcommands (`am`, `merge`, `pull`, `rebase`, `cherry-pick`) — in
front of it or exported earlier in the same command — and `pre-commit
uninstall`. A
command nested in `$(...)`, backticks or a subshell is judged as its own stage,
and so is a git call behind a wrapper (`env`, `sudo`, `xargs`, …), behind
`coproc`, inside a command string (`bash -c '…'`, `fish --command`, `eval`,
`trap 'cmd' SIG`, a here-string into a shell) or inside a git alias's body
(agent-loopholes-df530242, agent-loopholes-911e2929). Text a shell reads from
stdin (`… | bash`, `source <(…)`, a heredoc) and a command string built by
expansion (`eval "$CMD"`) cannot be tokenized, so they are refused whenever
they name git with a write word.
`tests/test_hooks.py::test_git_guard_denies_the_reopened_bypass_classes` and
`test_git_guard_unwraps_eval_source_coproc_and_here_strings` hold these shapes.

Treat it as a backstop rather than the binding gate. It judges the command's
**text**, so a request whose git call is not in that text is outside it, and
those are not theoretical:

- an indirection that runs git from inside something else — a shell function or
  rc alias defined by an earlier call, a script the hook sees only by its own
  name (`./deploy.sh`), a string assembled at runtime whose text never appears
  in the command (`eval "$(cat cmd.txt)"`), a variable exported by an earlier
  call
- a wrapper outside the list `_hooklib._WRAPPERS` names, or a runner that
  takes a command string the guard does not open (`watch`, `su -c`, `ssh`)

`enforcement-surface-integrity.py` reports a change to the hooks or settings
after the call that made it, whatever the spelling; it cannot stop a commit.

Closing the spelled-out forms raised the cost of the rewrite; it did not turn
the guard into the gate. Keep the `Validate` job a required status check on
every protected branch; a merge that bypasses it lands on `main` unvalidated —
that required check, not the local pre-commit run, is the binding gate.
