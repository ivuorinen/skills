---
paths:
  - ".claude/settings.json"
  - "scripts/hooks/**"
  - "tests/test_settings.py"
  - "tests/test_hooks.py"
---

# Hook Inventory

The blocking and reminding hooks `.claude/settings.json` registers, and what
each one does. The PostToolUse validators are listed in `CLAUDE.md` under
`## Configuration`; this file holds the PreToolUse guards and the Stop hooks.

## PreToolUse guards

These can *block* a tool call before it runs — the most behaviour-changing
entries in the file. `.claude/settings.json` holds the authoritative list;
`tests/test_settings.py` fails when one of them is configured and unnamed here:

- matcher `Bash` and the context-mode shell tools (`ctx_execute`,
  `ctx_execute_file`, `ctx_batch_execute`) — `deny-agents-path-hook.py`, which
  blocks a shell command whose
  text names `.claude/agents/` **or a full protected agent filename** —
  literally, quoted, escaped, variable-built, or glob-spelled. The text is
  matched per shell word, with the command's own variable assignments
  expanded first; a word still carrying an unresolved substitution falls back
  to a whole-command match (agent-hooks-bbb2edb0). The
  permissions deny block binds file tools only, not Bash, and it names `Edit`
  **and** `Write` rules for that tree — no `Read` rule. `Read` was removed
  deliberately in 561e285 so agent definitions can be audited in-session, which
  makes the do-not-read policy in `AGENTS.md` agent discipline for file tools,
  not a settings denial. Claude Code's permissions docs state that `Edit`
  rules apply to every built-in tool that edits files, so the `Write` entries
  are redundant belt and braces, kept because they cost nothing.
  `tests/test_settings.py` pins the exact list. So
  `find . -name release-readiness-reviewer.md -exec cat {} +` is blocked too.
  It raises the cost of reaching that tree; it does not close it. The guard
  matches tokens, so a command that locates the files by **content** rather than
  by path or name (`git ls-files | grep review | xargs cat`) carries neither
  token and passes — the one token it does carry, `review`, is a nitpicker
  command name that appears in ordinary commands constantly, so matching it
  would block routine work. Treat `.github/CODEOWNERS` plus branch protection as
  the binding control, not this hook. The same hook also blocks a shell
  **write** to any `PROTECTED_WRITE` path — `scripts/hooks/`,
  `.claude/settings.json`, `.claude/settings.local.json`,
  `.claude/skills/graphify/.graphify_version` — resolving each written operand
  from the repo root, every `cd`/`pushd` target, a context-mode `cwd` and a git
  stage's `-C`/`--work-tree` (agent-loopholes-6442185e), and treating a write
  to an ancestor directory (`mv scripts …`, `rm -rf .claude`, `git rm -r
  scripts`, and `mv`'s sources) as a write to what is under it
  (agent-loopholes-0426afd8). A `$` in a written operand is expanded from the
  variables the command binds itself; a value the command computes (`$(…)`,
  a backtick, `read`) is denied, and a variable it never binds is judged by
  the literal text around it, so `"$TMPDIR/y"` stays writable
  (agent-loopholes-d61a805c). It also refuses context-mode code in another
  language, or shell text piped into a shell (`… | bash`), that names one of
  them or the agents tree, where reading stays allowed — so the enforcement
  surface cannot be edited around via `sed -i` or a redirect. `.claude/rules/enforcement-surface-owner.md` says who
  makes those edits.
- matcher `Bash` and the context-mode shell tools — `deny-unsafe-git-hook.py`,
  which blocks `git` with `--no-verify` or `-n` (stacked clusters and the
  abbreviations git accepts included), a `-c core.hooksPath=`, `--config-env`
  (either form) or `GIT_CONFIG_*` override that disables the repository's hooks,
  a `git config` write to `core.hooksPath` or `alias.*`, an alias whose body
  resolves to any of those (a `!` shell body included, and aliases already in
  git config judged by their body), a pre-commit skip variable on `git commit`,
  in front of it or exported earlier in the same command
  (`.claude/rules/commit-gate-integrity.md` names them), `pre-commit uninstall`,
  a `git add` whose pathspec reaches the whole tree
  however it is spelled, and a push to a protected branch. It reads a command
  nested in `$(...)`, backticks or a subshell as its own stage, and judges the
  command behind a wrapper (`env`, `sudo`, `xargs`, …) as well as the wrapper,
  the command string of `sh -c`/`bash -c`/`fish --command`
  (agent-loopholes-015b8134), and a command behind a leading reserved word
  (`then`, `do`, `{`, `!`).
  Per `.claude/rules/commit-gate-integrity.md` the pre-commit validators are not
  optional; commit without the flag and fix what fails. That rule also states
  what remains open — the guard matches command text, so a request whose git
  call is not in that text (a shell function shadowing it, a script, `eval` on
  a runtime-built string, a variable exported by an earlier call) passes it;
  text piped into a shell is refused when it names git with a write word.
- matcher `Bash` — `guard-ctx-ok-hook.py`, which validates the `# ctx-ok`
  escape hatch from `.claude/rules/use-context-mode.md` and denies it on any
  verb outside its allowlist, including every read verb. Fails closed on an
  unrecognised verb, so a denial usually means route the command through
  context-mode instead — not that the marker was spelled wrong.
- matcher `Bash` and the context-mode shell tools —
  `ask-destructive-restore-hook.py`, which asks before a `git checkout` of paths
  (with or without `--`) or a `git restore` that would discard uncommitted
  tracked changes, treating pathspec magic and globs as covering every dirty
  path. It judges every restore in the command, not only the first, and
  compares against every dirty path when a git call relocates with `-C`,
  `--work-tree`, `--git-dir` or `GIT_DIR`/`GIT_WORK_TREE`
  (agent-loopholes-6ae4667d). See `.claude/rules/snapshot-before-mutating.md`:
  snapshot with `cp` instead.
- matcher `Bash` — `graphify hook-guard search`
- matcher `Read|Glob` — `graphify hook-guard read`
- matcher `mcp__(plugin_…_)?nitpicker__np_(new_finding|resolve_finding|write_index|process_sarif)`
  — `deny-stale-mcp-write-hook.py`, which denies a findings-store or SARIF MCP
  write while `git status -- skills/nitpicker/scripts` is non-empty or
  unreadable, and names the CLI command to use instead
  (`.claude/rules/mcp-stale-server.md`).
- matcher the context-mode shell tools only — `deny-unguarded-cd-hook.py`,
  which denies a script that writes (a git write, a file-changing command,
  `sed -i`, a redirect into a file) after a `cd` or `pushd` that can fail. A
  `cd` counts as guarded by `|| …`, an `&&` chain reaching the write, or an
  earlier `set -e` that no `set +e` has cleared; `find` with `-delete`/`-exec`
  and `rsync` count as writes (agent-loopholes-d707fb69). Bash is out of
  scope, since its working directory is the project; `cd x || true` still
  counts as guarded.

Every repo guard's registered command maps any exit other than 0 or 2 to 2, so a
guard that fails to run denies (`.claude/rules/hooks-fail-closed.md`). An
empty, truncated or non-object hook event denies too: every PreToolUse guard
reads it with `_hooklib.load_event_strict` (errors-4a2d2f34).

## The graphify guards

Each graphify guard opens `command -v graphify >/dev/null || exit 0`, so on a
clone without graphify installed it exits 0 and is a no-op. When graphify is on
the executable search path (`$PATH`), the guard's own exit code propagates and
can block the call.

Between those two it **pins the binary**: it compares `graphify --version`
against `.claude/skills/graphify/.graphify_version` and exits 2 on a mismatch,
telling the agent to ask the owner. The pin file is on the permissions deny list and
`PROTECTED_WRITE`, so an agent cannot re-pin it.
Without that, a different or compromised `graphify` earlier on `$PATH` silently
takes over the permit/deny decision for every file read, glob and shell command
in the session — the one executing component the vendored-skill trust model left
unbound. An **empty or missing** pin file denies rather than passes: treating an
unreadable pin as "no constraint" would make deleting one file disable the check
in silence. The ceiling is worth knowing — a version string is self-reported, so
this raises the cost of substitution and makes an accidental mismatch visible;
it is not attestation.

## Stop hooks

`stop-reminder.py` reminds about pending skill files before Claude hands back
control. Its scope is the union of the git index (`git diff --cached`), the
working tree (`git diff`) and the untracked set (`git ls-files --others`), so
**unstaged** and brand-new files count too. When git runs but fails, it
reports the skip with exit 1 rather than returning silently (audit-38c90f58).

It hands the reminder to the agent as `additionalContext` on exit 0
(`_hooklib.stop_feedback`), the form the hooks reference recommends for a hook
giving guidance: it continues the conversation as exit 2 would, but shows no
hook-error notification. A `stop_hook_active` guard keeps the reminder from
re-firing on the continuation it causes. That is one stop cycle, not one session:
the reminder repeats once per turn for as long as skill edits stay
uncommitted. That is the observed behaviour, not a broken guard.

`command-closure-reminder.py` reads the session transcript and reminds when a
command loaded through `np_read_command` has process steps, seeded with
`np_task_create`, still `pending` or `in_progress` — or none seeded. It reminds
rather than blocks, under the same once-per-cycle guard: a turn ending is not a
command ending, since a run legitimately waits on the user and on background
work across turns. It sees only runs tracked with the `np_task_*` tools, and
checks that steps were closed, not that their work was done.

## Enforcement

Gated in part. `tests/test_settings.py` fails when a PreToolUse hook registered
in `.claude/settings.json` is not named in this file, and when `CLAUDE.md` stops
pointing here. The prose describing each hook's behaviour is author discipline:
no test compares it with what the hook does.
