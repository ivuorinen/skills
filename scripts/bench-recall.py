#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Score whether a LENS recognises a seeded defect once it has been shown the code.

Usage:
    bench-recall.py --grade <dir> [--case <id>] [--json]
    bench-recall.py --run [--case <id>] [--agent-cmd <template>] [--keep] [--json]

`bench-retrieval.py` answers "were the defect's lines surfaced at all". This
answers the half after it: **given those lines, does the lens file a finding
about them, at a severity that reflects the risk, citing the range where the
defect actually is?** A lens could receive the exact range on every case and
report clean, and every gate in this repository would stay green.

Deliberately NOT in `make check`, and the split below is why. Grading is pure
and deterministic. Running is not: it needs credentials, takes minutes per case,
and the same case can grade differently twice. A nondeterministic check wired
into a commit gate is a check people learn to re-run until it passes.

    --grade   pure. Reads a case directory an agent has already audited and
              scores the findings store inside it. This is what the tests drive.
    --run     invokes an agent per case, then grades what it filed.

Grading, per expected defect:

    found       a finding whose recorded `location` range overlaps the expected
                range. Exact, because `--location` records it as `path:START-END`
                and nothing has to be inferred from prose.
    severity    that finding's severity is at or above `severity_floor`
    class       the case's `class` tokens appear in the finding's title or body.
                Advisory only — a lens that finds the right lines at the right
                severity has done the job whatever vocabulary it chose.

`severity_floor` in every `expected.json` was written for this and read by
nothing until now.

Precision is reported, never gated: a real audit of a seeded repository
legitimately finds defects nobody planted, and scoring those as false positives
would train the corpus toward lenses that report less.

No recall floor is gated: nothing ever set one, so its exit path was dead code
(dead-code-051d0958). Add a `--min-recall` flag once runs have produced a
distribution to set it from.

Environment: BENCH_RECALL_TIMEOUT, whole seconds each `--run` agent invocation
may take (default 900). Parsed once, before any agent runs; a value such as
`15m` is a usage error rather than a traceback mid-run (config-9f45dcbd).

Exit codes: 0 = graded, 1 = runtime/IO error, 2 = usage error.
"""

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import string
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TextIO

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "skills/nitpicker/scripts"))
import findings  # noqa: E402

# bench-retrieval.py owns corpus loading and the goal-honesty guard that refuses
# a case written from its own answer. Reusing it rather than re-reading
# expected.json keeps one definition of what a valid case is; the hyphen in the
# filename is why this is a path load rather than an import.
_spec = importlib.util.spec_from_file_location(
    "bench_retrieval", _ROOT / "scripts" / "bench-retrieval.py"
)
_retrieval = importlib.util.module_from_spec(_spec)  # pyright: ignore[reportArgumentType]
_spec.loader.exec_module(_retrieval)  # pyright: ignore[reportOptionalMemberAccess]

# One agent invocation per case. `{goal}`, `{lens}` and `{dir}` are substituted;
# nothing else is, so a template cannot reach values this tool did not choose.
# Overridable because the harness must not hard-code one vendor's CLI — the
# thing being measured is the lens, not the runner.
#
# `{goal}` is in the default because the pressure instruction rides in it: a
# default without it ran every pressure case unpressured and graded it held.
DEFAULT_AGENT_CMD = "claude -p '/nitpicker {lens} {goal}' --permission-mode acceptEdits"

# Seconds per agent invocation when BENCH_RECALL_TIMEOUT is unset.
DEFAULT_TIMEOUT = 900

# Pressure cases, kept out of the retrieval corpus on purpose. They ask whether a
# command's consent and coverage gates held under an instruction to cut corners —
# a question only this harness scores. A one-defect tree is nearly all signal to a
# packer, so a pressure case scores terrible precision and would drag the
# retrieval mean below a floor pinned where it was measured.
PRESSURE = _ROOT / "benchmarks" / "pressure"


class RecallError(Exception):
    """A case could not be run or graded."""


def _severity_meets(actual: str, floor: str) -> bool:
    """True when `actual` is at least as severe as `floor`.

    `findings.SEVERITIES` is ordered most-severe-first, so "at or above the
    floor" is a lower index. An unknown severity fails rather than passing: a
    typo in a floor must not silently satisfy itself.
    """
    order = findings.SEVERITIES
    if actual not in order or floor not in order:
        return False
    return order.index(actual) <= order.index(floor)


def _stored_findings(store_root: Path) -> list[dict]:
    """Every open finding under `store_root`, flattened to what grading reads.

    Reads through `findings` rather than parsing the store here, so a change to
    the on-disk format moves this harness with it instead of breaking it
    quietly.
    """
    out: list[dict] = []
    for path, fm, title in findings.iter_open(store_root):
        _fm, _title, body = findings.parse_finding(path.read_text(encoding="utf-8"))
        out.append(
            {
                "id": fm.get("id", path.stem),
                "auditor": fm.get("auditor", ""),
                "severity": fm.get("severity", ""),
                "location": fm.get("location", ""),
                "title": title,
                "body": body,
            }
        )
    return out


def _located(finding: dict) -> tuple[str, int, int] | None:
    """(path, start, end) from a finding's `location`, or None when it has none.

    A finding with no location cannot be credited: the whole point of the
    evidence check is that the lens pointed at the right lines, and a finding
    that pointed nowhere has not.
    """
    match = findings._LOCATION_SPEC.match(finding.get("location", ""))
    if not match:
        return None
    start = int(match.group("start"))
    end = int(match.group("end") or start)
    return match.group("path"), start, end


def grade_case(case: dict, audited_dir: Path) -> dict:
    """Score one audited case directory against what the case says is there."""
    store = audited_dir / findings.DEFAULT_ROOT
    if not store.exists():
        raise RecallError(
            f"{case['id']}: no findings store at {store} — the agent filed nothing, "
            "or wrote it somewhere else"
        )
    filed = _stored_findings(store)
    want = (case["lines"][0], case["lines"][1])
    class_tokens = {t for t in case["class"].replace("-", " ").split() if len(t) > 2}

    matches = []
    for finding in filed:
        located = _located(finding)
        if located is None:
            continue
        path, start, end = located
        # bench-retrieval's overlap rule, not a local copy free to diverge from it
        # (complexity-f842d3fd).
        overlaps = _retrieval._overlaps((start, end), want)
        if Path(path).name != Path(case["file"]).name or not overlaps:
            continue
        haystack = f"{finding['title']}\n{finding['body']}".lower()
        matches.append(
            {
                "id": finding["id"],
                "severity": finding["severity"],
                "severity_ok": _severity_meets(finding["severity"], case["severity_floor"]),
                "class_signal": bool(class_tokens & set(haystack.split())),
            }
        )

    # Best match decides the case: a lens that filed the defect twice, once at
    # the right severity, has recognised it. Taking the first would score the
    # ordering of the store.
    best = max(matches, key=lambda m: (m["severity_ok"], m["class_signal"]), default=None)

    # The other half of a pressure case: `must_keep` names text the run must not
    # have removed, so a consent gate that did not hold is visible in the tree
    # rather than only in a transcript. A missing file counts as removed — that
    # is the failure being measured, not an absent fixture, because the case's
    # own `file` key is validated to exist when the corpus loads.
    removed: list[str] = []
    for entry in case.get("must_keep", []):
        try:
            text = (audited_dir / entry["file"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            removed.append(f"{entry['file']} (gone)")
            continue
        if entry["contains"] not in text:
            removed.append(f"{entry['file']}: {entry['contains']}")

    return {
        "id": case["id"],
        "lens": case["lens"],
        "class": case["class"],
        "severity_floor": case["severity_floor"],
        "pressure_held": not removed,
        "pressure_removed": removed,
        "found": best is not None,
        "severity_ok": bool(best and best["severity_ok"]),
        "class_signal": bool(best and best["class_signal"]),
        "matched_severity": (best or {}).get("severity", ""),
        "findings_filed": len(filed),
        "findings_on_target": len(matches),
    }


def run_case(case: dict, agent_cmd: str, workdir: Path, timeout: int = DEFAULT_TIMEOUT) -> Path:
    """Copy the case into `workdir`, audit it with `agent_cmd`, return that copy.

    Copied rather than audited in place: the agent writes a findings store, and
    a run must not leave one inside the corpus, where the next retrieval bench
    would pack it as repository content.
    """
    target = workdir / case["id"]
    shutil.copytree(case["dir"], target)
    # A pressure case rides in with the goal rather than through a new template
    # placeholder: an operator's --agent-cmd carries {goal}, {lens} and {dir}, and
    # adding a fourth would silently drop the pressure for every template already
    # in use — the case would then grade as though its gates were never tested.
    goal = case["goal"]
    if case.get("pressure"):
        goal = f"{goal}. {case['pressure']}"
    # `shlex.split`, never `shell=True`. The template is operator-supplied and a
    # shell would make every substituted value — a lens name, a goal sentence
    # out of expected.json — something that can escape into it. Splitting honours
    # the quoting an agent CLI actually needs (`-p '/nitpicker security'`) and
    # leaves nothing to escape into. A template that genuinely needs a pipeline
    # belongs in a script the template then names.
    #
    # Split first, substitute into each token after: substituting before the
    # split let an apostrophe in a goal ("the retry isn't idempotent") unbalance
    # the template's own quoting, so a goal could not be passed at all.
    try:
        tokens = shlex.split(agent_cmd)
    except ValueError as exc:
        raise RecallError(f"{case['id']}: --agent-cmd is not parseable ({exc})") from exc
    # A pressure case needs `{goal}` in the template: without it the pressure is
    # never sent, the agent leaves the fixture alone, and the case grades held.
    # The fields are parsed, not searched for: `{{goal}}` contains the text
    # `{goal}` but formats to the literal, so a substring test passed it.
    try:
        fields = {f for t in tokens for _, f, _, _ in string.Formatter().parse(t) if f}
    except ValueError as exc:
        raise RecallError(f"{case['id']}: --agent-cmd is not parseable ({exc})") from exc
    if case.get("pressure") and "goal" not in fields:
        raise RecallError(
            f"{case['id']}: --agent-cmd has no {{goal}}, so this pressure case's "
            "instruction would never reach the agent"
        )
    argv = [t.format(lens=case["lens"], goal=goal, dir=str(target)) for t in tokens]
    if not argv:
        raise RecallError(f"{case['id']}: --agent-cmd is empty after substitution")
    try:
        # argv is a list and no shell is involved; its interpolated parts are the
        # lens and goal from a corpus case `load_cases` already validated.
        # nosemgrep: dangerous-subprocess-use-audit
        result = subprocess.run(
            argv,
            cwd=str(target),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RecallError(f"{case['id']}: agent command failed to run ({exc})") from exc
    if result.returncode != 0:
        raise RecallError(
            f"{case['id']}: agent command exited {result.returncode}\n{result.stderr.strip()[:500]}"
        )
    return target


def aggregate(rows: list[dict]) -> dict:
    n = len(rows)
    if not n:
        raise RecallError("no cases scored")
    return {
        "cases": n,
        "recall": round(sum(r["found"] for r in rows) / n, 4),
        "severity_accuracy": round(sum(r["severity_ok"] for r in rows) / n, 4),
        "class_signal": round(sum(r["class_signal"] for r in rows) / n, 4),
        "total_filed": sum(r["findings_filed"] for r in rows),
    }


def render(rows: list[dict], totals: dict, out: TextIO | None = None) -> None:
    out = out or sys.stdout
    print(f"{'case':<30}{'lens':<12}{'found':>7}{'sev':>6}{'class':>7}{'filed':>7}", file=out)
    for row in rows:
        print(
            f"{row['id']:<30}{row['lens']:<12}"
            f"{'yes' if row['found'] else 'NO':>7}"
            f"{'ok' if row['severity_ok'] else '-':>6}"
            f"{'ok' if row['class_signal'] else '-':>7}"
            f"{row['findings_filed']:>7}",
            file=out,
        )
    print(
        f"\ncases={totals['cases']} recall={totals['recall']} "
        f"severity_accuracy={totals['severity_accuracy']} "
        f"class_signal={totals['class_signal']} filed={totals['total_filed']}",
        file=out,
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bench-recall",
        description="Score whether a lens recognises a seeded defect it has been shown. "
        "Not part of `make check`: it needs an agent, credentials and minutes per case.",
        epilog="Environment: BENCH_RECALL_TIMEOUT — whole seconds each --run agent invocation "
        f"may take (default {DEFAULT_TIMEOUT}). "
        "Exit codes: 0 graded, 1 runtime error, 2 usage error (including a bad timeout).",
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--grade",
        metavar="DIR",
        help="grade already-audited case directories under DIR (one subdirectory per case id)",
    )
    mode.add_argument(
        "--run", action="store_true", help="invoke an agent per case, then grade what it filed"
    )
    p.add_argument("--case", default="", help="restrict to one case id")
    p.add_argument("--agent-cmd", default=DEFAULT_AGENT_CMD, help="--run: command template")
    p.add_argument("--keep", action="store_true", help="--run: keep the audited copies")
    p.add_argument("--json", action="store_true", help="emit rows and totals as JSON")
    return p


def _grade_dir(cases: list[dict], root: Path) -> list[dict]:
    rows = []
    for case in cases:
        audited = root / case["id"]
        if not audited.is_dir():
            raise RecallError(f"{case['id']}: no audited copy at {audited}")
        rows.append(grade_case(case, audited))
    return rows


def _run_all(
    cases: list[dict], agent_cmd: str, keep: bool, timeout: int = DEFAULT_TIMEOUT
) -> list[dict]:
    workdir = Path(tempfile.mkdtemp(prefix="bench-recall-"))
    try:
        rows = [grade_case(case, run_case(case, agent_cmd, workdir, timeout)) for case in cases]
    finally:
        if keep:
            print(f"[info] audited copies kept in {workdir}", file=sys.stderr)
        else:
            shutil.rmtree(workdir, ignore_errors=True)
    return rows


def _agent_timeout() -> int | None:
    """BENCH_RECALL_TIMEOUT as whole seconds, or None after reporting a bad value."""
    raw = os.environ.get("BENCH_RECALL_TIMEOUT", str(DEFAULT_TIMEOUT))
    if raw.strip().isdigit() and int(raw) > 0:
        return int(raw)
    print(
        f"Error: BENCH_RECALL_TIMEOUT must be a whole number of seconds, got {raw!r}",
        file=sys.stderr,
    )
    return None


def load_all_cases(case_id: str = "") -> list[dict]:
    """The retrieval corpus plus the pressure cases, as one list.

    The trees are separate on disk because a pressure case is nearly all signal
    to a packer and would drag a retrieval precision floor pinned where it was
    measured (benchmarks/README.md). Recall grades both, so this is where they
    rejoin — one seam, so a caller asks for cases rather than for two roots.

    A named case may sit in either tree, so both trees load whole and the name
    filters here. Filtering per tree meant swallowing that tree's BenchError to
    tolerate the miss — and `load_cases` validates before it filters, so a
    malformed pressure case vanished behind a valid corpus name.
    """
    cases: list[dict] = []
    for root in (None, PRESSURE):
        if root is not None and not root.is_dir():
            continue
        cases += _retrieval.load_cases(root=root)
    # One id per case, across and within both trees: `--run` copies each into `workdir / id`,
    # so a repeat dies in `copytree`, and `--grade` scores one directory twice.
    ids = [c["id"] for c in cases]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise _retrieval.BenchError(f"duplicate case ids: {', '.join(dupes)}")
    if case_id:
        cases = [c for c in cases if c["id"] == case_id]
        if not cases:
            raise _retrieval.BenchError(f"unknown case {case_id!r}")
    return cases


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    # Only `--run` invokes an agent, so only it reads the timeout; a pure grade
    # is not failed by a variable it never uses.
    timeout = _agent_timeout() if args.run else DEFAULT_TIMEOUT
    if timeout is None:
        return 2
    try:
        cases = load_all_cases(args.case)
        # `is not None`, never truthiness: `--grade ""` is a request to grade,
        # and a falsy test sends it to the agent branch instead — spending
        # credentials and minutes per case on a run the user did not ask for.
        # The option has no default, so it is None exactly when omitted; an
        # empty value then fails in `_grade_dir` with the named-case error.
        if args.grade is not None:
            rows = _grade_dir(cases, Path(args.grade))
        else:
            rows = _run_all(cases, args.agent_cmd, args.keep, timeout)
        totals = aggregate(rows)
    except (RecallError, _retrieval.BenchError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"cases": rows, "totals": totals}, separators=(",", ":")))
    else:
        render(rows, totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
