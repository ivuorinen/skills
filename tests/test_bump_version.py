"""Tests for scripts/bump-version.py — bump_version(), update_toml(), render_json(), main()."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def _load_mod():
    """Load bump-version.py; module code lives under __main__, so import has no side effects."""
    spec = importlib.util.spec_from_file_location(
        "bump_version_module",
        SCRIPTS_DIR / "bump-version.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class TestBumpVersion:
    def test_patch_bump(self):
        assert _load_mod().bump_version("1.2.3", "patch") == "1.2.4"

    def test_minor_bump_resets_patch(self):
        assert _load_mod().bump_version("1.2.3", "minor") == "1.3.0"

    def test_major_bump_resets_minor_and_patch(self):
        assert _load_mod().bump_version("1.2.3", "major") == "2.0.0"

    def test_unknown_part_exits(self):
        with pytest.raises(SystemExit):
            _load_mod().bump_version("1.2.3", "bogus")

    def test_malformed_version_exits(self):
        with pytest.raises(SystemExit):
            _load_mod().bump_version("1.2", "patch")


class TestUpdateToml:
    def _run(self, tmp_path, toml_content, new_version):
        mod = _load_mod()
        mod.REPO_ROOT = tmp_path
        (tmp_path / "pyproject.toml").write_text(toml_content, encoding="utf-8")
        return mod.update_toml("pyproject.toml", new_version)

    def test_project_version_updated(self, tmp_path):
        result = self._run(tmp_path, '[project]\nname = "foo"\nversion = "1.0.0"\n', "2.0.0")
        assert 'version = "2.0.0"' in result

    def test_tool_section_version_untouched(self, tmp_path):
        toml = '[project]\nname = "foo"\nversion = "1.0.0"\n\n[tool.poetry]\nversion = "9.9.9"\n'
        result = self._run(tmp_path, toml, "2.0.0")
        assert 'version = "2.0.0"' in result
        assert 'version = "9.9.9"' in result

    def test_project_after_other_section_found(self, tmp_path):
        toml = '[build-system]\nrequires = ["setuptools"]\n\n[project]\nversion = "1.0.0"\n'
        result = self._run(tmp_path, toml, "3.0.0")
        assert 'version = "3.0.0"' in result

    def test_missing_project_version_exits(self, tmp_path):
        mod = _load_mod()
        mod.REPO_ROOT = tmp_path
        toml = '[build-system]\nrequires = ["setuptools"]\n'
        (tmp_path / "pyproject.toml").write_text(toml, encoding="utf-8")
        with pytest.raises(SystemExit):
            mod.update_toml("pyproject.toml", "2.0.0")
        # File is never written by update_toml (it only returns content), so it stays intact.
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


class TestMain:
    def _make_repo(self, tmp_path):
        (tmp_path / ".claude-plugin").mkdir()
        (tmp_path / "package.json").write_text('{"version": "1.0.0"}\n', encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "foo"\nversion = "1.0.0"\n', encoding="utf-8"
        )
        (tmp_path / ".claude-plugin/plugin.json").write_text(
            '{"version": "1.0.0"}\n', encoding="utf-8"
        )
        (tmp_path / ".claude-plugin/marketplace.json").write_text(
            '{"plugins": [{"version": "1.0.0"}]}\n', encoding="utf-8"
        )
        (tmp_path / ".release-please-manifest.json").write_text(
            '{".": "1.0.0"}\n', encoding="utf-8"
        )

    def test_main_bumps_all_five_manifests(self, tmp_path, monkeypatch):
        self._make_repo(tmp_path)
        mod = _load_mod()
        mod.REPO_ROOT = tmp_path
        monkeypatch.setattr(sys, "argv", ["bump-version.py", "minor"])
        assert mod.main() == 0
        pkg = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
        plugin = json.loads((tmp_path / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        market = json.loads(
            (tmp_path / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
        )
        manifest = json.loads(
            (tmp_path / ".release-please-manifest.json").read_text(encoding="utf-8")
        )
        assert pkg["version"] == "1.1.0"
        assert 'version = "1.1.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
        assert plugin["version"] == "1.1.0"
        assert market["plugins"][0]["version"] == "1.1.0"
        assert manifest["."] == "1.1.0"

    def test_main_unknown_part_returns_1(self, tmp_path, monkeypatch):
        self._make_repo(tmp_path)
        mod = _load_mod()
        mod.REPO_ROOT = tmp_path
        monkeypatch.setattr(sys, "argv", ["bump-version.py", "bogus"])
        assert mod.main() == 1
        # Nothing written on the guard path.
        assert (
            json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))["version"]
            == "1.0.0"
        )

    def test_malformed_manifest_aborts_before_any_write(self, tmp_path, monkeypatch):
        """A broken manifest must abort the bump with no partial writes (parse-all-before-write)."""
        self._make_repo(tmp_path)
        (tmp_path / ".claude-plugin/marketplace.json").write_text(
            '{"plugins": [ BROKEN', encoding="utf-8"
        )
        mod = _load_mod()
        mod.REPO_ROOT = tmp_path
        monkeypatch.setattr(sys, "argv", ["bump-version.py", "minor"])
        with pytest.raises(json.JSONDecodeError):
            mod.main()
        # package.json (the first manifest) is untouched: rendering aborted before any write.
        assert (
            json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))["version"]
            == "1.0.0"
        )
