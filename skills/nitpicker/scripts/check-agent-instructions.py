#!/usr/bin/env python3
"""Check the agent instruction files a session always loads.

Usage:
    check-agent-instructions.py [<project_root>]

Defaults to cwd when no argument is given.

`check-rules-anatomy.py` audits one rule file at a time. This one audits the
*set* — every instruction file the detected harnesses load each turn — because
three defects only exist across files or against a whole-set budget:

    instruction_budget    every always-loaded file's directives, counted
                          together. A harness reserves roughly 50 instructions
                          for itself, so a config past ~150 is competing with it
                          for the same attention. No single file is at fault,
                          which is why no per-file check finds it.
    position_risk         a critical rule titled in the middle 20-80% of a long
                          file. The top and bottom of a file survive; the middle
                          is where an instruction goes to be skimmed past.
    cross_file_duplicate  the same directive stated in two files. Whichever copy
                          gets edited, the other becomes a second, contradicting
                          source — and this repo already forbids the practice in
                          prose without checking it.
    dangling_import       an `@path.md` import whose target does not exist. The
                          harness skips it in silence, so the author reads their
                          own file, sees the rule referenced, and never learns it
                          was never loaded.
    circular_import       an import chain that returns to a file already on it.
                          The chain is cut at a depth limit rather than followed,
                          making what actually loads depend on the entry point.

Outputs a JSON report to stdout, diagnostics to stderr.

Harnesses covered: Claude Code, Cursor, GitHub Copilot, Gemini CLI, Windsurf,
Cline, Zed, Aider, Continue, plus the cross-agent AGENTS.md. A repo answering to
several at once is normal and every file found counts against one budget — they
compete for the same window whichever agent reads them.

Exit codes: 0 = no High/Critical findings, 1 = High or Critical found, or an
explicitly supplied <project_root> that holds no agent instruction files,
2 = usage error.
"""

import json
import re
import sys
from pathlib import Path

# Instruction surfaces per harness. This tool audits somebody else's repository,
# and which agent they run is not ours to assume: a set hardcoded to Claude Code
# answered "not an agent workspace" for Cursor, Copilot, Gemini, Windsurf, Cline
# and Zed alike — telling a user their agent config is not agent config.
#
# A pattern with no glob is a *root* file: one document read start to finish, so
# position within it is meaningful. A glob names a rules directory, where each
# file is its own unit and `check-rules-anatomy.py` is the per-file authority.
_HARNESSES: dict[str, tuple[str, ...]] = {
    "Claude Code": ("CLAUDE.md", ".claude/CLAUDE.md", ".claude/rules/*.md"),
    "Cursor": (".cursorrules", ".cursor/rules/*.mdc", ".cursor/rules/*.md"),
    "GitHub Copilot": (
        ".github/copilot-instructions.md",
        ".github/instructions/*.instructions.md",
    ),
    "Gemini CLI": ("GEMINI.md", ".gemini/GEMINI.md"),
    "Windsurf": (".windsurfrules", ".windsurf/rules/*.md"),
    "Cline": (".clinerules", ".clinerules/*.md"),
    "Zed": (".rules",),
    "Aider": ("CONVENTIONS.md",),
    "Continue": (".continuerules",),
    # AGENTS.md is the cross-agent convention rather than any one harness's, so
    # it is listed once here instead of repeated under every entry above.
    "cross-agent": ("AGENTS.md",),
}

_ROOT_FILES = frozenset(p for pats in _HARNESSES.values() for p in pats if "*" not in p)

# The harness's own instructions occupy part of the window before a repo's do.
# The budget below is the remainder, and the warn band starts where a config is
# consuming enough that the next addition is the one that costs something. The
# numbers are calibrated on Claude Code, whose reserved share is documented; for
# the other harnesses they are the best available estimate, not a measurement.
_BUDGET_ERROR = 150
_BUDGET_WARN = 100

# A rule *statement*, not a mention of one. Tested against the line with its
# markup stripped, so the directive has to be what the line opens with.
#
# Matching the word anywhere instead scores ordinary prose, and matching only a
# heading or a bolded lead-in scores nothing here: AGENTS.md states every rule as
# a plain bullet, so requiring decoration made the file structurally exempt from
# the check written for it. Position is about where a rule sits, so what matters
# is that the line *is* a rule — decoration is how a given file happens to spell
# that, and it varies by file and by harness.
_MARKUP_RE = re.compile(r"^(?:#{1,6}\s+|[-*+]\s+|\d+\.\s+|\*\*|__)+")
_CRITICAL_RE = re.compile(r"^(?:NEVER|Never|MUST|Must|Do not|DO NOT|Don't|Always|ALWAYS)\b")
_POSITION_BAND = (0.20, 0.80)
# 50 rather than a rounder number for a measured reason: AGENTS.md is 58 lines
# and holds the hit this check exists for — "Never read or modify anything under
# .claude/agents/" at 58% depth, a constraint backed by CODEOWNERS and a
# PreToolUse hook. A floor of 60 made the one file that needed checking exempt.
_POSITION_MIN_LINES = 50


def _is_rule_statement(stripped: str) -> bool:
    """True when the line opens with an unconditional directive, markup aside."""
    return bool(_CRITICAL_RE.match(_MARKUP_RE.sub("", stripped)))


# A directive: a list item, or a sentence opening with an imperative verb. Prose
# that merely mentions a rule is not one, which is why the verb set is closed
# rather than "any sentence".
_LIST_RE = re.compile(r"^([-*+]\s+|\d+\.\s+)")
_IMPERATIVE_RE = re.compile(
    r"^(Never|Always|Do not|Don't|Must|Use|Run|Keep|Add|Write|Prefer|Treat|Read|Check|Ensure)\b"
)

_MIN_DUPLICATE_LEN = 40


def _content_lines(text: str):
    """Yield (lineno, stripped) for lines outside fenced code, tables and quotes.

    A fence is closed only by a run at least as long as its opener, matching
    `check-rules-anatomy.py`. Getting this wrong in the other direction — treating
    an unclosed fence as closed — would count every code sample as instructions.
    """
    fence = ""
    for i, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if fence:
            close = re.fullmatch(r"(`{3,}|~{3,})\s*", s)
            if close and close.group(1)[0] == fence[0] and len(close.group(1)) >= len(fence):
                fence = ""
            continue
        opener = re.match(r"(`{3,}|~{3,})", s)
        if opener:
            fence = opener.group(1)
            continue
        if not s or s.startswith(("|", ">")):
            continue
        yield i, s


def _count_instructions(text: str) -> int:
    """Directives in one file, by the shape a reader would count them."""
    n = 0
    for _, s in _content_lines(text):
        if s.startswith("#"):
            continue
        if _LIST_RE.match(s) or _IMPERATIVE_RE.match(s):
            n += 1
    return n


def detect(project_root: Path) -> dict[str, list[Path]]:
    """Harness name -> its instruction files present here, harnesses with none omitted.

    A repo can answer to several at once — an AGENTS.md beside a CLAUDE.md beside
    a .cursorrules is the normal shape of a team whose members use different
    agents, and every one of those files is loaded by the agent that reads it.
    """
    out: dict[str, list[Path]] = {}
    for harness, patterns in _HARNESSES.items():
        found = []
        for pattern in patterns:
            if "*" in pattern:
                found += sorted(p for p in project_root.glob(pattern) if p.is_file())
            elif (project_root / pattern).is_file():
                found.append(project_root / pattern)
        if found:
            out[harness] = found
    return out


def _co_loaded(a: set[str], b: set[str]) -> bool:
    """True when one session can hold both files, so a duplicate contradicts itself.

    Two files read by different agents never meet: `.github/copilot-instructions.md`
    exists precisely because Copilot does not read CLAUDE.md, so text repeated
    between them is a deliberate mirror rather than a second competing source.
    Reporting that as one context window holding two rules states something false,
    which is why the check asks this question before it grades. `AGENTS.md` is the
    exception in the other direction — near enough every agent reads it, so it
    co-loads with all of them.
    """
    return bool(a & b) or "cross-agent" in a | b


def loaded_files(project_root: Path) -> list[Path]:
    """The always-loaded set present in this project, deduplicated and ordered."""
    seen: set[Path] = set()
    out = []
    for found in detect(project_root).values():
        for p in found:
            if p not in seen:
                seen.add(p)
                out.append(p)
    return out


# An `@path.md` import. Harnesses that support imports pull the target in as
# though its text were pasted at that point, and a target that does not resolve
# is skipped in silence — the author reads their own instruction file, sees the
# rule referenced, and never learns it was never loaded.
#
# Requiring a `.md` suffix is what keeps this off ordinary prose: an email
# address, a scoped npm package (`@types/node`), a Python decorator and a handle
# all carry an `@` and none of them end in `.md`. Inline code spans are stripped
# first, so `@old-rules.md` quoted as an example of the syntax is not read as a
# live import.
_IMPORT_RE = re.compile(r"(?<![\w./-])@([\w~./-]+\.md)")
_CODE_SPAN_RE = re.compile(r"`[^`]*`")


def _imports(text: str) -> list[tuple[int, str]]:
    """(lineno, target) for each `@path.md` import outside code fences and spans."""
    out = []
    for lineno, s in _content_lines(text):
        for m in _IMPORT_RE.finditer(_CODE_SPAN_RE.sub("", s)):
            out.append((lineno, m.group(1)))
    return out


def _import_findings(project_root: Path, files: list[Path]) -> list[dict]:
    """Imports that resolve to nothing, and import cycles.

    Resolution is relative to the *importing* file's directory, which is how the
    harnesses that support this resolve it. A `~` path is left alone: it points
    outside the repository at the machine running the agent, so its presence here
    would say nothing about whether it resolves there.
    """
    findings: list[dict] = []
    edges: dict[Path, list[tuple[Path, int, str]]] = {}
    queue = list(files)
    visited: set[Path] = set()

    while queue:
        path = queue.pop()
        if path in visited or not path.is_file():
            continue
        visited.add(path)
        rel = _rel_to(path, project_root)
        edges[path] = []
        for lineno, target in _imports(path.read_text(encoding="utf-8", errors="replace")):
            if target.startswith("~"):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.is_file():
                findings.append(
                    {
                        "severity": "High",
                        "code": "dangling_import",
                        "file": rel,
                        "detail": f"Line {lineno} imports @{target}, which does not exist — "
                        f"the import is skipped in silence, so every rule the target "
                        f"holds is absent from the session that reads this file",
                    }
                )
                continue
            edges[path].append((resolved, lineno, target))
            # Imported files are instruction files too, and one of them importing
            # a missing target is the same defect one level down.
            queue.append(resolved)

    findings += _import_cycles(edges, project_root)
    return findings


def _import_cycles(
    edges: dict[Path, list[tuple[Path, int, str]]], project_root: Path
) -> list[dict]:
    """One finding per import cycle, reported at the edge that closes it."""
    findings: list[dict] = []
    state: dict[Path, int] = {}  # 1 = on the current path, 2 = finished
    reported: set[tuple[Path, Path]] = set()

    def walk(node: Path) -> None:
        state[node] = 1
        for target, lineno, spelling in edges.get(node, []):
            if state.get(target) == 1:
                if (node, target) not in reported:
                    reported.add((node, target))
                    findings.append(
                        {
                            "severity": "Medium",
                            "code": "circular_import",
                            "file": _rel_to(node, project_root),
                            "detail": f"Line {lineno} imports @{spelling}, which imports its "
                            f"way back here — the chain is cut at a depth limit rather "
                            f"than followed, so what actually loads depends on where "
                            f"the walk started",
                        }
                    )
            elif target not in state:
                walk(target)
        state[node] = 2

    for node in edges:
        if node not in state:
            walk(node)
    return findings


def _rel_to(path: Path, project_root: Path) -> str:
    """`path` as a project-relative posix string, left absolute if it is outside."""
    try:
        return path.relative_to(project_root).as_posix()
    except ValueError:
        return str(path)


def _scan_file(
    rel: str,
    text: str,
    owners: dict[str, set[str]],
    seen_lines: dict[str, tuple[str, int]],
) -> list[dict]:
    """Per-line findings for one file; records its lines in `seen_lines` as it goes.

    `seen_lines` is shared across the whole set and mutated here, which is what
    makes the first file to state a line its owner and every later repeat the
    finding.
    """
    findings: list[dict] = []
    body_total = len(text.splitlines())
    # Position risk is judged on the root files only — the single documents an
    # agent reads start to finish. A rules *directory* belongs to
    # check-rules-anatomy.py, which scores it with a stricter opener rule suited
    # to that file shape. Two tools reporting the same file under different
    # definitions would disagree, and the author would have no way to tell which
    # answer was the contract.
    scored_for_position = rel in _ROOT_FILES

    for lineno, s in _content_lines(text):
        depth = lineno / body_total if body_total else 0
        if (
            scored_for_position
            and body_total >= _POSITION_MIN_LINES
            and _POSITION_BAND[0] <= depth <= _POSITION_BAND[1]
            and _is_rule_statement(s)
        ):
            findings.append(
                {
                    "severity": "Low",
                    "code": "position_risk",
                    "file": rel,
                    "detail": f'Line {lineno} ({round(depth * 100)}%): "{s[:70]}" — a '
                    f"critical rule titled mid-file is the one an agent skims past",
                }
            )
        if len(s) < _MIN_DUPLICATE_LEN or s.startswith("#"):
            continue
        prior = seen_lines.get(s)
        if prior is None:
            seen_lines[s] = (rel, lineno)
        elif prior[0] != rel:
            together = _co_loaded(owners.get(prior[0], set()), owners.get(rel, set()))
            findings.append(
                {
                    "severity": "Medium" if together else "Low",
                    "code": "cross_file_duplicate",
                    "file": rel,
                    "detail": f"Line {lineno} repeats {prior[0]}:{prior[1]} verbatim: "
                    f'"{s[:60]}" — '
                    + (
                        "two sources for one rule in a single session, and editing "
                        "either leaves the other contradicting it"
                        if together
                        else "a mirrored rule for a different agent; no session holds "
                        "both, but editing one silently leaves the other stale"
                    ),
                }
            )
    return findings


def check(project_root: Path) -> tuple[dict, bool]:
    """The report for `project_root`, and whether it blocks; (report, blocking).

    Raises ValueError when the root holds no instruction file for any known
    harness — a repo with none is not one this check has anything to say about,
    and an empty clean report would present "nothing to check" as "nothing wrong".
    """
    harnesses = detect(project_root)
    files = loaded_files(project_root)
    if not files:
        raise ValueError(
            f"{project_root} holds no agent instruction file for any known harness "
            f"({', '.join(_HARNESSES)})"
        )

    # Which harnesses read each file, so a duplicate can be judged by whether one
    # session ever holds both copies.
    owners: dict[str, set[str]] = {}
    for harness, found in harnesses.items():
        for f in found:
            owners.setdefault(f.relative_to(project_root).as_posix(), set()).add(harness)

    findings: list[dict] = []
    per_file: list[dict] = []
    seen_lines: dict[str, tuple[str, int]] = {}
    total = 0

    for path in files:
        rel = path.relative_to(project_root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        count = _count_instructions(text)
        total += count
        per_file.append({"file": rel, "instructions": count})
        findings += _scan_file(rel, text, owners, seen_lines)

    findings += _import_findings(project_root, files)

    if total > _BUDGET_ERROR:
        findings.append(
            {
                "severity": "High",
                "code": "instruction_budget",
                "file": "(always-loaded set)",
                "detail": f"{total} instructions across {len(files)} always-loaded files "
                f"(limit {_BUDGET_ERROR}). A harness reserves roughly 50 internally, so "
                f"this config competes with it. Move what is situational into a "
                f"path-scoped rule file or an on-demand skill.",
            }
        )
    elif total > _BUDGET_WARN:
        findings.append(
            {
                "severity": "Low",
                "code": "instruction_budget",
                "file": "(always-loaded set)",
                "detail": f"{total} instructions across {len(files)} always-loaded files "
                f"(warn above {_BUDGET_WARN}, limit {_BUDGET_ERROR}).",
            }
        )

    blocking = any(f["severity"] in ("High", "Critical") for f in findings)
    report = {
        "project_root": str(project_root),
        "harnesses": sorted(harnesses),
        "files": per_file,
        "total_instructions": total,
        "budget": {"warn": _BUDGET_WARN, "limit": _BUDGET_ERROR},
        "findings": findings,
        "summary": {
            "files": len(files),
            "findings": len(findings),
            "blocking": blocking,
        },
    }
    return report, blocking


def main() -> None:
    """CLI entry point: parse argv, print the report, exit per the outcome.

    Thin by design — `check` holds the logic so an MCP tool runs the same code.
    What lives only here is the CLI contract: usage on stderr with exit 2, a
    misconfigured root on stderr with exit 1, and exit 1 on a blocking finding so
    CI fails on it.
    """
    # --help is how an agent learns this script's interface
    # (https://agentskills.io/skill-creation/using-scripts). Checked before the
    # argument is read as a path, or `--help` resolves as a project root.
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return
    if len(sys.argv) > 2:
        print("Usage: check-agent-instructions.py [<project_root>]", file=sys.stderr)
        sys.exit(2)

    project_root = Path(sys.argv[1]).resolve() if sys.argv[1:] else Path.cwd()
    try:
        report, blocking = check(project_root)
    except ValueError as e:
        print(f"ERROR  {e}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"ERROR  cannot read agent instruction files: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(report, indent=2))
    sys.exit(1 if blocking else 0)


if __name__ == "__main__":
    main()
