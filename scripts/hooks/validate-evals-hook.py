#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — validate skill eval sets after Write or Edit.

Resolves finding audit-4589bff5. Every other governed surface in this repo has
an in-session validator plus a commit-time gate; eval sets had only the gate.
`validate-json-hook.py` fires on any edited `.json` but checks syntax alone, so
a file that parses yet carries a missing `assertions` array, a duplicate `id`,
or a split holding one label passed cleanly until `make check` or the commit
hook ran.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (  # type: ignore[import-not-found]
    HOOK_TIMEOUT,
    event_path,
    repo_root,
)

REPO_ROOT = repo_root()


def is_eval_file(path: Path, root: Path) -> bool:
    """True when `path` is an eval set this hook owns.

    The shape is exactly `skills/<skill>/evals/<file>.json`. Checking the
    grandparent against `skills/` rather than just `is_relative_to` keeps a
    deeper file such as `skills/x/evals/files/fixture.json` out — those are eval
    *inputs*, not eval sets, and validate-evals.py has no opinion on them.
    """
    skills_dir = root / "skills"
    return (
        path.suffix == ".json"
        and path.is_relative_to(skills_dir)
        and path.parent.name == "evals"
        and path.parent.parent.parent == skills_dir
    )


def main() -> None:
    """Validate the skill whose evals/ directory the edited file belongs to.

    Scoped to the one skill rather than the whole tree: an edit cannot affect
    another skill's eval set, and the per-skill run keeps the diagnostic pointed
    at the file just written. Passing the skill directory (not the JSON file) is
    what validate-evals.py expects as an argument.
    """
    path = event_path()
    if path is None:
        return

    root = REPO_ROOT.resolve()
    if not is_eval_file(path, root):
        return

    validator = REPO_ROOT / "scripts" / "validate-evals.py"
    if not validator.exists():
        # A checkout without the validator is not a failure to report here;
        # the commit-time gate still covers it.
        return

    try:
        # argv is the resolved validator path plus the skill directory derived
        # from the event — no shell, and nothing interpolated from user text.
        result = subprocess.run(
            ["uv", "run", "--quiet", str(validator), str(path.parent.parent)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=HOOK_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        # Returning beats raising: a hook that raises replaces its diagnosable
        # message with a traceback, and the commit-time gate is still in front
        # of anything landing.
        return

    if result.returncode != 0:
        # PostToolUse surfaces only exit 2 + stderr back to the agent.
        print((result.stdout + result.stderr).rstrip(), file=sys.stderr, flush=True)
        sys.exit(2)


if __name__ == "__main__":
    main()
