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


# Importing bandit's CLI pulls in stevedore, which warns about a no-op argument
# in its own plugin loader. Upstream, not actionable here, and scoped to the two
# tests that need the import so it never hides a warning from our own code.
@pytest.mark.filterwarnings("ignore:The verify_requirements argument:DeprecationWarning")
def test_bandits_own_ini_loader_returns_the_skips():
    """Asserted through the loader `--ini` actually calls, not a string compare.

    The silent-ignore trap is INI-side: a key bandit accepts and drops leaves the
    file looking correct while changing nothing. `_get_options_from_ini` is what
    `--ini` invokes, so a value that does not reach bandit does not reach this
    assertion either. The pyproject side needs no equivalent — `-c
    pyproject.toml` is exercised by `make security` and the pre-commit hook on
    every run, and a TOML table has no such failure mode.

    Deliberately not a subprocess. An earlier version shelled out to the real
    binary, which was a stronger check but introduced a `subprocess.run` call
    that Codacy's bandit then reported as B603 — a new security finding created
    by a test whose subject is suppressing that very rule.
    """
    from bandit.cli.main import _get_options_from_ini

    ini = _get_options_from_ini(str(BANDIT_INI), None)
    assert ini is not None, ".bandit was not readable by bandit's own INI loader"
    assert [s.strip() for s in ini["skips"].split(",")] == _pyproject_bandit()["skips"]


@pytest.mark.filterwarnings("ignore:The verify_requirements argument:DeprecationWarning")
def test_bandit_reads_the_ini_exclusions_at_all():
    """`exclude_dirs` in an INI parses and is dropped; this proves `exclude` survives.

    The assertion is that bandit's INI loader returns the key — a config file it
    silently ignores is the failure this whole file exists to prevent.
    """
    from bandit.cli.main import _get_options_from_ini

    ini = _get_options_from_ini(str(BANDIT_INI), None)
    assert ini is not None, ".bandit was not readable by bandit's own INI loader"
    assert "exclude" in ini, "bandit's INI loader returned no exclusions"
    assert "tests" in ini["exclude"]
