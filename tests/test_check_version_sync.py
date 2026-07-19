"""Tests for scripts/check-version-sync.py — main() cross-manifest version check."""

import importlib.util
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _load_mod():
    """Load check-version-sync.py; code lives under __main__, so import has no side effects."""
    spec = importlib.util.spec_from_file_location(
        "check_version_sync_module",
        SCRIPTS_DIR / "check-version-sync.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _make_repo(
    tmp_path,
    *,
    package="1.0.0",
    pyproject='[project]\nname = "foo"\nversion = "1.0.0"\n',
    plugin="1.0.0",
    marketplace='{"plugins": [{"version": "1.0.0"}]}\n',
    manifest="1.0.0",
):
    (tmp_path / ".claude-plugin").mkdir()
    (tmp_path / "package.json").write_text(f'{{"version": "{package}"}}\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (tmp_path / ".claude-plugin/plugin.json").write_text(
        f'{{"version": "{plugin}"}}\n', encoding="utf-8"
    )
    (tmp_path / ".claude-plugin/marketplace.json").write_text(marketplace, encoding="utf-8")
    (tmp_path / ".release-please-manifest.json").write_text(
        f'{{".": "{manifest}"}}\n', encoding="utf-8"
    )


def _run(tmp_path):
    mod = _load_mod()
    mod.REPO_ROOT = tmp_path
    return mod.main()


def test_all_in_sync_returns_0(tmp_path):
    _make_repo(tmp_path)
    assert _run(tmp_path) == 0


def test_marketplace_mismatch_returns_1(tmp_path, capsys):
    _make_repo(tmp_path, marketplace='{"plugins": [{"version": "9.9.9"}]}\n')
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "marketplace.json" in out
    assert "9.9.9" in out


def test_second_stale_plugin_returns_1(tmp_path, capsys):
    """FIX 1: a mismatch in any plugin (not just the first) must be caught."""
    _make_repo(
        tmp_path,
        marketplace='{"plugins": [{"version": "1.0.0"}, {"version": "0.0.1"}]}\n',
    )
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "marketplace.json" in out
    assert "0.0.1" in out


def test_tool_section_version_ignored(tmp_path):
    """A differing [tool.*] version must not trip the [project] version check."""
    pyproject = '[project]\nversion = "1.0.0"\n\n[tool.poetry]\nversion = "9.9.9"\n'
    _make_repo(tmp_path, pyproject=pyproject)
    assert _run(tmp_path) == 0


def test_single_quoted_pyproject_version_no_false_alarm(tmp_path):
    """FIX 2: a valid single-quoted TOML version in sync must not be misread as missing."""
    _make_repo(tmp_path, pyproject="[project]\nname = 'foo'\nversion = '1.0.0'\n")
    assert _run(tmp_path) == 0


def test_pyproject_version_mismatch_returns_1(tmp_path, capsys):
    """The [project].version has its own branch (not the shared CHECKS loop); a
    drift there must fail the gate."""
    _make_repo(tmp_path, pyproject='[project]\nname = "foo"\nversion = "9.9.9"\n')
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "pyproject.toml" in out
    assert "9.9.9" in out


def test_malformed_pyproject_reports_error_not_crash(tmp_path, capsys):
    """Invalid TOML surfaces as a clean ERROR (return 1), never an uncaught TOMLDecodeError."""
    _make_repo(tmp_path, pyproject="[project\nversion = \n")
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "pyproject.toml" in out


def test_null_plugins_reports_error_and_keeps_checking(tmp_path, capsys):
    """A null 'plugins' raises TypeError in the extractor; an uncaught one would abort
    the loop, leaving the later manifests unchecked and a real mismatch masked."""
    _make_repo(tmp_path, marketplace='{"plugins": null}\n', manifest="9.9.9")
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "marketplace.json" in out
    # The manifest checked after marketplace.json must still be reported.
    assert ".release-please-manifest.json" in out
    assert "9.9.9" in out


def test_empty_plugins_array_reports_error_not_crash(tmp_path, capsys):
    """An empty plugins array must report a clean ERROR (return 1), never IndexError on vals[0]."""
    _make_repo(tmp_path, marketplace='{"plugins": []}\n')
    assert _run(tmp_path) == 1
    out = capsys.readouterr().out
    assert "marketplace.json" in out
    assert "no version entries" in out
