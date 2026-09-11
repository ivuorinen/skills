#!/usr/bin/env python3
"""Report the size of what a session loads before it does any work.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required.

`check-agent-instructions.py` counts list items and imperative directives across
the always-loaded set and fails above a limit. That is a complexity budget, and
it is blind to size: ten terse directives rewritten as ten long paragraphs score
identically and cost several times as much. This tool measures the other half.

Two payloads matter and they are measured separately:

    always-loaded   CLAUDE.md, AGENTS.md, .claude/CLAUDE.md, .claude/rules/*.md
                    — read every turn whether or not the turn needs them.
    invocation      the router plus the always-loaded shared conventions plus
                    one command file — what a single `/nitpicker <cmd>` costs
                    before it has looked at any code.

**This tool does not gate, and the numbers it prints are estimates.** Token
counts are tokenizer-specific; four characters per token is close enough to
budget against and not close enough to fail a build on. Gating on an estimate
converts an approximation into a rule and then argues with contributors about a
number nobody can reproduce. Use it to see a delta between two commits: the
direction and the magnitude are reliable even where the absolute value is not.
`--baseline` takes a previous `--json` run and prints the change.

Exit codes: 0 always for a report, 1 on an I/O error, 2 on a usage error. There
is no failure exit for a large number, deliberately.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Four characters per token. Every printed number carries the word "est" for
# this reason; see the module docstring for why nothing gates on it.
CHARS_PER_TOKEN = 4

# The files a harness reads on every turn. Names, not a glob, because the set is
# a convention rather than a directory: a stray markdown file next to CLAUDE.md
# is not loaded and must not be counted as though it were.
ALWAYS_LOADED = ("CLAUDE.md", "AGENTS.md", ".claude/CLAUDE.md", ".github/copilot-instructions.md")
RULES_GLOB = ".claude/rules/*.md"


class UsageError(Exception):
    """A bad argument, reported at exit code 2."""


def estimate_tokens(text: str) -> int:
    """Characters divided by four, rounded up. An estimate — see the module docstring."""
    return (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def _measure(path: Path, root: Path) -> dict:
    """One row: relative path, bytes, lines, estimated tokens.

    Decoded with `errors="replace"` rather than strictly. `UnicodeDecodeError`
    derives from `ValueError`, not `OSError`, so a strict decode escaped `main`'s
    handler and replaced the whole report with a traceback over one stray byte
    somewhere in the set. The question this tool answers is *how large*, and a
    replacement character answers it; the byte count comes from the raw bytes so
    it stays exact regardless.
    """
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(raw),
        "lines": text.count("\n") + 1,
        "est_tokens": estimate_tokens(text),
    }


def always_loaded(root: Path) -> list[dict]:
    """Every file the harness reads each turn, rules directory included."""
    rows = [_measure(root / name, root) for name in ALWAYS_LOADED if (root / name).is_file()]
    rows += [_measure(p, root) for p in sorted(root.glob(RULES_GLOB))]
    return rows


def _skill_dir(root: Path, skill: str) -> Path:
    for candidate in (root / "skills" / skill, root / ".claude" / "skills" / skill):
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise UsageError(f"no SKILL.md for skill {skill!r} under {root}")


# Protocols whose trigger is a *command*, not an event inside a run: these load
# every time that command runs, so they are part of its floor. The rest of the
# protocol set is trigger-conditional — `_findings-store` on the first store
# operation, `_committing` before a commit, `_documentation` before a fix — and
# a run can finish without paying any of them.
#
# Keyed here rather than derived from `_conventions.md`'s trigger table because
# that table is prose. `tests/test_check_context_tokens.py` asserts the `audit`
# entry, so the mapping fails the build if the two drift.
_ALWAYS_FOR = {"audit": ("_audit-coverage.md",), "teach": ("_teach-formats.md",)}


def invocation(root: Path, skill: str, command: str) -> list[dict]:
    """What one `/<skill> <command>` loads before touching any repository code.

    The shared conventions are included because the router loads them
    unconditionally, and so is any protocol whose trigger is the command itself
    — `audit` loads `_audit-coverage.md` at run start, mandatorily, and `audit`
    is the default command. Excluding it on the grounds that protocols are
    conditional understated the default command's floor by roughly a fifth and
    credited this repo's own conventions split with a saving it does not take.

    Trigger-conditional protocols stay out: a run that files nothing and
    commits nothing pays for neither, so counting them would report a floor no
    invocation actually reaches.
    """
    skill_dir = _skill_dir(root, skill)
    paths = [skill_dir / "SKILL.md"]
    conventions = skill_dir / "commands" / "_conventions.md"
    if conventions.is_file():
        paths.append(conventions)
    for name in _ALWAYS_FOR.get(command, ()):
        protocol = skill_dir / "commands" / name
        if protocol.is_file():
            paths.append(protocol)
    target = skill_dir / "commands" / f"{command}.md"
    if not target.is_file():
        known = sorted(p.stem for p in (skill_dir / "commands").glob("*.md"))
        raise UsageError(f"no command {command!r} in {skill}; known: {', '.join(known)}")
    paths.append(target)
    return [_measure(p, root) for p in paths]


def report(root: Path, skill: str, command: str) -> dict:
    """Both payloads plus their totals, in one JSON-serializable structure."""
    sets = {"always_loaded": always_loaded(root), "invocation": invocation(root, skill, command)}
    return {
        "root": root.name,
        "skill": skill,
        "command": command,
        "unit": "estimated tokens at 4 chars each; not a gate",
        "sets": {
            name: {
                "files": rows,
                "totals": {
                    "bytes": sum(r["bytes"] for r in rows),
                    "lines": sum(r["lines"] for r in rows),
                    "est_tokens": sum(r["est_tokens"] for r in rows),
                },
            }
            for name, rows in sets.items()
        },
    }


def _render_set(name: str, block: dict, out) -> None:
    print(f"\n{name}  ({len(block['files'])} files)", file=out)
    for row in sorted(block["files"], key=lambda r: -r["est_tokens"]):
        print(f"  {row['est_tokens']:>7,} est  {row['bytes']:>7,} B  {row['path']}", file=out)
    totals = block["totals"]
    print(f"  {totals['est_tokens']:>7,} est  {totals['bytes']:>7,} B  TOTAL", file=out)


def render(data: dict, out=None) -> None:
    """Human-readable form: one line per file, biggest first, then the total.

    `out` resolves at call time rather than defaulting to `sys.stdout` in the
    signature: a default binds the stream this module saw at import, so any
    caller that replaced `sys.stdout` afterwards — a test harness, a wrapper
    capturing output — gets nothing and no error.
    """
    out = out or sys.stdout
    print(f"Context payload — {data['skill']} / {data['command']}", file=out)
    print(f"Unit: {data['unit']}", file=out)
    for name, block in data["sets"].items():
        _render_set(name, block, out)


def _delta(current: int, previous: int) -> str:
    if previous == 0:
        return "n/a"
    return f"{(current - previous) / previous:+.1%}"


def render_delta(data: dict, baseline: dict, out=None) -> None:
    """The change against a previous `--json` run — the reading this tool is for.

    An absolute estimate is worth little; the same estimator applied to two
    commits cancels its own bias, so the delta is the number to act on.

    `out` resolves at call time; see `render` for why.
    """
    out = out or sys.stdout
    print(f"{'set':<16}{'baseline':>12}{'current':>12}{'delta':>10}", file=out)
    for name, block in data["sets"].items():
        before = baseline.get("sets", {}).get(name, {}).get("totals", {}).get("est_tokens", 0)
        after = block["totals"]["est_tokens"]
        print(f"{name:<16}{before:>12,}{after:>12,}{_delta(after, before):>10}", file=out)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="check-context-tokens",
        description="Report the estimated size of the always-loaded set and of one "
        "skill invocation. Reports only — never fails on a large number.",
        epilog="Exit codes: 0 report produced, 1 runtime/IO error, 2 usage error.",
    )
    p.add_argument("root", nargs="?", default=".", help="project root (default: cwd)")
    p.add_argument("--skill", default="nitpicker", help="skill to measure (default: nitpicker)")
    p.add_argument("--command", default="audit", help="command to measure (default: audit)")
    p.add_argument("--json", action="store_true", help="emit the report as JSON")
    p.add_argument("--baseline", help="a previous --json report; print the delta against it")
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Report to stdout, diagnostics to stderr."""
    args = _parser().parse_args(argv)
    try:
        root = Path(args.root).resolve()
        if not root.is_dir():
            raise UsageError(f"not a directory: {args.root}")
        data = report(root, args.skill, args.command)
        if args.baseline:
            baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
            # Parsing is not enough: `[]`, `null`, `123` and a bare string are all
            # valid JSON, and every one of them reaches `render_delta` as
            # something without `.get`. A truncated redirect or the wrong file
            # produced exactly those, and the reporting command answered with an
            # AttributeError.
            if not isinstance(baseline, dict):
                raise UsageError(
                    "--baseline must be a report object from a previous --json run. "
                    f"Received a JSON {type(baseline).__name__}."
                )
            render_delta(data, baseline)
        elif args.json:
            print(json.dumps(data, separators=(",", ":")))
        else:
            render(data)
    except UsageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"Error: --baseline is not valid JSON: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
