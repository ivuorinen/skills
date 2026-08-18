#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""Validate the eval sets bundled with each skill.

Usage:
    validate-evals.py [<skill-dir> ...]

With no arguments, checks every `skills/*/evals/` directory in the repo.

Two file shapes are checked, both defined by the Agent Skills skill-creation
guides:

    evals/evals.json          output-quality test cases
                              (https://agentskills.io/skill-creation/evaluating-skills)
    evals/trigger-queries.json  description trigger-accuracy queries
                              (https://agentskills.io/skill-creation/optimizing-descriptions)

Neither file is required. When one exists it must be well-formed, so an eval
set cannot rot into a shape the eval loop silently skips.

Exit codes: 0 = valid (or no eval sets present), 1 = malformed eval set.
"""

import json
import sys
from collections.abc import Callable
from pathlib import Path

_SPLITS = ("train", "validation")


def _load(path: Path, errors: list[str]) -> dict | None:
    """Parse a JSON object, recording a diagnostic instead of raising."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        errors.append(f"  ERROR  {path}: {e}")
        return None
    if not isinstance(data, dict):
        errors.append(f"  ERROR  {path}: top level must be a JSON object")
        return None
    return data


def _check_files(
    refs: object, label: str | int, skill_dir: Path, err: Callable[[str], None]
) -> None:
    """Validate a case's optional `files` list of input-file paths.

    Shape-checked before iteration: a null, a number, or a non-string element
    would raise TypeError and replace every remaining diagnostic with a
    traceback — the failure mode this validator exists to avoid.
    """
    if not isinstance(refs, list):
        err(f"eval {label} 'files' must be a list; got {type(refs).__name__}")
        return
    for ref in refs:
        if not isinstance(ref, str) or not ref.strip():
            err(f"eval {label} has an input file reference that is not a non-empty string")
        elif not (skill_dir / ref).exists():
            err(f"eval {label} references missing input file {ref!r}")


def _check_case(case: dict, label: str | int, skill_dir: Path, err: Callable[[str], None]) -> None:
    """Check one evals.json test case (id uniqueness handled by the caller)."""
    for field in ("prompt", "expected_output"):
        if not str(case.get(field, "")).strip():
            err(f"eval {label} has an empty '{field}'")

    assertions = case.get("assertions")
    if not isinstance(assertions, list) or not assertions:
        # Without assertions there is nothing to grade, so the case contributes
        # no signal to the pass rate.
        err(f"eval {label} needs at least one assertion")
    elif any(not str(a).strip() for a in assertions):
        err(f"eval {label} has an empty assertion")

    _check_files(case.get("files", []), label, skill_dir, err)


def _check_id(raw_id: object, index: int, seen: set, err: Callable[[str], None]) -> str | int:
    """Validate one case's `id`, record it, and return the label for diagnostics.

    Split out of validate_evals so the per-case ladder does not push that
    function past the complexity ceiling. Returns a positional label when the id
    is missing or unusable, so later diagnostics can still name the case.
    """
    if raw_id is None:
        err(f"evals[{index}] is missing 'id'")
    elif not isinstance(raw_id, str | int) or isinstance(raw_id, bool):
        # A list or dict id would raise TypeError on the set membership test,
        # replacing every remaining diagnostic with a traceback. bool is
        # excluded explicitly because it subclasses int.
        err(f"evals[{index}] id must be a string or integer; got {type(raw_id).__name__}")
    elif raw_id in seen:
        err(f"duplicate eval id {raw_id!r}")
    else:
        seen.add(raw_id)
        return raw_id
    return f"index {index}"


def validate_evals(path: Path, skill_name: str, errors: list[str]) -> None:
    """Check evals/evals.json — test cases with prompts, outputs, assertions."""
    data = _load(path, errors)
    if data is None:
        return

    def err(msg: str) -> None:
        errors.append(f"  ERROR  {path}: {msg}")

    if data.get("skill_name") != skill_name:
        err(f"skill_name is {data.get('skill_name')!r}; must be {skill_name!r}")

    cases = data.get("evals")
    if not isinstance(cases, list) or not cases:
        err("'evals' must be a non-empty list of test cases")
        return

    seen: set = set()
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            err(f"evals[{i}] must be an object")
            continue
        label = _check_id(case.get("id"), i, seen, err)
        _check_case(case, label, path.parent.parent, err)


def _query_labels(queries: list, err: Callable[[str], None]) -> dict[str, set[bool]]:
    """Check each query and return the should_trigger labels present per split."""
    labels: dict[str, set[bool]] = {s: set() for s in _SPLITS}
    for i, q in enumerate(queries):
        if not isinstance(q, dict):
            err(f"queries[{i}] must be an object")
            continue
        if not str(q.get("query", "")).strip():
            err(f"queries[{i}] has an empty 'query'")
        labelled = isinstance(q.get("should_trigger"), bool)
        if not labelled:
            err(f"queries[{i}] needs a boolean 'should_trigger'")
        split = q.get("split")
        if split not in _SPLITS:
            err(f"queries[{i}] split must be one of {_SPLITS}; got {split!r}")
        elif labelled:
            labels[split].add(q["should_trigger"])
    return labels


def validate_trigger_queries(path: Path, skill_name: str, errors: list[str]) -> None:
    """Check evals/trigger-queries.json — labelled queries in a fixed split."""
    data = _load(path, errors)
    if data is None:
        return

    def err(msg: str) -> None:
        errors.append(f"  ERROR  {path}: {msg}")

    if data.get("skill_name") != skill_name:
        err(f"skill_name is {data.get('skill_name')!r}; must be {skill_name!r}")

    threshold = data.get("threshold", 0.5)
    if not isinstance(threshold, int | float) or not 0 < threshold < 1:
        err(f"threshold must be between 0 and 1 exclusive; got {threshold!r}")

    queries = data.get("queries")
    if not isinstance(queries, list) or not queries:
        err("'queries' must be a non-empty list")
        return

    labels = _query_labels(queries, err)
    for split in _SPLITS:
        if labels[split] != {True, False}:
            # A split holding only one label cannot measure both failure modes:
            # missed triggers and false triggers.
            err(f"the '{split}' split must contain both should_trigger true and false queries")


def validate_skill_evals(skill_dir: Path, errors: list[str]) -> bool:
    """Validate one skill's evals/ directory. Returns True if any file was checked."""
    evals_dir = skill_dir / "evals"
    checked = False
    for filename, checker in (
        ("evals.json", validate_evals),
        ("trigger-queries.json", validate_trigger_queries),
    ):
        path = evals_dir / filename
        if path.is_file():
            checker(path, skill_dir.name, errors)
            checked = True
    return checked


def _target_dirs(args: list[str]) -> list[Path]:
    """Skill directories to check: the supplied paths, else every skills/*/evals."""
    if args:
        return [Path(a) for a in args]
    repo_root = Path(__file__).parent.parent
    return sorted(p.parent for p in repo_root.glob("skills/*/evals"))


def _report_missing(missing: list[Path]) -> None:
    """Fail on supplied paths that yielded no eval set, naming each one.

    An explicitly supplied path with no eval set is a misconfiguration — a typo
    or a moved directory — not a clean run. Reported per path rather than as a
    total, so one valid path cannot mask a typo'd sibling. Only the no-argument
    sweep is allowed to find nothing, because a repo with no eval sets is
    genuinely clean; that caller never reaches here.
    """
    if not missing:
        return
    for d in missing:
        print(
            f"  ERROR  no eval set under supplied path {str(d)!r} — "
            "the argument must be a skill directory",
            file=sys.stderr,
        )
    sys.exit(1)


def main() -> None:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return

    explicit = bool(sys.argv[1:])
    skill_dirs = _target_dirs(sys.argv[1:])

    errors: list[str] = []
    # Per-path, not a total: summing hides a typo'd path behind a valid one, so
    # `validate-evals.py good-skill typo-skill` would exit 0 on a non-zero total.
    results = [(d, validate_skill_evals(d, errors)) for d in skill_dirs]
    checked = sum(was_checked for _, was_checked in results)

    if errors:
        for e in errors:
            print(e)
        print(f"\n{len(errors)} error(s). Fix before committing.")
        sys.exit(1)

    if explicit:
        _report_missing([d for d, was_checked in results if not was_checked])

    print(f"OK  {checked} eval set(s) validated.")


if __name__ == "__main__":
    main()
