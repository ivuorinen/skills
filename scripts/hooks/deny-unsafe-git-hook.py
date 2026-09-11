#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PreToolUse hook — block the two git-write mandates the rules declare unenforced.

1. `git commit --no-verify` / `-n` skips the pre-commit validators that guard
   skill files, the version manifests, and the findings store
   (.claude/rules/commit-gate-integrity.md, which states no in-session hook
   enforces it).
2. `git push` onto a protected branch
   (skills/nitpicker/commands/cr.md Step 6: never push directly to main/master).
3. `git add -A` / `--all` / `.` — staging the whole tree is a recurring source
   of commits carrying files the change never touched: scratch output, local
   config, editor artifacts. Explicit pathspecs and `git add -u` (tracked files
   only) stay allowed.

Tokenising lives in _hooklib.git_calls, shared with the sibling guards.

Blocks with exit 2 + stderr, matching deny-agents-path-hook.py — for PreToolUse
that is a deny. Fails closed: malformed stdin or an internal error also exits 2,
because a guard that exits 0 on exception enforces nothing.
"""

import functools
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (  # type: ignore[import-not-found]
    _VALUE_OPTS,
    git_calls,
    load_event,
    repo_root,
    shell_stages_with_env,
    skip_git_global_opts,
)

REPO_ROOT = repo_root()
PROTECTED = frozenset({"main", "master"})
_NO_VERIFY = frozenset({"--no-verify", "-n"})
# git accepts any UNAMBIGUOUS abbreviation of a long option, so `--no-veri` runs
# `--no-verify` and a membership test against the full spelling matches neither.
# Generated from `--no-v` rather than from a shorter stem: `--no-verbose` also
# exists on `git commit`, so git itself rejects anything shorter as ambiguous.
# Erring longer would leave a working bypass; erring shorter only refuses a
# command git would refuse too.
_NO_VERIFY_PREFIXES = frozenset(
    "--no-verify"[:n] for n in range(len("--no-v"), len("--no-verify") + 1)
)
# Arguments that stage every change rather than a named path. `.` is included
# deliberately: from the repo root it stages the same set `-A` does, so blocking
# only the flags would move the hazard to `git add .` instead of removing it.
# `:/` is git's whole-repo pathspec magic — the same thing spelled differently.
_ADD_ALL = frozenset({"-A", "--all", "--no-ignore-removal", ".", ":/"})


_HOOKSPATH_DENIAL = (
    "  DENIED  git -c {key}={value} disables the repository's hooks.\n"
    "          The pre-commit validators are not optional — see\n"
    "          .claude/rules/commit-gate-integrity.md. Commit without the\n"
    "          override and fix what fails."
)

_ALIAS_NOTE = "\n          Reached through a git alias; the alias body was judged, not its name."

_ALIAS_DEPTH_DENIAL = (
    "  DENIED  git alias nesting exceeded the guard's depth limit.\n"
    "          An alias body that defines further aliases cannot be judged to the\n"
    "          end, so it is refused rather than allowed unexamined."
)


def _norm_pathspec(arg: str) -> str:
    """Fold the whole-tree pathspec spellings onto one comparable form.

    `git add ./`, `git add .//` and `git add :/.` stage exactly what `git add .`
    stages, so comparing raw tokens let three spellings through a check the
    module docstring declares blocked. deny-agents-path-hook.py already strips a
    leading `./` before comparing paths; this keeps the two guards agreeing on
    identical input.
    """
    if arg.startswith(":/"):
        return ":/" if not arg[2:].strip("./") else arg
    s = arg
    while s.startswith("./"):
        s = s[2:]
    return s.rstrip("/") or "."


# Push modes that name no refspec and update protected branches regardless of HEAD.
_ALL_REFS = frozenset({"--all", "--mirror"})

_COMMIT_DENIAL = (
    "  DENIED  git commit --no-verify skips the pre-commit validators that guard\n"
    "          skill files, version manifests, and the findings store.\n"
    "          See .claude/rules/commit-gate-integrity.md — commit without the\n"
    "          flag, or fix what pre-commit reports."
)
_PUSH_DENIAL = (
    "  DENIED  push targets a protected branch (HEAD is '{branch}').\n"
    "          Open a PR from a feature branch instead — see cr.md Step 6."
)
_ADD_DENIAL = (
    "  DENIED  `git add {arg}` stages the whole tree, including files this change\n"
    "          never touched — scratch output, local config, editor artifacts.\n"
    "          Stage what you actually changed: git add <path> [<path> ...]\n"
    "          `git add -u` restages tracked files only, if that is what you meant."
)


@functools.cache
def _current_branch() -> str | None:
    """HEAD's branch. Cached: a denial resolves it once to decide and again to
    name the branch in the message, and this hook runs on every Bash call."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _head_is_protected() -> bool:
    """HEAD decides when no refspec does. An unresolvable HEAD blocks — the guard
    cannot prove the push is safe."""
    branch = _current_branch()
    return branch is None or branch in PROTECTED


def _ref_target(ref: str) -> str:
    """Destination branch a refspec names: `+src:refs/heads/main` -> `main`."""
    return ref.split(":")[-1].lstrip("+").removeprefix("refs/heads/")


def _push_targets_protected(args: list[str]) -> bool:
    """True when the push could land on a protected branch.

    EVERY refspec is a target, not just the first: `git push origin feature main`
    reaches main through its second one, and `git push origin f:f main:main`
    through the second colon form. `--all`/`--mirror` push every matching ref, so
    they are protected whatever HEAD is. A bare `HEAD` refspec resolves through
    the current branch, as does a push with no refspec at all.
    """
    if any(a in _ALL_REFS for a in args):
        return True
    operands = [a for a in args if not a.startswith("-")]
    if len(operands) < 2:
        return _head_is_protected()
    targets = [_ref_target(ref) for ref in operands[1:]]
    if any(t in PROTECTED for t in targets):
        return True
    return "HEAD" in targets and _head_is_protected()


# Short options of `git commit` that consume the next characters as their value.
# Scanning a cluster stops at one of these, so `-cn` reads as `-c n` (reuse
# message from commit "n") rather than as a stacked `-n`.
_COMMIT_VALUE_SHORTS = frozenset("CcFmtSu")

# Config keys that disable the hooks the commit gate depends on. Git config keys
# are case-insensitive, so comparison is case-folded.
_HOOKS_DISABLING = ("core.hookspath",)

# The environment reaches the same setting `-c` does. `GIT_CONFIG_COUNT` plus
# `GIT_CONFIG_KEY_<n>`/`GIT_CONFIG_VALUE_<n>` assigns any config key, and
# `GIT_CONFIG_GLOBAL`/`GIT_CONFIG_SYSTEM` repoint config wholesale at a file the
# caller wrote. Both disable the pre-commit gate exactly as
# `git -c core.hooksPath=/dev/null` does, which this guard blocks.
_HOOKS_DISABLING_FILES = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")
_ENV_DENIAL = (
    "  DENIED  {var} disables the repository's hooks through the environment.\n"
    "          Same effect as `git -c core.hooksPath=…`, which this guard blocks.\n"
    "          The pre-commit validators are not optional — see\n"
    "          .claude/rules/commit-gate-integrity.md."
)


def _env_denial(env: dict[str, str]) -> str | None:
    """Denial for a hooks-disabling assignment in the stage's environment prefix.

    Every `GIT_CONFIG_KEY_<n>` present is inspected rather than the first
    `GIT_CONFIG_COUNT` of them: the count is chosen by the same caller as the
    keys, so trusting it to bound the scan lets a mismatched pair hide a key
    from the guard while git still reads it.
    """
    for name, value in env.items():
        if name.startswith("GIT_CONFIG_KEY_") and value.strip().lower() in _HOOKS_DISABLING:
            return _HOOKSPATH_DENIAL.format(
                key=value.strip().lower(),
                value=env.get(name.replace("_KEY_", "_VALUE_"), ""),
            )
        if name in _HOOKS_DISABLING_FILES:
            return _ENV_DENIAL.format(var=name)
    return None


def _global_config(tokens: list[str], env: dict[str, str] | None = None) -> list[tuple[str, str]]:
    """Every `-c key=value` assignment sitting before the subcommand, key folded.

    `skip_git_global_opts` consumes the value of `-c` without inspecting it, so
    everything expressed through `-c` was invisible to this guard — which is how
    `git -c core.hooksPath=/dev/null commit` and `git -c alias.z=push z` both
    reached real git untouched.

    `--config-env=<key>=<var>` names an environment variable rather than a
    value, so it is resolved through `env` before being recorded. Recording the
    variable *name* is what let `ALIAS_BODY=push git
    --config-env=alias.z=ALIAS_BODY z origin main` through: `_alias_denial`
    inspected the literal string `ALIAS_BODY`, found no subcommand in it, and
    never saw the protected-branch push. An unresolvable name keeps its literal
    spelling — the variable is then set outside this command's text, which is
    the same reach the guard's docstring already records as open.
    """
    env = env or {}
    pairs: list[tuple[str, str]] = []
    i = 1
    while i < len(tokens):
        opt = tokens[i]
        if opt in _VALUE_OPTS:
            if opt == "-c" and i + 1 < len(tokens) and "=" in tokens[i + 1]:
                key, _, value = tokens[i + 1].partition("=")
                pairs.append((key.strip().lower(), value))
            i += 2
        elif opt.startswith("-"):
            if opt.startswith("--config-env=") or opt.startswith("-c="):
                key, _, value = opt.split("=", 1)[1].partition("=")
                if opt.startswith("--config-env="):
                    value = env.get(value, value)
                pairs.append((key.strip().lower(), value))
            i += 1
        else:
            break
    return pairs


def _carries_no_verify(args: list[str]) -> bool:
    """True when any argument carries `-n`, stacked, standalone, or abbreviated.

    `-nm "msg"` is `--no-verify` plus `-m`, and a membership test against
    {"--no-verify", "-n"} matches neither. Neither does it match `--no-veri`,
    which git accepts as an abbreviation of the same option — the cluster scan
    below is entered only when `arg[1] != "-"`, so nothing here saw a long
    option that was not spelled in full.
    """
    for arg in args:
        if arg in _NO_VERIFY or arg in _NO_VERIFY_PREFIXES:
            return True
        if len(arg) > 1 and arg[0] == "-" and arg[1] != "-":
            for char in arg[1:]:
                if char == "n":
                    return True
                if char in _COMMIT_VALUE_SHORTS:
                    break
    return False


def _denial(subcommand: str, args: list[str]) -> str | None:
    """The message to block this git call with, or None to allow it."""
    if subcommand == "commit" and _carries_no_verify(args):
        return _COMMIT_DENIAL
    if subcommand == "add":
        staged_all = [a for a in args if _norm_pathspec(a) in _ADD_ALL]
        if staged_all:
            return _ADD_DENIAL.format(arg=staged_all[0])
    if subcommand == "push" and _push_targets_protected(args):
        return _PUSH_DENIAL.format(branch=_current_branch() or "unknown")
    return None


def _deny(reason: str) -> None:
    """Print the denial and exit 2, which is how a PreToolUse hook blocks a call."""
    print(reason, file=sys.stderr, flush=True)
    sys.exit(2)


def _alias_denial(raw: str, args: list[str], depth: int) -> str | None:
    """Denial for what an invoked alias BODY runs, or None to allow it.

    Split from `_global_denial` because the two shapes of body are two different
    questions and together they put that function past the repo's complexity
    ceiling — the same reason `_global_denial` was itself split from `main`.

    A `!`-prefixed body is a SHELL command, not a git subcommand: `shlex.split`
    yields `!git`, which matches no subcommand, so the whole class was allowed.
    It is also the more capable spelling — the body can carry a full pipeline —
    so it goes back through the same machinery the outer command did rather than
    through `_denial` alone.

    The call's own arguments belong AFTER the alias body: `push` alone targets no
    branch, `push origin main` does.
    """
    if not raw:
        return None
    if raw.startswith("!"):
        if depth >= _MAX_ALIAS_DEPTH:
            return _ALIAS_DEPTH_DENIAL
        body = raw[1:]
        for inner_env, inner_tokens in shell_stages_with_env(body):
            if (reason := _global_denial(inner_tokens, inner_env, depth + 1)) is not None:
                return reason + _ALIAS_NOTE
        for inner_sub, inner_args in git_calls(body):
            if (reason := _denial(inner_sub, inner_args + args)) is not None:
                return reason + _ALIAS_NOTE
        return None
    body_tokens = shlex.split(raw)
    if body_tokens and (reason := _denial(body_tokens[0], body_tokens[1:] + args)):
        return reason + _ALIAS_NOTE
    return None


# An alias body may define another alias, so the recursion below needs a
# ceiling. Two is already past anything a real alias does; the cap exists so a
# crafted body cannot spin the guard, not to support depth.
_MAX_ALIAS_DEPTH = 4


def _global_denial(
    tokens: list[str], env: dict[str, str] | None = None, depth: int = 0
) -> str | None:
    """Denial for what a git stage's *global options and environment* carry.

    Split from `main` because the branches here pushed it past the repo's
    complexity ceiling, and because this is a separate question from the one
    `_denial` answers: `_denial` judges a subcommand, this judges the `-c`
    assignments and `GIT_CONFIG_*` variables sitting in front of it — which is
    precisely where the bypasses lived.
    """
    if env and (reason := _env_denial(env)) is not None:
        return reason
    if Path(tokens[0]).name != "git":
        return None
    config = _global_config(tokens, env)
    for key, value in config:
        if key in _HOOKS_DISABLING:
            return _HOOKSPATH_DENIAL.format(key=key, value=value)

    index = skip_git_global_opts(tokens, 1)
    if index >= len(tokens):
        return None
    subcommand, args = tokens[index], tokens[index + 1 :]
    # An alias is judged by what it *runs*, and only when it is actually
    # invoked: `-c alias.z=push z origin main` names a subcommand `z` that
    # matches nothing, so the call reached real git untouched. The call's own
    # arguments belong after the alias body — `push` alone targets no branch,
    # `push origin main` does.
    aliases = {k.split(".", 1)[1]: v for k, v in config if k.startswith("alias.") and "." in k}
    return _alias_denial(aliases.get(subcommand, ""), args, depth)


def main() -> None:
    """Block the git writes the rules declare unenforced.

    Every git invocation in the command is judged, not just the first:
    `echo hi && git push origin main` reaches a protected branch through its
    second stage, and a guard reading only stage one would pass it. A command
    nested in `$(...)`, backticks or a subshell is a stage too, and so is the
    git call behind a wrapper — see `_hooklib.shell_stages_with_env`. Exit 2 is
    a PreToolUse deny.
    """
    data = load_event()
    if data is None:
        return  # not a parseable event — nothing to judge

    command = (data.get("tool_input") or {}).get("command") or ""
    if not command:
        return

    for env, tokens in shell_stages_with_env(command):
        reason = _global_denial(tokens, env)
        if reason is not None:
            _deny(reason)

    for subcommand, args in git_calls(command):
        reason = _denial(subcommand, args)
        if reason is not None:
            _deny(reason)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # fail closed — an internal error must not allow the call
        print(f"  DENIED  git guard failed internally: {exc}", file=sys.stderr, flush=True)
        sys.exit(2)
