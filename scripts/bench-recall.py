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

Exit codes: 0 = graded (or thresholds met), 1 = runtime/IO error or a threshold
missed, 2 = usage error.
"""

import argparse
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

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
_retrieval = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_retrieval)  # type: ignore[union-attr]

# One agent invocation per case. `{goal}`, `{lens}` and `{dir}` are substituted;
# nothing else is, so a template cannot reach values this tool did not choose.
# Overridable because the harness must not hard-code one vendor's CLI — the
# thing being measured is the lens, not the runner.
DEFAULT_AGENT_CMD = "claude -p '/nitpicker {lens}' --permission-mode acceptEdits"

# Recall is the number that matters; the others are reported so a regression can
# be attributed. Left unset rather than guessed: no run has produced a
# distribution yet, so any floor written today would be aspiration, which is
# exactly what bench-retrieval.py's threshold comment warns against. Set them
# from the first few runs.
MIN_RECALL: float | None = None


class RecallError(Exception):
    """A case could not be run or graded."""


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


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
        if Path(path).name != Path(case["file"]).name or not _overlaps((start, end), want):
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
    return {
        "id": case["id"],
        "lens": case["lens"],
        "class": case["class"],
        "severity_floor": case["severity_floor"],
        "found": best is not None,
        "severity_ok": bool(best and best["severity_ok"]),
        "class_signal": bool(best and best["class_signal"]),
        "matched_severity": (best or {}).get("severity", ""),
        "findings_filed": len(filed),
        "findings_on_target": len(matches),
    }


def run_case(case: dict, agent_cmd: str, workdir: Path) -> Path:
    """Copy the case into `workdir`, audit it with `agent_cmd`, return that copy.

    Copied rather than audited in place: the agent writes a findings store, and
    a run must not leave one inside the corpus, where the next retrieval bench
    would pack it as repository content.
    """
    target = workdir / case["id"]
    shutil.copytree(case["dir"], target)
    command = agent_cmd.format(lens=case["lens"], goal=case["goal"], dir=str(target))
    # `shlex.split`, never `shell=True`. The template is operator-supplied and a
    # shell would make every substituted value — a lens name, a goal sentence
    # out of expected.json — something that can escape into it. Splitting honours
    # the quoting an agent CLI actually needs (`-p '/nitpicker security'`) and
    # leaves nothing to escape into. A template that genuinely needs a pipeline
    # belongs in a script the template then names.
    argv = shlex.split(command)
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
            timeout=int(os.environ.get("BENCH_RECALL_TIMEOUT", "900")),
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


def render(rows: list[dict], totals: dict, out=None) -> None:
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
        epilog="Exit codes: 0 graded, 1 runtime error or threshold missed, 2 usage error.",
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


def _run_all(cases: list[dict], agent_cmd: str, keep: bool) -> list[dict]:
    workdir = Path(tempfile.mkdtemp(prefix="bench-recall-"))
    try:
        rows = [grade_case(case, run_case(case, agent_cmd, workdir)) for case in cases]
    finally:
        if keep:
            print(f"[info] audited copies kept in {workdir}", file=sys.stderr)
        else:
            shutil.rmtree(workdir, ignore_errors=True)
    return rows


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = _retrieval.load_cases(args.case)
        if args.grade:
            rows = _grade_dir(cases, Path(args.grade))
        else:
            rows = _run_all(cases, args.agent_cmd, args.keep)
        totals = aggregate(rows)
    except (RecallError, _retrieval.BenchError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"cases": rows, "totals": totals}, separators=(",", ":")))
    else:
        render(rows, totals)

    if MIN_RECALL is not None and totals["recall"] < MIN_RECALL:
        print(f"FAIL  recall {totals['recall']} < {MIN_RECALL}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
