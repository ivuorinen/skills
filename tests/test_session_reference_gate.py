"""The session-reference gate lives in two places: the `no-session-reference`
commit-msg hook and the commit-lint workflow step. Both patterns are read out of
their files here, so a change to one that the other does not follow fails."""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent

LEAKS = [
    "Claude-Session: https://example.invalid/x",
    "claude-session: lowercase trailer",
    "see https://claude.ai/code/session_EXAMPLE",
]
CLEAN = ["fix: gate session trailers", "Co-Authored-By: someone", "claude.ai docs"]


def _hook_pattern() -> re.Pattern[str]:
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    hooks = [h for repo in config["repos"] for h in repo["hooks"]]
    hook = next(h for h in hooks if h["id"] == "no-session-reference")
    assert "--negate" not in hook.get("args", []), "--negate would pass every leaking message"
    assert hook["stages"] == ["commit-msg"]
    flags = re.I if "--ignore-case" in hook.get("args", []) else 0
    return re.compile(hook["entry"], flags)


def _workflow_pattern() -> re.Pattern[str]:
    workflow = (ROOT / ".github/workflows/commit-lint.yml").read_text(encoding="utf-8")
    m = re.search(r'SESSION = re\.compile\(r"([^"]+)"(, re\.I)?\)', workflow)
    assert m, "could not find the SESSION regex in commit-lint.yml"
    return re.compile(m.group(1), re.I if m.group(2) else 0)


def test_hook_and_workflow_reject_the_same_messages():
    for pattern in (_hook_pattern(), _workflow_pattern()):
        for text in LEAKS:
            assert pattern.search(text), f"{pattern.pattern!r} misses {text!r}"
        for text in CLEAN:
            assert not pattern.search(text), f"{pattern.pattern!r} flags {text!r}"
