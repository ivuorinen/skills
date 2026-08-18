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


def _discovered(targets: list[str]) -> list[str]:
    """Files bandit would actually scan under `.bandit`'s exclusions.

    Uses bandit's own discovery rather than reasoning about the patterns. The
    pattern syntax is not the property worth asserting — whether a given path is
    excluded depends on the target bandit was invoked with, so only running the
    matcher answers it.
    """
    from bandit.core import config as bandit_config
    from bandit.core import manager

    mgr = manager.BanditManager(bandit_config.BanditConfig(), "file")
    mgr.discover_files(targets, True, _ini()["exclude"])
    return mgr.files_list


# Both spellings a runner might use: the repo root, or each directory named.
_TARGET_FORMS = [["."], ["skills/", "scripts/", "tests/"]]


@pytest.mark.filterwarnings("ignore:The verify_requirements argument:DeprecationWarning")
@pytest.mark.parametrize("targets", _TARGET_FORMS, ids=["root", "explicit-dirs"])
def test_every_pyproject_exclusion_is_honoured_by_the_ini(targets):
    """Behaviour, under both invocation forms.

    `exclude = tests` excludes tests/ when bandit is given `tests` as a target
    and does not when it is given `.`; `*/tests/*` is the exact reverse. A test
    that asserted pattern *syntax* enforced a rule that is false half the time,
    which is why this runs the matcher instead.
    """
    scanned = _discovered(targets)
    for name in _pyproject_bandit()["exclude_dirs"]:
        offenders = [f for f in scanned if f"/{name}/" in f or f.startswith(f"{name}/")]
        assert not offenders, f"{name} is excluded in pyproject.toml but scanned: {offenders[:3]}"


@pytest.mark.filterwarnings("ignore:The verify_requirements argument:DeprecationWarning")
@pytest.mark.parametrize("targets", _TARGET_FORMS, ids=["root", "explicit-dirs"])
def test_the_shipped_tools_are_still_scanned(targets):
    """The other direction, and the one that matters for security.

    The sync check above only proves nothing is under-excluded. An exclusion
    added to `.bandit` and not to pyproject.toml — `*/skills/*`, say — would
    satisfy it while silently taking the shipped tools out of bandit's reach.
    """
    scanned = _discovered(targets)
    assert any("skills/nitpicker/scripts/" in f for f in scanned), (
        "no shipped tool is being scanned — an over-broad exclusion in .bandit"
    )
    assert any("scripts/hooks/" in f for f in scanned), "the hooks are not being scanned"


def test_ini_uses_the_exclude_key_not_exclude_dirs():
    """`exclude_dirs` parses fine in an INI and is silently ignored by bandit.

    That failure mode is invisible — the file looks right and the directory is
    still scanned — so the key name is pinned rather than trusted.
    """
    section = _ini()
    assert "exclude" in section
    assert "exclude_dirs" not in section


def test_each_excluded_dir_is_listed_in_both_forms():
    """Bare and globbed, because neither spelling works for every invocation.

    Not a syntax preference: the behavioural tests above fail if this drifts,
    and this one names the reason so the next editor does not "tidy" the
    apparent duplication away.
    """
    patterns = {p.strip() for p in _ini()["exclude"].split(",") if p.strip()}
    for name in _pyproject_bandit()["exclude_dirs"]:
        assert name in patterns, f"{name} missing its bare form (needed when it is the target)"
        assert f"*/{name}/*" in patterns, f"{name} missing its glob form (needed when target is .)"


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
