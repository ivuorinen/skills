"""Read the gate list out of `.mise/tasks/check`, the one definition of the gate.

Every test that used to parse the Makefile's `check:` rule reads the phases
here instead, so no test keeps a second copy of which gates run.
"""

import shlex
from pathlib import Path

# Tokens that end one command; whatever follows belongs to the next.
_COMMAND_ENDS = {"||", "&&", ";", "|"}
# Flags that take a value as the next token.
_VALUED_FLAGS = {"--jobs", "-j"}


def _task_names(tokens: list[str]) -> list[str]:
    """The task names of one `mise run` argument list, flags dropped, `:::` split."""
    names: list[str] = []
    skip_value = False
    for tok in tokens:
        if tok in _COMMAND_ENDS:
            break
        if skip_value:
            skip_value = False
        elif tok in _VALUED_FLAGS:
            skip_value = True
        elif tok != ":::" and not tok.startswith("-"):
            names.append(tok)
    return names


def check_phases(root: Path) -> tuple[list[str], list[str]]:
    """(read_only, writers): the tasks each `mise run` in `check` names, in file order."""
    text = (root / ".mise" / "tasks" / "check").read_text(encoding="utf-8")
    joined = text.replace("\\\n", " ")
    runs = []
    for line in joined.splitlines():
        tokens = shlex.split(line, comments=True)
        for i in range(len(tokens) - 1):
            if tokens[i] == "mise" and tokens[i + 1] == "run":
                runs.append(_task_names(tokens[i + 2 :]))
    read_only, writers = runs
    return read_only, writers
