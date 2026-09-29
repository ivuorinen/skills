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
`## Configuration`; this file holds the PreToolUse guards, the
enforcement-surface integrity check and the Stop hooks.

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
  `.claude/skills/graphify/.graphify_version`, and the git dir's `.git/hooks`
  holding the installed pre-commit scripts (agent-loopholes-3736b057; a linked
  worktree's hooks live outside it) — resolving each written operand
  from the repo root, every `cd`/`pushd` target, a context-mode `cwd` and a git
  stage's `-C`/`--work-tree` (agent-loopholes-6442185e), and treating a write
  to an ancestor directory (`mv scripts …`, `rm -rf .claude`, `git rm -r
  scripts`, and `mv`'s sources) as a write to what is under it
  (agent-loopholes-0426afd8). A `$` in a written operand is expanded from the
  variables the command binds itself; a value the command computes (`$(…)`,
  a backtick, `read`) is denied, and a variable it never binds is judged by
  the literal text around it, so `"$TMPDIR/y"` stays writable
  (agent-loopholes-d61a805c). A `~`, `~user` or `~+` path is expanded first,
  and one it cannot resolve counts as protected (agent-loopholes-0f3351b2). A
  `cd` target is read past `--`, expanded the same way, and tried under every
  `CDPATH` entry; a landing it cannot know makes the protected directories
  the current base (agent-loopholes-5cdfb163). Every redirection that opens a
  file for writing counts — `>`, `>>`, `>|`, `>&`, `&>`, `<>`, behind any
  descriptor number (agent-loopholes-ff4a37fd). Which commands write, and
  what, is `_hooklib.write_targets`, the model the unguarded-cd guard shares
  (agent-loopholes-6bb5ff99): besides the plain writers it knows `unlink`,
  `rsync`, `scp`, compressors, `awk -i inplace`, the output files of `curl`,
  `wget` and `sort`, and the commands that write below a directory at paths
  their input chooses — archive extraction, a `find` that deletes or runs a
  non-reader, and `patch`, which is judged by its directory the way `git
  apply` is denied (agent-loopholes-88dddd67). Such a directory counts when it
  is the checkout root or above it, so an extraction or a deleting `find`
  needs a destination outside the checkout; a `find` whose `-name` tests match
  no name on the surface is cleared. `git checkout-index` and `git read-tree -u`
  count as worktree writes. It also refuses context-mode code in another
  language, or shell text a shell reads from stdin, that names one of them or
  the agents tree, where reading stays allowed — so the enforcement surface
  cannot be edited around via `sed -i` or a redirect.
  `.claude/rules/enforcement-surface-owner.md` says who makes those edits.
- matcher `Bash` and the context-mode shell tools — `deny-unsafe-git-hook.py`,
  which blocks `git` with `--no-verify` or `-n` (stacked clusters and the
  abbreviations git accepts included), a `-c core.hooksPath=`, `include.path`
  or `includeIf.*.path` set through `-c`, `--config-env` (either form) or
  `GIT_CONFIG_*`, and `GIT_CONFIG_PARAMETERS` at all
  (agent-loopholes-3736b057), a `git config` write to any of those keys or to
  `alias.*`, an alias whose body
  resolves to any of those (a `!` shell body included, and aliases already in
  git config judged by their body), a pre-commit skip variable, `HOME` or
  `XDG_CONFIG_HOME` on `git commit`,
  in front of it or exported earlier in the same command
  (`.claude/rules/commit-gate-integrity.md` names them), `pre-commit uninstall`,
  a `git add` whose pathspec operand resolves to the whole tree (`.`, `:/`,
  `*`, the root spelled absolutely or through `$PWD`, `:(top)`, an exclude),
  and a push to a protected branch — including one routed there by a glob
  refspec, the bare `:` matching refspec, or `remote.*.push`, `push.default`
  or `branch.*.merge` set through `-c`, the environment or a `git config`
  write (agent-loopholes-3f71784c). A `git add` pathspec read from a file
  (`--pathspec-from-file`) is not judged. It reads a command
  nested in `$(...)`, backticks or a subshell as its own stage, and judges the
  command behind a wrapper (`env`, `sudo`, `xargs`, …) as well as the wrapper,
  the command string of `sh -c`/`bash -c`/`fish --command`
  (agent-loopholes-015b8134), of `eval`, of `trap 'cmd' SIG` and of a
  here-string into a shell, a command behind a leading reserved word (`then`,
  `do`, `{`, `!`, `coproc`), and what a git alias runs
  (agent-loopholes-df530242, agent-loopholes-911e2929). The stage parser,
  alias expansion included, is `_hooklib`, so the protected-write and restore
  guards see the same stages.
  Per `.claude/rules/commit-gate-integrity.md` the pre-commit validators are not
  optional; commit without the flag and fix what fails. That rule also states
  what remains open — the guard matches command text, so a request whose git
  call is not in that text (a shell function defined by an earlier call, a
  script, a string built at runtime whose text never appears, a variable
  exported by an earlier call) passes it; text a shell reads from stdin, and a
  command string built by expansion (`eval "$CMD"`), is refused when it names
  git with a write word.
- matcher `Bash` — `guard-ctx-ok-hook.py`, which validates the `# ctx-ok`
  escape hatch from `.claude/rules/use-context-mode.md` and denies it on any
  verb outside its allowlist, including every read verb. Fails closed on an
  unrecognised verb, so a denial usually means route the command through
  context-mode instead — not that the marker was spelled wrong.
- matcher `Bash` and the context-mode shell tools —
  `ask-destructive-restore-hook.py`, which asks before a `git checkout` of paths
  (with or without `--`) or a `git restore` that would discard uncommitted
  tracked changes, treating pathspec magic, globs and `--pathspec-from-file`
  (a file or stdin, abbreviations included; agent-loopholes-a79daccb) as
  covering every dirty path. It judges every restore in the command, not only
  the first, and
  compares against every dirty path when a git call relocates with `-C`,
  `--work-tree`, `--git-dir` or `GIT_DIR`/`GIT_WORK_TREE`
  (agent-loopholes-6ae4667d). A `~` target is expanded, and a restore behind an
  alias, `eval`, `coproc` or a here-string is found through the shared stage
  parser (agent-loopholes-0f3351b2, agent-loopholes-911e2929,
  agent-loopholes-df530242). See `.claude/rules/snapshot-before-mutating.md`:
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
  earlier `set -e` that no `set +e` has cleared. What counts as a write is
  `_hooklib.write_targets` and `_hooklib.redirect_targets`, shared with the
  protected-write guard (agent-loopholes-6bb5ff99, agent-loopholes-ff4a37fd).
  Bash is out of scope, since its working directory is the project;
  `cd x || true` still counts as guarded.

Still open for every text guard, and named rather than implied: a write made
by an interpreter (`python3 -c "open(…)"`) or by a script file the command
merely runs; a runner that takes a command string outside `eval`, `trap` and a
shell's `-c` or here-string (`watch`, `su -c`, `ssh`); a command substitution
inside a word, which cuts the word's stage in two (`git -C $(pwd)/scripts
checkout -- hooks`); a write through a symlink created in the same command;
and git subcommands that write the worktree from a commit rather than a path
(`git am`, `merge`, `pull`, `cherry-pick`), whose changes land in history. The
integrity check below reports what any of these changes on the surface.

Every repo guard's registered command maps any exit other than 0 or 2 to 2, so a
guard that fails to run denies (`.claude/rules/hooks-fail-closed.md`). An
empty, truncated or non-object hook event denies too: every PreToolUse guard
reads it with `_hooklib.load_event_strict` (errors-4a2d2f34).

## Enforcement-surface integrity check

`enforcement-surface-integrity.py` is the detective control behind the text
guards (agent-hooks-c8ad2907). At SessionStart it records a SHA-256 of every
file under `scripts/hooks/`, `.claude/settings.json`,
`.claude/settings.local.json` and the graphify pin; after every Bash,
context-mode shell or Write/Edit call it hashes them again and, on any file
changed, added or removed, exits 2 with `enforcement surface changed: <paths>`.
It parses no command, so it sees a change whatever spelling made it — but only
after that call ran, and it keeps reporting until the session restarts. The
baseline lives per session in the temp directory and is re-taken only on a
fresh start or `/clear`, so a compaction or resume cannot absorb a change.
`__pycache__` is not hashed. Its registrations use the fail-closed wrapper, so
a check that cannot run reports as exit 2 instead of passing.

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
in `.claude/settings.json` is not named in this file, when `CLAUDE.md` stops
pointing here, and when the integrity check loses its SessionStart baseline, a
shell or Write/Edit matcher, or its fail-closed wrapper. The prose describing each hook's behaviour is author discipline:
no test compares it with what the hook does.
