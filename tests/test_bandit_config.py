"""The `.bandit` INI mirrors `[tool.bandit]` in pyproject.toml.

Two files describe one policy, so they can drift. pyproject.toml is the source
of truth — it carries the reasoning for every skip — while `.bandit` exists
purely so a runner that cannot be told `-c pyproject.toml` still finds the
configuration. Codacy is that runner: bandit auto-discovers nothing, so a bare
`bandit -r` uses defaults and reports B404/B603/B607 no matter what
pyproject.toml says.

These pin the values in both places and the shape of the INI keys, which differ
from pyproject.toml's in a way that fails silently: the INI key is `exclude`,
not `exclude_dirs`, and a bare directory name never matches.
"""

import configparser
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent
BANDIT_INI = REPO_ROOT / ".bandit"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _ini() -> configparser.SectionProxy:
    parser = configparser.ConfigParser()
    parser.read(BANDIT_INI, encoding="utf-8")
    return parser["bandit"]


def _pyproject_bandit() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["tool"]["bandit"]


def test_skips_match_pyproject():
    ini_skips = [s.strip() for s in _ini()["skips"].split(",") if s.strip()]
    assert ini_skips == _pyproject_bandit()["skips"]


def test_every_excluded_dir_is_represented():
    """Same directories, allowing for the glob form the INI needs.

    Compared as a set of directory names rather than literal strings: the INI
    must write `*/tests/*` where pyproject.toml writes `tests`, so a string
    comparison would fail on correct configuration.
    """
    ini_globs = [p.strip() for p in _ini()["exclude"].split(",") if p.strip()]
    ini_dirs = {p.strip("*/") for p in ini_globs}
    for name in _pyproject_bandit()["exclude_dirs"]:
        assert name in ini_dirs, f"{name} excluded in pyproject.toml but not in .bandit"


def test_ini_uses_the_exclude_key_not_exclude_dirs():
    """`exclude_dirs` parses fine in an INI and is silently ignored by bandit.

    That failure mode is invisible — the file looks right and the directory is
    still scanned — so the key name is pinned rather than trusted.
    """
    section = _ini()
    assert "exclude" in section
    assert "exclude_dirs" not in section


def test_exclusions_are_globs_not_bare_names():
    # `exclude = tests` leaves tests/ scanned; only a glob matches the walked path.
    for pattern in (p.strip() for p in _ini()["exclude"].split(",")):
        assert "*" in pattern, f"{pattern!r} is a bare name and will not match"


def test_bandit_defaults_are_not_lost():
    """Setting `exclude` replaces bandit's built-in list rather than adding to it."""
    patterns = _ini()["exclude"]
    for expected in (".git", "__pycache__", ".tox", ".eggs"):
        assert expected in patterns, f"bandit's default exclusion {expected} was dropped"


@pytest.mark.parametrize("args", [["--ini", str(BANDIT_INI)], ["-c", str(PYPROJECT)]])
def test_both_config_paths_agree_on_the_shipped_tools(args):
    """The property that matters: the two configurations produce the same verdict.

    Runs the real binary rather than comparing parsed values, so a key bandit
    accepts but ignores cannot pass this.
    """
    result = subprocess.run(
        [sys.executable, "-m", "bandit", *args, "-q", "-r", "skills/", "scripts/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"bandit {args[0]} reported issues:\n{result.stdout[-2000:]}"
