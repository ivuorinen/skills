"""Tests for scripts/check-make-help.py."""

import importlib.util
import runpy
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "check-make-help.py"
_spec = importlib.util.spec_from_file_location("check_make_help", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_HELP_BLOCK = 'help:\n\t@echo "Available targets:"\n\t@echo "  build        — do it"\n\n'


def _makefile(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "Makefile"
    p.write_text(body, encoding="utf-8")
    return p


class TestParsing:
    def test_reads_targets_help_entries_and_phony(self, tmp_path):
        p = _makefile(tmp_path, ".PHONY: build help\n\n" + _HELP_BLOCK + "build:\n\techo hi\n")
        targets, listed, phony = _mod.read_makefile(p)

        assert targets == {"help", "build"}
        assert listed == {"build"}
        assert phony == {"build", "help"}

    def test_a_variable_assignment_is_not_a_target(self, tmp_path):
        """`UV := uv run` looks like `name:` and is not a target.

        Counting it would report a phantom missing from help on every run.
        """
        p = _makefile(tmp_path, "uv := uv run --quiet\n.PHONY: help\n\n" + _HELP_BLOCK)
        targets, _, _ = _mod.read_makefile(p)
        assert "uv" not in targets

    def test_a_makefile_with_no_help_target_reports_every_target_as_undocumented(self, tmp_path):
        """No help block is not "nothing to check" — it is every command
        undiscoverable, which is the strongest form of the defect."""
        p = _makefile(tmp_path, ".PHONY: build\n\nbuild:\n\techo hi\n")
        targets, listed, phony = _mod.read_makefile(p)

        assert targets == {"build"}
        assert listed == set()
        assert _mod.drift(targets, listed, phony) == [
            "target 'build' is not listed in `make help` — nobody can discover it"
        ]

    def test_help_is_found_when_it_is_the_first_target(self, tmp_path):
        """Searching for "\\nhelp:" misses a Makefile that opens with it.

        The failure is silent and inverted: no help entries are collected, so
        every target reports as undocumented rather than the file erroring.
        """
        p = _makefile(tmp_path, _HELP_BLOCK + ".PHONY: build help\n\nbuild:\n\techo hi\n")
        targets, listed, _ = _mod.read_makefile(p)

        assert listed == {"build"}
        assert _mod.drift(targets, listed, {"build", "help"}) == []

    def test_echo_lines_outside_the_help_recipe_are_not_help_entries(self, tmp_path):
        """Scanning the whole file for @echo would collect every other target's
        output as though it documented a command."""
        body = (
            ".PHONY: build help\n\n"
            + _HELP_BLOCK
            + 'build:\n\t@echo "  ghost        — printed by build, not a help entry"\n'
        )
        _, listed, _ = _mod.read_makefile(_makefile(tmp_path, body))
        assert listed == {"build"}


class TestDrift:
    def test_target_missing_from_help(self):
        problems = _mod.drift({"build", "ship"}, {"build"}, {"build", "ship"})
        assert len(problems) == 1
        assert "'ship' is not listed" in problems[0]

    def test_help_entry_with_no_target(self):
        problems = _mod.drift({"build"}, {"build", "ghost"}, {"build"})
        assert any("lists 'ghost'" in p for p in problems)

    def test_target_missing_from_phony(self):
        """Make silently skips a target whose name matches a real file, which
        takes the gate out of the build without failing it."""
        problems = _mod.drift({"build"}, {"build"}, set())
        assert any("missing from .PHONY" in p for p in problems)

    def test_help_and_all_are_exempt(self):
        """`help` documenting itself is noise, and `all` is the default alias."""
        assert _mod.drift({"help", "all"}, set(), set()) == []

    def test_agreement_reports_nothing(self):
        assert _mod.drift({"build"}, {"build"}, {"build"}) == []


class TestCli:
    def test_this_repos_makefile_agrees(self, capsys, monkeypatch):
        """The gate runs against the real Makefile, so this is the live contract."""
        monkeypatch.setattr(sys, "argv", ["check-make-help.py"])
        _mod.main()
        assert "agree" in capsys.readouterr().out

    def test_drift_exits_one_and_names_each_mismatch(self, tmp_path, capsys, monkeypatch):
        body = ".PHONY: help\n\n" + _HELP_BLOCK + "build:\n\techo hi\nship:\n\techo hi\n"
        monkeypatch.setattr(sys, "argv", ["x", str(_makefile(tmp_path, body))])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "'ship' is not listed" in out
        assert "missing from .PHONY" in out

    def test_help_flag_prints_usage(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["x", "--help"])
        _mod.main()
        assert "make help" in capsys.readouterr().out

    def test_too_many_arguments_is_a_usage_error(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["x", "a", "b"])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 2
        assert "Usage:" in capsys.readouterr().err

    def test_unreadable_makefile_exits_one(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["x", str(tmp_path / "nope" / "Makefile")])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1
        assert "cannot read" in capsys.readouterr().err

    def test_runs_as_a_script(self, capsys, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["check-make-help.py"])
        runpy.run_path(str(_TOOL), run_name="__main__")
        assert "agree" in capsys.readouterr().out
