"""Tests for skills/nitpicker/scripts/md_fences.py and its four consumers.

The point of the shared module is agreement, so most of this file is a
differential test: one document through every tool that walks fences, asserting
they draw the block boundaries in the same place. Two of them did not, and the
disagreement was invisible because each had its own tests passing against its
own reading.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import md_fences  # type: ignore[import-not-found]  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# A block whose content contains a fence line carrying an info string. Only the
# bare run closes, so `OUTSIDE` is the one line outside the block.
_NESTED = "```\nINSIDE-A\n```python\nINSIDE-B\n```\nOUTSIDE\n"


class TestPredicates:
    def test_opener_returns_the_run(self):
        assert md_fences.opener("```python") == "```"
        assert md_fences.opener("~~~~") == "~~~~"
        assert md_fences.opener("not a fence") == ""

    def test_an_info_string_never_closes(self):
        """CommonMark: a closing fence may not have an info string."""
        assert md_fences.closes("```python", "```") is False
        assert md_fences.closes("```", "```") is True

    def test_a_shorter_run_does_not_close_a_longer_one(self):
        assert md_fences.closes("```", "````") is False
        assert md_fences.closes("````", "```") is True

    def test_markers_do_not_cross(self):
        assert md_fences.closes("~~~", "```") is False

    def test_trailing_whitespace_still_closes(self):
        assert md_fences.closes("```   ", "```") is True


class TestConsumersAgree:
    """Every tool that walks fences must draw the same boundaries."""

    @pytest.fixture(scope="class")
    def mods(self):
        return {
            "findings": _load("f_", _SCRIPTS / "findings.py"),
            "skill_catalog": _load("sc_", _SCRIPTS / "skill_catalog.py"),
            "check_agent_instructions": _load("cai_", _SCRIPTS / "check-agent-instructions.py"),
        }

    def test_skill_catalog_keeps_an_info_string_fence_inside_the_block(self, mods):
        assert list(mods["skill_catalog"]._outside_fences(_NESTED)) == ["OUTSIDE"]

    def test_check_agent_instructions_keeps_it_inside_too(self, mods):
        assert [s for _, s in mods["check_agent_instructions"]._content_lines(_NESTED)] == [
            "OUTSIDE"
        ]

    def test_findings_strips_the_whole_block(self, mods):
        """It returned 'INSIDE-B' before: closed early, then ate the real closer."""
        assert mods["findings"]._strip_fenced(_NESTED).strip() == "OUTSIDE"

    def test_a_table_row_inside_a_fence_is_never_read_as_a_command(self, mods):
        """The concrete cost for skill_catalog: a documented example becomes a row."""
        body = "```\n| `ghost` | not a real command |\n```python\nx\n```\n"
        assert list(mods["skill_catalog"]._outside_fences(body)) == []
