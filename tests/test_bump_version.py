"""Tests for scripts/bump-version.py — bump_version(), update_toml(), render_json(), main()."""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
REPO_ROOT = SCRIPTS_DIR.parent


class _Result:
    """Stand-in for CompletedProcess in the relock tests."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        """Store the three fields relock() reads."""
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


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
        # Assert the message, not just the type: SystemExit(0) is also a SystemExit,
        # so a bare `pytest.raises(SystemExit)` accepts a *successful* exit here.
        with pytest.raises(SystemExit) as exc:
            _load_mod().bump_version("1.2.3", "bogus")
        assert "unknown part 'bogus'" in str(exc.value)

    def test_malformed_version_exits(self):
        with pytest.raises(SystemExit) as exc:
            _load_mod().bump_version("1.2", "patch")
        assert "not in MAJOR.MINOR.PATCH form" in str(exc.value)


class TestUpdateToml:
    def _run(self, tmp_path, toml_content, new_version):
        mod = _load_mod()
        mod.__dict__["REPO_ROOT"] = tmp_path  # set the module global (typed-clean)
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
        mod.__dict__["REPO_ROOT"] = tmp_path  # set the module global (typed-clean)
        toml = '[build-system]\nrequires = ["setuptools"]\n'
        (tmp_path / "pyproject.toml").write_text(toml, encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            mod.update_toml("pyproject.toml", "2.0.0")
        assert exc.value.code == 1
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


class TestRelock:
    """relock() must never abort the bump: the manifests are already written by
    the time it runs, so every failure arm reports and returns False."""

    def _mod(self, tmp_path, *, lockfile=True):
        mod = _load_mod()
        mod.__dict__["REPO_ROOT"] = tmp_path
        if lockfile:
            (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
        return mod

    def test_success_returns_true(self, tmp_path, monkeypatch, capsys):
        mod = self._mod(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/uv")
        monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result())
        assert mod.relock() is True
        assert "updated uv.lock" in capsys.readouterr().out

    def test_uv_absent_is_reported_not_raised(self, tmp_path, monkeypatch, capsys):
        mod = self._mod(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: None)
        assert mod.relock() is False
        assert "uv not on PATH" in capsys.readouterr().out

    def test_missing_lockfile_is_reported_not_raised(self, tmp_path, monkeypatch, capsys):
        mod = self._mod(tmp_path, lockfile=False)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/uv")
        assert mod.relock() is False
        assert "no lockfile" in capsys.readouterr().out

    def test_nonzero_exit_names_the_failure(self, tmp_path, monkeypatch, capsys):
        mod = self._mod(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/uv")
        monkeypatch.setattr(
            mod.subprocess,
            "run",
            lambda *_a, **_k: _Result(returncode=2, stderr="no solution found\n"),
        )
        assert mod.relock() is False
        assert "no solution found" in capsys.readouterr().out

    def test_silent_nonzero_exit_still_reports(self, tmp_path, monkeypatch, capsys):
        """A failure with no output would otherwise print a bare dash."""
        mod = self._mod(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/uv")
        monkeypatch.setattr(mod.subprocess, "run", lambda *_a, **_k: _Result(returncode=2))
        assert mod.relock() is False
        assert "no output" in capsys.readouterr().out

    def test_timeout_is_reported_not_raised(self, tmp_path, monkeypatch, capsys):
        mod = self._mod(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/uv")

        def _hang(*_a, **_k):
            """A cold-cache resolve against an unreachable index."""
            raise mod.subprocess.TimeoutExpired(["uv", "lock"], mod.LOCK_TIMEOUT)

        monkeypatch.setattr(mod.subprocess, "run", _hang)
        assert mod.relock() is False
        assert "timed out" in capsys.readouterr().out

    def test_oserror_is_reported_not_raised(self, tmp_path, monkeypatch, capsys):
        mod = self._mod(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: "/usr/bin/uv")

        def _boom(*_a, **_k):
            """exec failure — permissions, ENOEXEC."""
            raise OSError("exec format error")

        monkeypatch.setattr(mod.subprocess, "run", _boom)
        assert mod.relock() is False
        assert "could not run" in capsys.readouterr().out

    def test_failed_relock_tells_the_user_to_run_uv_lock(self, tmp_path, monkeypatch, capsys):
        """Silence here would leave a bumped tree failing `make lock-check` with
        no hint about which command fixes it."""
        mod = _load_mod()
        mod.__dict__["REPO_ROOT"] = tmp_path
        TestMain()._make_repo(tmp_path)
        monkeypatch.setattr(mod.shutil, "which", lambda _n: None)
        monkeypatch.setattr(sys, "argv", ["bump-version.py", "patch"])
        assert mod.main() == 0
        assert "Run `uv lock`" in capsys.readouterr().out


# ── the gate itself: `make check` must actually run lock-check ────────────────


def test_make_check_runs_lock_check():
    """The Validate job runs `make check` as a single invocation, so the Makefile
    is the only place CI learns about a gate. A lock-check target that exists but
    is absent from `check` is dead — the drift it catches reaches the tag anyway,
    which is exactly how 3.0.0 shipped a 2.0.0 lockfile."""
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    check_line = next(line for line in makefile.splitlines() if line.startswith("check:"))
    assert "lock-check" in check_line, f"`check` does not run lock-check: {check_line}"
    assert "uv lock --check" in makefile, "lock-check must use uv's own staleness test"


def test_release_workflow_syncs_the_lockfile():
    """release-please rewrites pyproject but has no updater for uv.lock, so
    without this job every release PR arrives failing lock-check."""
    workflow = (REPO_ROOT / ".github/workflows/release-please.yml").read_text(encoding="utf-8")
    assert "sync-lockfile:" in workflow
    assert "uv lock" in workflow
    # The commit-lint gate rejects a non-conventional subject, which would fail
    # the release PR in a second, more confusing way.
    assert "chore: sync uv.lock" in workflow


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

    def test_main_relocks_after_writing_pyproject(self, tmp_path, monkeypatch):
        """`uv lock` reads the version out of pyproject, so it has to run after the
        manifests are on disk — running it first would re-lock the OLD version and
        leave `make lock-check` failing on a freshly bumped tree."""
        self._make_repo(tmp_path)
        (tmp_path / "uv.lock").write_text("# lock\n", encoding="utf-8")
        mod = _load_mod()
        mod.__dict__["REPO_ROOT"] = tmp_path
        monkeypatch.setattr(mod.shutil, "which", lambda _name: "/usr/bin/uv")
        seen = {}

        def _fake_lock(cmd, *a, **k):
            """Record the version pyproject carried at the moment uv lock ran."""
            seen["cmd"] = cmd
            seen["pyproject"] = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
            return _Result()

        monkeypatch.setattr(mod.subprocess, "run", _fake_lock)
        monkeypatch.setattr(sys, "argv", ["bump-version.py", "minor"])
        assert mod.main() == 0
        assert seen["cmd"] == ["/usr/bin/uv", "lock"]
        assert 'version = "1.1.0"' in seen["pyproject"], "uv lock ran before pyproject was written"

    def test_main_bumps_all_five_manifests(self, tmp_path, monkeypatch):
        self._make_repo(tmp_path)
        mod = _load_mod()
        mod.__dict__["REPO_ROOT"] = tmp_path  # set the module global (typed-clean)
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
        mod.__dict__["REPO_ROOT"] = tmp_path  # set the module global (typed-clean)
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
        mod.__dict__["REPO_ROOT"] = tmp_path  # set the module global (typed-clean)
        monkeypatch.setattr(sys, "argv", ["bump-version.py", "minor"])
        with pytest.raises(json.JSONDecodeError) as exc:
            mod.main()
        # `doc` is the text that failed to parse — pins the failure to the manifest
        # this test broke, not to some other malformed file.
        assert "BROKEN" in exc.value.doc
        # package.json (the first manifest) is untouched: rendering aborted before any write.
        assert (
            json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))["version"]
            == "1.0.0"
        )


def test_module_runs_as_a_script(monkeypatch, capsys):
    """Covers the `if __name__ == '__main__'` body — the only wiring to main().

    An unrecognised part exits before any manifest is read or written, so this
    never touches the real repo's version files.
    """
    monkeypatch.setattr(sys, "argv", ["bump-version.py", "bogus"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(SCRIPTS_DIR / "bump-version.py"), run_name="__main__")
    assert exc.value.code == 1
    assert "Usage:" in capsys.readouterr().out
