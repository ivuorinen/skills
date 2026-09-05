#!/usr/bin/env python3
"""The markdown code-fence rule, defined once for every bundled tool.

Four shipped tools walk markdown and must agree on where a fenced block starts
and ends: findings.py normalizing a finding body, skill_catalog.py parsing the
command tables, check-rules-anatomy.py deciding which lines the hedged-language
gate judges, and check-agent-instructions.py counting directives. Each carried
its own copy of the rule, and the copies had already drifted: findings.py and
skill_catalog.py closed a block on any line *beginning* with a fence run, so

    ```
    example
    ```python
    leaked
    ```

ended the block at ```` ```python ````, exposed `leaked` as ordinary content,
and then read the real closer as a new opener — swallowing everything after it.
CommonMark is explicit that a closing fence may not carry an info string, so the
full-match spelling the other two used is the correct one. Sharing the predicate
makes that divergence structurally impossible rather than merely fixed.

Line-based, not marker-based: the earlier signature took an already-extracted
marker, which is exactly what let a prefix match stand in for a full one.
"""

import re

_OPEN_RE = re.compile(r"(`{3,}|~{3,})")
_CLOSE_RE = re.compile(r"(`{3,}|~{3,})\s*")


def opener(stripped: str) -> str:
    """The fence run opening this line (``` or ~~~, 3+ chars), else ''.

    Takes the line already stripped, because callers differ on whether an
    indented fence counts and that is theirs to decide.
    """
    m = _OPEN_RE.match(stripped)
    return m.group(1) if m else ""


def closes(stripped: str, fence: str) -> bool:
    """True when this line closes the open ``fence``.

    Three conditions, each of which a hand-rolled copy got wrong somewhere: the
    line is *only* the run plus optional trailing whitespace (an info string
    means it is not a closer), the marker character matches, and the run is at
    least as long — so a four-backtick block is not closed by three backticks.
    """
    m = _CLOSE_RE.fullmatch(stripped)
    return bool(m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence))
