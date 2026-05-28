"""Tests for scripts/bump-version.py — bump_version() and update_toml()."""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _fake_read(self, encoding: str = "utf-8") -> str:
    """Return stub JSON matching each file's expected structure."""
    _ = encoding
    p = str(self)
    if "marketplace" in p:
        return '{"plugins": [{"version": "0.0.0"}]}'
    if "manifest" in p:
        return '{".": "0.0.0"}'
    return '{"version": "0.0.0"}'


def _load_mod():
    """Load bump-version.py without triggering its module-level file mutations."""
    spec = importlib.util.spec_from_file_location(
        "bump_version_module",
        SCRIPTS_DIR / "bump-version.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    with (
        patch.object(sys, "argv", ["bump-version.py", "patch"]),
        patch("pathlib.Path.read_text", _fake_read),
        patch("pathlib.Path.write_text", return_value=None),
        patch.object(sys, "exit"),  # suppress sys.exit from failed TOML parse at import time
    ):
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestBumpVersion:
    def test_patch_bump(self):
        mod = _load_mod()
        assert mod.bump_version("1.2.3", "patch") == "1.2.4"

    def test_minor_bump_resets_patch(self):
        mod = _load_mod()
        assert mod.bump_version("1.2.3", "minor") == "1.3.0"

    def test_major_bump_resets_minor_and_patch(self):
        mod = _load_mod()
        assert mod.bump_version("1.2.3", "major") == "2.0.0"

    def test_unknown_part_treated_as_patch(self):
        mod = _load_mod()
        assert mod.bump_version("1.2.3", "bogus") == "1.2.4"


class TestUpdateToml:
    def _run(self, tmp_path, toml_content, new_version):
        mod = _load_mod()
        setattr(mod, "REPO_ROOT", tmp_path)
        (tmp_path / "pyproject.toml").write_text(toml_content, encoding="utf-8")
        mod.update_toml("pyproject.toml", new_version)
        return (tmp_path / "pyproject.toml").read_text(encoding="utf-8")

    def test_project_version_updated(self, tmp_path):
        toml = '[project]\nname = "foo"\nversion = "1.0.0"\n'
        result = self._run(tmp_path, toml, "2.0.0")
        assert 'version = "2.0.0"' in result

    def test_tool_section_version_untouched(self, tmp_path):
        toml = (
            '[project]\nname = "foo"\nversion = "1.0.0"\n\n'
            '[tool.poetry]\nversion = "9.9.9"\n'
        )
        result = self._run(tmp_path, toml, "2.0.0")
        assert 'version = "2.0.0"' in result
        assert 'version = "9.9.9"' in result

    def test_project_after_other_section_found(self, tmp_path):
        toml = (
            '[build-system]\nrequires = ["setuptools"]\n\n'
            '[project]\nversion = "1.0.0"\n'
        )
        result = self._run(tmp_path, toml, "3.0.0")
        assert 'version = "3.0.0"' in result

    def test_missing_project_version_exits(self, tmp_path):
        mod = _load_mod()
        setattr(mod, "REPO_ROOT", tmp_path)
        toml = '[build-system]\nrequires = ["setuptools"]\n'
        (tmp_path / "pyproject.toml").write_text(toml, encoding="utf-8")
        with patch.object(sys, "exit") as mock_exit:
            mod.update_toml("pyproject.toml", "2.0.0")
        mock_exit.assert_called_once_with(1)
        assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == toml

    def test_project_subscope_not_matched_as_project(self, tmp_path):
        """[project.optional-dependencies] must not be treated as [project]."""
        toml = (
            '[project]\nversion = "1.0.0"\n\n'
            '[project.optional-dependencies]\nversion = "should-not-change"\n'
        )
        result = self._run(tmp_path, toml, "2.0.0")
        assert 'version = "2.0.0"' in result
        assert 'version = "should-not-change"' in result
