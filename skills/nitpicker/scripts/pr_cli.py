#!/usr/bin/env python3
"""CLI driving adapter for the PR fetchers: argv in, JSON on stdout, exit code back.

`fetch-pr-comments.py` and `fetch-pr-status.py` differ only in which provider
operation they name, so the accepted argument forms, `--help` handling, stdout
rendering and the 0/1/2 exit contract live here once instead of twice.

Split out of `pr_common.py` deliberately. That module is the provider *port* —
`Target`, the shared output envelopes, the credential-pinned transport — and is
imported by all three providers and by `mcp_server.py`. A delivery mechanism
belongs outside that boundary, not inside it: argv parsing, `print`, `sys.stderr`
and process exit codes are facts about running as a command, and neither a
provider nor the MCP server has any use for them. Keeping them here is what lets
`pr_common`'s docstring claim ("a library, not a CLI") stay true.

The two driving adapters stay independent: nothing here imports the MCP server,
and the MCP server does not import this. Both reach the providers through
`pr_common.provider_for`.

Stdlib-only, per `.claude/rules/use-uv-runner.md`. Not itself an entry point —
it has no `__main__` guard, because each entry point owns the `--help` text for
its own tool and passes it in.
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_common
from pr_common import Target, UsageError


def emit(payload: Any) -> None:
    """Structured data to stdout — the only thing that ever goes there."""
    print(json.dumps(payload, indent=2))


def _split_flags(argv: list[str]) -> tuple[list[str], str, str]:
    """(positional args, --platform value, --remote value). Both spellings of a
    flag are accepted (`--platform x` and `--platform=x`), and an unknown flag is
    a usage error rather than a positional — otherwise a typo'd flag would be read
    as a repository name and reported as a bad path."""
    platform = ""
    remote = "origin"
    positional: list[str] = []
    it = iter(argv)
    for arg in it:
        if arg in ("--platform", "--remote"):
            try:
                value = next(it)
            except StopIteration:
                raise UsageError(f"{arg} needs a value") from None
            if arg == "--platform":
                platform = value
            else:
                remote = value
        elif arg.startswith("--platform="):
            platform = arg.split("=", 1)[1]
        elif arg.startswith("--remote="):
            remote = arg.split("=", 1)[1]
        elif arg.startswith("-"):
            raise UsageError(f"unknown flag: {arg!r}")
        else:
            positional.append(arg)
    return positional, platform, remote


def parse_cli_args(argv: list[str]) -> tuple[Target, int]:
    """Resolve (target, pr_number) from the argument forms both CLIs accept.

    Accepted, in the order they are tried:
        <pr-url>                          — everything comes from the URL
        <pr_number>                       — repo comes from the git remote
        <owner>/<repo> <pr_number>        — also group/sub/project, or host/owner/repo
        <owner> <repo> <pr_number>        — the 1.x GitHub form, still accepted
    Plus `--platform github|gitlab|bitbucket` and `--remote <name>` anywhere.
    """
    positional, platform, remote = _split_flags(argv)

    if len(positional) == 1 and pr_common.looks_like_pr_url(positional[0]):
        host, path, number = pr_common.parse_pr_url(positional[0])
        return pr_common.make_target(host, path, platform), number
    if len(positional) == 1:
        return (
            pr_common.resolve_target_from_remote(platform, remote),
            pr_common.parse_pr_number(positional[0]),
        )
    if len(positional) == 2:
        return (
            pr_common.resolve_target(positional[0], platform),
            pr_common.parse_pr_number(positional[1]),
        )
    if len(positional) == 3:
        return (
            pr_common.resolve_target(f"{positional[0]}/{positional[1]}", platform),
            pr_common.parse_pr_number(positional[2]),
        )
    raise UsageError(
        "expected a PR URL, a PR number, or <repo> <pr_number>. "
        "Run with --help for the accepted forms."
    )


def run_cli(doc: str, operation: str, argv: list[str]) -> int:
    """Shared main() for both entry points. Returns the process exit code.

    Exit codes: 0 success, 1 runtime/API error, 2 usage error — the contract
    every shipped tool in this repo publishes.

    `--help` is handled before any argument is resolved as a repository, so the
    flag never gets read as input and answered with a path error instead of usage.

    `pr_common.provider_for` is called through the module rather than imported by
    name so a test can patch the single dispatch point.
    """
    if "--help" in argv or "-h" in argv:
        print(doc)
        return 0
    try:
        target, pr_number = parse_cli_args(argv)
    except UsageError as err:
        print(f"[error] {err}", file=sys.stderr)
        return 2
    try:
        emit(getattr(pr_common.provider_for(target), operation)(target, pr_number))
    except UsageError as err:
        print(f"[error] {err}", file=sys.stderr)
        return 2
    except Exception as err:
        print(f"[error] {err}", file=sys.stderr)
        return 1
    return 0
