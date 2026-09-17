"""Every argparse argument in a shipped skill tool carries `help=`.

`.claude/rules/use-uv-runner.md` requires a shipped tool to answer `--help` with
its interface, because that output is how an agent learns what the tool accepts.
An argument with no `help=` is invisible there: `--root` was declared without one
and three separate command runs in a single session read it as the project root,
built a findings store in the repository and replaced its `.gitattributes` and
`.gitignore` (audit-141e9b71).

Static, not a `--help` smoke test: the per-tool tests already confirm `--help`
exits 0, which it does whether or not the flags it lists say anything.
"""

import ast
from pathlib import Path

import pytest

_SHIPPED = sorted((Path(__file__).parent.parent / "skills").glob("*/scripts/*.py"))


def _undocumented(path: Path) -> list[str]:
    """`<flag>:<line>` for every add_argument call in `path` with no help=."""
    missing: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "add_argument"):
            continue
        if any(keyword.arg == "help" for keyword in node.keywords):
            continue
        first = node.args[0] if node.args else None
        name = first.value if isinstance(first, ast.Constant) else "<computed>"
        missing.append(f"{name}:{node.lineno}")
    return missing


@pytest.mark.parametrize("tool", _SHIPPED, ids=lambda p: p.name)
def test_every_argument_is_documented(tool):
    undocumented = _undocumented(tool)
    assert not undocumented, (
        f"{tool.name}: add help= to {', '.join(undocumented)} — "
        "an undocumented flag is absent from --help, which is the only interface "
        "an agent reads before invoking the tool"
    )


def test_the_probe_catches_a_missing_help(tmp_path):
    """The control: a clean sweep above means nothing if the probe cannot fail."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import argparse\n"
        "p = argparse.ArgumentParser()\n"
        "p.add_argument('--documented', help='x')\n"
        "p.add_argument('--bare')\n",
        encoding="utf-8",
    )
    assert _undocumented(sample) == ["--bare:4"]


def test_the_sweep_actually_found_tools():
    """A glob that matches nothing would pass every assertion above in silence."""
    assert _SHIPPED, "no shipped tools found under skills/*/scripts/"
