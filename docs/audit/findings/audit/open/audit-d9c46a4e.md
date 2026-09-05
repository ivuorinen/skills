---
id: audit-d9c46a4e
auditor: audit
severity: medium
category: security
area: .claude/settings.json
status: open
found: 2026-09-04
---

# The graphify binary gates every Bash, Read and Glob call and is unpinned and unverified

## Problem

Two PreToolUse hooks route every `Bash`, `Read` and `Glob` tool call through the
`graphify` binary resolved from `PATH` at invocation time. That binary can block or
allow those calls. Nothing pins or verifies which build runs. Every other executable
dependency in this repository is pinned and verified.

## Evidence

```text
PreToolUse | matcher=Bash       | command -v graphify >/dev/null || exit 0; exec graphify hook-guard search
PreToolUse | matcher=Read|Glob  | command -v graphify >/dev/null || exit 0; exec graphify hook-guard read
```

There is no version argument, no checksum, and no lockfile entry for the CLI in
`pyproject.toml`, `uv.lock`, or `package.json`. A version file exists but binds only the
vendored skill markdown, and nothing compares it to the binary:

```text
$ cat .claude/skills/graphify/.graphify_version
0.9.16
$ graphify --version
graphify 0.9.16
```

They match here by coincidence of installation order, not by enforcement.

Contrast the discipline applied everywhere else: every workflow `uses:` is a full commit
SHA with a version comment, every pre-commit `rev:` is a 40-character SHA, and the CI
opengrep binary is installed against a verified digest before it is allowed to run.

## Impact

A different or compromised `graphify` earlier on `PATH` silently takes over the decision
to permit or deny every file read, glob, and shell command in the session. The vendored
skill trust model in `.claude/rules/vendored-skills.md` governs the skill markdown, which
is inert text, and leaves unbound the one component that actually executes and enforces.
The hook fails open when the binary is absent, which is correct for portability, but that
same lookup is what makes substitution invisible.

## Fix

Have each hook command compare the binary's version to the pinned file and refuse to
proceed on a mismatch, rather than executing whatever is found:

```sh
command -v graphify >/dev/null || exit 0
[ "$(graphify --version | awk '{print $2}')" = "$(cat "$CLAUDE_PROJECT_DIR/.claude/skills/graphify/.graphify_version")" ] || {
  echo "graphify version does not match the pinned version" >&2; exit 2; }
exec graphify hook-guard search
```

That mirrors the digest verification already applied to the opengrep binary in CI, and
keeps the absent-binary no-op intact.
