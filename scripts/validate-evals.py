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

    for ref in case.get("files", []):
        if not (skill_dir / ref).exists():
            err(f"eval {label} references missing input file {ref!r}")


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
        raw_id = case.get("id")
        label = raw_id if raw_id is not None else f"index {i}"
        if raw_id is None:
            err(f"evals[{i}] is missing 'id'")
        elif not isinstance(raw_id, str | int) or isinstance(raw_id, bool):
            # A list or dict id would raise TypeError on the set membership
            # test below, replacing every remaining diagnostic with a traceback.
            err(f"evals[{i}] id must be a string or integer; got {type(raw_id).__name__}")
        elif raw_id in seen:
            err(f"duplicate eval id {raw_id!r}")
        else:
            seen.add(raw_id)
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


def main() -> None:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return

    explicit = bool(sys.argv[1:])
    if explicit:
        skill_dirs = [Path(a) for a in sys.argv[1:]]
    else:
        repo_root = Path(__file__).parent.parent
        skill_dirs = sorted(p.parent for p in repo_root.glob("skills/*/evals"))

    errors: list[str] = []
    checked = sum(validate_skill_evals(d, errors) for d in skill_dirs)

    if errors:
        for e in errors:
            print(e)
        print(f"\n{len(errors)} error(s). Fix before committing.")
        sys.exit(1)

    # An explicitly supplied path that yielded no eval set is a
    # misconfiguration — a typo or a moved directory — not a clean run. Only
    # the no-argument sweep is allowed to find nothing, because a repo with no
    # eval sets is genuinely clean.
    if explicit and not checked:
        print(
            "  ERROR  no evals/ directory under any supplied path — "
            "the argument must be a skill directory",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"OK  {checked} eval set(s) validated.")


if __name__ == "__main__":
    main()
