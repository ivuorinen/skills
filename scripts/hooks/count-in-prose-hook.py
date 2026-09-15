#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.11"
# ///
"""PostToolUse hook — flag a spelled-out count of a growing set written into prose.

`.claude/rules/counts-in-prose.md` forbids counting a set that grows (tools,
hooks, validators, …) unless the count is structural or a gate pins it, and
concedes that nothing enforced it. The resolved ledger shows the result: the same
defect re-filed audit after audit, each count accurate the day it was typed
(agent-hooks-8c634b79).

Feedback, not a gate: a PostToolUse hook runs after the write, and exit 2 is the
only channel back to the agent. The agent judges each hit, because a structural
count is allowed and no pattern can tell one apart from a tally.

Scope: the text an Edit or Write put into a Markdown file, and docstring lines a
write put into a Python file. The findings store is skipped — a finding quotes
the stale count it reports.

Ceiling: a count in a code comment, a count of a set the pattern does not name,
and a count phrased without a following set noun (`the set has five`) all pass.
"""

import ast
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _hooklib import (
    _edited_path,
    _tool_input,
    load_event,
    repo_root,
)

REPO_ROOT = repo_root()

_NUMBER = (
    r"two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|\d+\+?"
)
# The set nouns from the finding, plus `steps` and `guards`, which the ledger also
# records drifting. One optional word may sit between: `thirteen read tools`.
_SET = (
    r"tools|hooks|validators|modules|operations|manifests|classes|commands|gates|rules|"
    r"steps|guards"
)
_COUNT = re.compile(rf"\b(?:{_NUMBER})\s+(?:\S+\s+)?(?:{_SET})\b", re.IGNORECASE)
_STORE = Path("docs") / "audit" / "findings"


def _written(tool_input: dict) -> str | None:
    """The text this Write, Edit or MultiEdit put into the file, or None if absent.

    Only the written text is judged, not the whole file: judging the file would
    re-flag every structural count on each later edit, and feedback that repeats
    on unrelated changes is feedback that stops being read.
    """
    parts = [tool_input.get("new_string"), tool_input.get("content")]
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        parts += [e.get("new_string") for e in edits if isinstance(e, dict)]
    texts = [p for p in parts if isinstance(p, str)]
    return "\n".join(texts) if texts else None


def _docstring_lines(source: str) -> set[str]:
    """Every stripped line of every module, class and function docstring.

    Unparseable source yields nothing: ruff-hook.py reports the syntax error, and
    guessing at docstrings in a broken file would flag code as prose.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    lines: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                lines.update(line.strip() for line in doc.splitlines())
    return lines


def main() -> None:
    """Report each written line that counts a growing set, and exit 2 if any does."""
    data = load_event()
    if data is None:
        return
    path = _edited_path(data)
    if path is None or path.suffix not in (".md", ".py"):
        return
    root = REPO_ROOT.resolve()
    if not path.is_relative_to(root) or path.is_relative_to(root / _STORE):
        return

    written = _written(_tool_input(data))
    source = path.read_text(encoding="utf-8") if path.is_file() else ""
    lines = (source if written is None else written).splitlines()
    if path.suffix == ".py":
        docs = _docstring_lines(source)
        lines = [line for line in lines if line.strip() in docs]
    hits = [line.strip() for line in lines if _COUNT.search(line)]
    if not hits:
        return

    rel = path.relative_to(root)
    for line in hits:
        print(f"  count-in-prose: {rel}: {line}", file=sys.stderr)
    print(
        "  A spelled-out count of a growing set goes stale when the set changes.\n"
        "  Name the set, or cite the gate that pins the number. A structural count\n"
        "  (one that cannot change without a redesign) may stay.\n"
        "  See .claude/rules/counts-in-prose.md.",
        file=sys.stderr,
        flush=True,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
