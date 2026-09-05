---
id: audit-fccf2da7
auditor: audit
severity: high
category: security
area: scripts/hooks/deny-unsafe-git-hook.py:130
status: open
found: 2026-09-04
---

# Every deny-unsafe-git mandate falls to a git alias, core.hooksPath, or a stacked -n

## Problem

`_denial` classifies a git call by the subcommand token that `_hooklib.skip_git_global_opts` lands on, and that helper *consumes* the value of `-c k=v` without inspecting it. Anything expressed through `-c` is therefore invisible to the guard, and no code decomposes combined short flags. All three mandates the hook exists to enforce — no `--no-verify`, no whole-tree `add`, no push to a protected branch — fall to one-line rewrites. The same helper's docstring names `-c k=v` as the case it was written to handle, so the guard consumes the option precisely in order to miss what it carries.

## Evidence

Against the live hook (exit 2 = deny, exit 0 = allowed through):

```text
git push origin main                          -> exit=2   (baseline blocked)
git commit --no-verify -m x                   -> exit=2   (literal blocked)
git commit -nm "msg"                          -> exit=0   BYPASS
git -c core.hooksPath=/dev/null commit -m x   -> exit=0   BYPASS
git -c alias.z=push z origin main             -> exit=0   BYPASS
git -c alias.c='commit --no-verify' c -m x    -> exit=0   BYPASS
git -c alias.s=add s -A                       -> exit=0   BYPASS
```

Each spelling does the blocked thing in real git. In a throwaway repo with a `pre-commit` hook that prints `PRE-COMMIT RAN` and exits 1:

```text
git commit -m base            -> PRE-COMMIT RAN, no commit   (baseline)
git commit -nm stacked        -> committed f0fdcae, hook never ran
git -c core.hooksPath=/dev/null commit -m viahookspath -> committed e814f60, hook never ran
git -c alias.c='commit --no-verify' c -m viaalias      -> committed 7f3cd4a, hook never ran
git -c alias.z=push z origin main -> reached the push transport ("Please make sure you have the correct access rights")
git -c alias.s=add s -A           -> staged untracked junk.tmp (git diff --cached --name-only)
```

The guard tests membership in a fixed set, so `-nm` matches neither element:

```text
scripts/hooks/deny-unsafe-git-hook.py:132
    if subcommand == "commit" and any(a in _NO_VERIFY for a in args):
scripts/hooks/deny-unsafe-git-hook.py:35
    _NO_VERIFY = frozenset({"--no-verify", "-n"})
```

The option value is discarded rather than judged:

```text
scripts/hooks/_hooklib.py:172-176
    while i < len(tokens):
        if tokens[i] in _VALUE_OPTS:
            i += 2
```

No test pins any of the three. `grep -rnE 'hooksPath|hookspath|alias\.|[^-]-nm' tests/ scripts/hooks/` returns one unrelated docstring hit in `tests/test_check_make_help.py`, and nothing else.

## Impact

The one PreToolUse control the repo advertises for the commit gate and the protected-branch push is defeated by spellings an agent reaches for naturally. The `core.hooksPath` and alias vectors let a local `git commit` skip every pre-commit validator — the class of hook that, per the `audit-9bc6eb39` note in CLAUDE.md, was once the only thing that caught an unredacted credential on its way into the ledger. Branch protection and the required CI `Validate` check remain binding, so this is a defeated defence-in-depth layer rather than a total breach.

## Fix

In `_denial`, judge the `-c` values instead of discarding them: have `git_calls` return the consumed global options alongside the subcommand, and deny any git call carrying `-c core.hooksPath=` (config keys are case-insensitive, so fold case) or `-c alias.<name>=<body>`, re-classifying the call against the alias body rather than the alias name. Decompose stacked short flags for `commit`: treat a token matching `-[A-Za-z]*n[A-Za-z]*` that is not a long option as carrying `-n`. Add the five payloads above to `tests/test_hooks.py` as parametrized deny cases alongside `test_git_guard_denies_no_verify`; they fail today, which is the RED step for this fix.
