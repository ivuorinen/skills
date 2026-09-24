#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Score context_pack's retrieval against the seeded defect corpus.

Usage:
    bench-retrieval.py [--case <id>] [--json] [--verbose] [--budget-tokens N]

Answers one question per case: **given a goal a lens would realistically issue,
does the pack surface the lines where the defect actually lives, and how much
irrelevant material comes first?**

This is the half of defect detection that can fail silently. A lens that never
receives the defect's lines cannot report it, and the clean run that follows is
indistinguishable from a repository with no defect. Nothing else in this repo
measures it, it needs no model, and it is exactly what a context-reduction
change puts at risk — so it gates on every commit.

What it does NOT measure: whether a lens recognises the defect once it sees it.
That is `bench-recall.py`'s half — it needs an agent per case and stays out of
`make check`. Do not read a passing run here as "the security lens works"; read
it as "retrieval did not regress".

Metrics, per case and aggregated:

    hit            the expected range overlaps at least one returned candidate
    rank           1-based position of the first overlapping candidate
    recall_at_5    hit within the first five candidates
    mrr            mean reciprocal rank across cases
    noise_tokens   estimated tokens packed ahead of the first hit
    precision      hit tokens / total packed tokens

Exit codes: 0 = thresholds met, 1 = a threshold missed or a case is malformed,
2 = usage error.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "skills/nitpicker/scripts"))
import context_pack

CORPUS = Path(__file__).resolve().parent.parent / "benchmarks" / "corpus"

# Thresholds, set from measurement rather than aspiration. The first draft of
# this file carried MIN_MRR = 0.9 described as "observed"; the actual figure was
# 0.42, because a lexical retriever puts the defect at rank 2-4 rather than 1 and
# every distractor in the corpus is there to make that happen. A floor nobody
# measured is a floor that gets lowered the first time it fails, which is how a
# gate becomes decoration.
#
# Scoring is fully deterministic, so the margins are small on purpose — they
# absorb a corpus addition, not run-to-run noise. Raise these when the retriever
# improves; never lower one to make a red build green.
# Precision's margin is the thin one and that is a deliberate reading, not an
# oversight: `ts-type-escape` was excluded as a known limitation until construct
# matching reached it, and folding a hard case back in moved precision down
# (0.1816 -> 0.1612) while moving recall and MRR up. A retriever that finds one
# more defect at the cost of some packed noise is better, so the floor stays
# where it was measured rather than being raised to the new number and locking
# the next hard case out.
MIN_RECALL_AT_5 = 1.0  # observed 1.0 — every gated defect must be found at all
MIN_MRR = 0.40  # observed 0.4305
MIN_PRECISION = 0.15  # observed 0.1612


class BenchError(Exception):
    """A malformed case or a bad argument."""


# The `expected.json` schema benchmarks/README.md documents. `note` is prose for
# a reader and is not required; every key here is read by one of the two
# scorers, so a case missing any of them fails somewhere further on with no case
# name attached.
_REQUIRED_KEYS = frozenset({"id", "lens", "class", "severity_floor", "goal", "file", "lines"})

# Optional, and read by bench-recall alone. A pressure case measures the half no
# gate in this repo tests: whether a lens's consent and coverage gates hold when
# the invocation tells it to cut corners. `pressure` is the corner-cutting
# instruction handed to the agent alongside the goal; `must_keep` names what the
# run must NOT have removed — the deterministic half of "did the gate hold",
# checked against the audited copy rather than against a transcript. Absent keys
# mean an ordinary recall case, so the existing corpus is unaffected.
_OPTIONAL_STRING_KEYS = frozenset({"pressure"})

# Every required key except `lines` is consumed as a string by one of the two
# scorers, so every one of them is checked as a string. Naming only the keys
# that happen to crash today would close two of six: `file` raises TypeError at
# the path join and `goal` AttributeError at `.lower()`, both here — but
# `class` reaches `.replace()` in bench-recall.py with the identical exposure,
# and it is only invisible from this file. The set is derived rather than
# written out so a key added to _REQUIRED_KEYS is validated by default.
_STRING_KEYS = _REQUIRED_KEYS - {"lines"}


def _overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _pressure_keys(path: Path, meta: dict) -> list[dict]:
    """Check a pressure case's optional keys; return its `must_keep` entries.

    The optional keys are checked on the same terms as the required ones. A
    `"pressure": 42` would reach the prompt substitution in bench-recall and a
    malformed `must_keep` would reach the grader — both outside the BenchError
    contract, and the second silently: an entry that is not a {file, contains}
    object cannot be checked, so the gate it encodes would score as held.
    Split out of `_case_meta` only to keep each function under the complexity
    limit; the path containment of each `file` stays there, beside `file`'s own.
    """
    mistyped_optional = sorted(
        k for k in _OPTIONAL_STRING_KEYS if k in meta and not isinstance(meta[k], str)
    )
    if mistyped_optional:
        raise BenchError(
            f"{path.parent.name}: expected.json needs a string for "
            f"{', '.join(f'{k} (got {type(meta[k]).__name__})' for k in mistyped_optional)}"
        )
    # Present means meant: `"pressure": ""` is falsy, so bench-recall skipped both
    # the pressure and its `{goal}` check and graded an untested gate as held.
    if "pressure" in meta and not meta["pressure"].strip():
        raise BenchError(f"{path.parent.name}: expected.json 'pressure' must not be blank")
    keep = meta.get("must_keep", [])
    if not isinstance(keep, list) or not all(
        isinstance(entry, dict)
        and isinstance(entry.get("file"), str)
        and isinstance(entry.get("contains"), str)
        # Blank never fails: `"" in text` holds for every file, and whitespace
        # survives the removal it is meant to detect — a held gate by default.
        and entry["contains"].strip()
        for entry in keep
    ):
        raise BenchError(
            f"{path.parent.name}: 'must_keep' must be a list of "
            "{file, contains} objects, both strings, contains not blank"
        )
    return keep


def _case_meta(path: Path) -> dict:
    """One case's `expected.json`, decoded and shape-checked.

    Every shape rejected here would otherwise end in a traceback that does not
    name the case, which is the outcome the out-of-range check in `load_cases`
    was written to prevent — a broken corpus reading as a broken retriever. The
    case directory is the identifier throughout, because `id` is one of the keys
    that may be missing.
    """
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BenchError(f"{path.parent.name}: expected.json is not valid JSON ({exc})") from exc
    # An object, before the keys. `json.loads` returns whatever the file holds,
    # and `null`, `42` and `[[]]` all reach `set(meta)` as a TypeError naming no
    # case — the same escape from the BenchError contract the element-type check
    # below exists to close. A string is worse than a traceback: it *is*
    # iterable, so `set("x")` succeeds and the run reports a case that "lacks"
    # every required key rather than saying the file is not an object at all.
    if not isinstance(meta, dict):
        raise BenchError(
            f"{path.parent.name}: expected.json is not a JSON object (got {type(meta).__name__})"
        )
    missing = _REQUIRED_KEYS - set(meta)
    if missing:
        raise BenchError(f"{path.parent.name}: expected.json lacks {', '.join(sorted(missing))}")
    # Present is not the same as usable. A key check alone let `"file": 42`
    # through to `path.parent / meta["file"]` (TypeError) and `"goal": null`
    # through to `meta["goal"].lower()` (AttributeError), both outside the
    # BenchError contract — the same escape as the checks either side of this
    # one, through the values rather than the keys.
    mistyped = sorted(k for k in _STRING_KEYS if not isinstance(meta[k], str))
    if mistyped:
        raise BenchError(
            f"{path.parent.name}: expected.json needs a string for "
            f"{', '.join(f'{k} (got {type(meta[k]).__name__})' for k in mistyped)}"
        )
    keep = _pressure_keys(path, meta)
    # Inside the case tree, or the case measures something else. An absolute
    # path makes `dir / file` discard `dir`, and `..` climbs out of it, so the
    # scorer reads unrelated local content and the grader can mark a pressure
    # gate held from a file the run never saw. `file` joins the same way.
    case_dir = path.parent.resolve()
    outside = [
        name
        for name in (meta["file"], *(entry["file"] for entry in keep))
        if not (case_dir / name).resolve().is_relative_to(case_dir)
    ]
    if outside:
        raise BenchError(
            f"{path.parent.name}: expected.json names files outside the case tree: "
            f"{', '.join(outside)}"
        )
    # `id` is joined the same way by bench-recall — `workdir / id` for the copy it
    # audits and `root / id` for the tree it grades — so it must be one plain name.
    if meta["id"] in ("", ".", "..") or Path(meta["id"]).name != meta["id"]:
        raise BenchError(f"{path.parent.name}: 'id' must be a plain name, got {meta['id']!r}")
    # Element types too, not just the shape. `["1", "2"]` is a two-element list,
    # so a shape-only check passes it through to `1 <= start`, which raises
    # TypeError — outside the BenchError contract again, one line further down
    # than the JSON and key checks above. `bool` is excluded because it is an
    # `int` subclass: `[true, 2]` would otherwise score line 1 silently, which is
    # worse than the traceback.
    bounds = meta["lines"]
    if not (
        isinstance(bounds, list)
        and len(bounds) == 2
        and all(isinstance(n, int) and not isinstance(n, bool) for n in bounds)
    ):
        raise BenchError(f"{meta['id']}: 'lines' must be a two-element [start, end] of integers")
    return meta


def load_cases(case_id: str = "", root: Path | None = None) -> list[dict]:
    """Every case's expected.json, or the one named.

    A case whose expected range does not exist in its own file is an error, not
    a zero: scoring retrieval against lines that are not there would report a
    broken corpus as a broken retriever.

    `root` defaults to the retrieval corpus. `bench-recall.py` passes
    `benchmarks/pressure` as well, because a pressure case is scored on whether a
    gate held and is nearly all signal to a packer — folding one into the
    retrieval mean drags a precision floor pinned where it was measured, and that
    floor is not to be lowered to make a red build green.
    """
    root = root or CORPUS
    found = []
    for path in sorted(root.glob("*/expected.json")):
        meta = _case_meta(path)
        meta["dir"] = path.parent
        target = path.parent / meta["file"]
        if not target.is_file():
            raise BenchError(f"{meta['id']}: expected file {meta['file']} does not exist")
        total = len(target.read_text(encoding="utf-8").splitlines())
        start, end = meta["lines"]
        if not 1 <= start <= end <= total:
            raise BenchError(
                f"{meta['id']}: expected lines {start}-{end} outside {meta['file']} (1-{total})"
            )
        _check_goal_is_honest(meta, target, start, end)
        found.append(meta)
    if case_id:
        found = [c for c in found if c["id"] == case_id]
        if not found:
            known = sorted(p.parent.name for p in CORPUS.glob("*/expected.json"))
            raise BenchError(f"unknown case {case_id!r}; known: {', '.join(known)}")
    if not found:
        raise BenchError(f"no cases under {CORPUS}")
    return found


def _check_goal_is_honest(meta: dict, target: Path, start: int, end: int) -> None:
    """Refuse a goal cribbed from the planted line rather than written from the class.

    The dishonest shape is specific: terms that hit *inside* the expected range
    and nowhere outside it. That is a search for a string the author already
    knows is unique to the answer, and it scores a perfect rank while measuring
    nothing.

    Terms that appear nowhere in the file are a different thing entirely and are
    allowed — that is a defect class with no lexical signature, which is a real
    property of the retriever worth recording. `ts-type-escape` is exactly that
    case: none of "unchecked cast any assertion" appears in `api.ts`, and the
    line is reached through `context_pack`'s construct matching rather than
    through any term. Rewriting such a goal until it hits lexically is the
    doctoring this guard exists to refuse.
    """
    lines = target.read_text(encoding="utf-8").splitlines()
    body = target.read_text(encoding="utf-8").lower()
    outside = "\n".join(lines[: start - 1] + lines[end:]).lower()
    terms = {t for t in meta["goal"].lower().split() if len(t) > 2}
    hits_inside = any(t in body and t not in outside for t in terms)
    if hits_inside and not any(t in outside for t in terms):
        raise BenchError(
            f"{meta['id']}: every goal term that matches at all matches only inside the "
            "expected range — the goal was written from the answer, so it measures nothing"
        )


def score_case(meta: dict, budget_tokens: int) -> dict:
    """Run one case through context_pack and score where the defect landed."""
    pack = context_pack.build(
        root=meta["dir"], goal=meta["goal"], mode="evidence", budget_tokens=budget_tokens
    )
    want = (meta["lines"][0], meta["lines"][1])
    rank, noise, hit_tokens = 0, 0, 0
    for index, cand in enumerate(pack["candidates"], start=1):
        same_file = cand["path"] == meta["file"]
        if same_file and _overlaps((cand["start"], cand["end"]), want):
            rank, hit_tokens = index, cand["tokens"]
            break
        noise += cand["tokens"]
    packed = pack["budget"]["estimated"]
    return {
        "id": meta["id"],
        "lens": meta["lens"],
        "known_limitation": meta.get("known_limitation", ""),
        "class": meta["class"],
        "hit": bool(rank),
        "rank": rank,
        "candidates": len(pack["candidates"]),
        "noise_tokens": noise if rank else packed,
        "packed_tokens": packed,
        "precision": round(hit_tokens / packed, 4) if packed else 0.0,
        "reciprocal_rank": round(1 / rank, 4) if rank else 0.0,
    }


def aggregate(rows: list[dict]) -> dict:
    """Totals over the gated cases only; known limitations are counted separately.

    A known-limitation case averaged into the score would drag every threshold
    down to accommodate it, which is how a floor stops detecting anything.
    """
    gated = [r for r in rows if not r["known_limitation"]]
    n = len(gated) or 1
    return {
        "cases": len(rows),
        "gated": len(gated),
        "known_limitations": sum(1 for r in rows if r["known_limitation"]),
        "hits": sum(r["hit"] for r in gated),
        "recall_at_5": round(sum(1 for r in gated if 0 < r["rank"] <= 5) / n, 4),
        "mrr": round(sum(r["reciprocal_rank"] for r in gated) / n, 4),
        "mean_precision": round(sum(r["precision"] for r in gated) / n, 4),
        "total_packed_tokens": sum(r["packed_tokens"] for r in rows),
    }


def failures(totals: dict, rows: list[dict]) -> list[str]:
    """Threshold breaches. Empty means the gate passes.

    A known-limitation case that *hits* is a failure too, exactly like a strict
    xfail: the limitation is gone, so the exemption is now hiding a case that
    should be gated. Without this the field becomes a place to park anything
    inconvenient and never look again.
    """
    checks = (
        ("recall_at_5", totals["recall_at_5"], MIN_RECALL_AT_5),
        ("mrr", totals["mrr"], MIN_MRR),
        ("mean_precision", totals["mean_precision"], MIN_PRECISION),
    )
    out = [f"{name} {value} < {floor}" for name, value, floor in checks if value < floor]
    out += [
        f"{r['id']} is marked known_limitation but retrieval found it at rank "
        f"{r['rank']} — remove the marker so the case gates"
        for r in rows
        if r["known_limitation"] and r["hit"]
    ]
    return out


def render(rows: list[dict], totals: dict, verbose: bool, out: TextIO | None = None) -> None:
    out = out or sys.stdout
    if verbose:
        print(f"{'case':<30}{'lens':<12}{'rank':>5}{'cands':>7}{'noise':>8}{'prec':>8}", file=out)
        for row in rows:
            rank = row["rank"] or ("n/a" if row["known_limitation"] else "MISS")
            print(
                f"{row['id']:<30}{row['lens']:<12}{rank:>5}{row['candidates']:>7}"
                f"{row['noise_tokens']:>8}{row['precision']:>8.2f}",
                file=out,
            )
        print(file=out)
    print(
        f"cases={totals['cases']} hits={totals['hits']} "
        f"recall@5={totals['recall_at_5']} mrr={totals['mrr']} "
        f"precision={totals['mean_precision']} packed={totals['total_packed_tokens']}",
        file=out,
    )


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bench-retrieval",
        description="Score context_pack retrieval against the seeded defect corpus. "
        "Measures whether the defect's lines are surfaced, not whether a lens recognises them.",
        epilog="Exit codes: 0 thresholds met, 1 threshold missed or malformed case, 2 usage error.",
    )
    p.add_argument("--case", default="", help="score one case by id")
    p.add_argument("--budget-tokens", type=int, default=4000, help="pack budget per case")
    p.add_argument("--json", action="store_true", help="emit rows and totals as JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="one line per case")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        cases = load_cases(args.case)
        rows = [score_case(c, args.budget_tokens) for c in cases]
    except BenchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except context_pack.PackError as exc:
        print(f"Error: context_pack refused a case: {exc}", file=sys.stderr)
        return 1

    totals = aggregate(rows)
    if args.json:
        print(json.dumps({"cases": rows, "totals": totals}, separators=(",", ":")))
    else:
        render(rows, totals, args.verbose or bool(args.case))

    # A single-case run reports but never gates: the thresholds are aggregates,
    # and applying them to one case would fail the hard case in isolation.
    if args.case:
        return 0
    if breaches := failures(totals, rows):
        print("FAIL  " + "; ".join(breaches), file=sys.stderr)
        for row in rows:
            if not row["hit"] and not row["known_limitation"]:
                print(f"      missed: {row['id']} ({row['lens']})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
