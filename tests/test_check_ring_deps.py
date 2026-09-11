"""Tests for scripts/check-ring-deps.py.

The tool's reason for existing is the edge no import graph sees, so the tests
that matter are the negative controls: a violation smuggled in through a
string-path load must fail the gate exactly like a plain import would. A tool
that only ever passes on this repo is indistinguishable from one that resolves
nothing.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_TOOL = _REPO / "scripts" / "check-ring-deps.py"

_spec = importlib.util.spec_from_file_location("check_ring_deps", _TOOL)
rd = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
# Registered before exec, unlike the sibling tool tests: `@dataclass` resolves
# its annotations through `sys.modules[cls.__module__]`, which is None for a
# module that is executing but unregistered.
sys.modules[_spec.name] = rd  # type: ignore[union-attr]
_spec.loader.exec_module(rd)  # type: ignore[union-attr]


def _tree(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


_PATH_LOAD = """\
import importlib.util
from pathlib import Path

_T = Path(__file__).parent.parent / "{target}"
_s = importlib.util.spec_from_file_location("t", _T)
"""


# ── the real repository ───────────────────────────────────────────────────────


class TestThisRepo:
    def test_ring_rule_holds(self, capsys):
        assert rd.main([str(_REPO), "--check"]) == 0
        assert "ring rule holds" in capsys.readouterr().out

    def test_the_cross_ring_string_path_edges_are_reported(self, capsys):
        """The edges that exist at runtime and in no import statement. If these
        ever stop appearing, the tool has silently stopped resolving and the
        graph it prints is a lie.

        Each one is a hyphen-named module, which is the whole reason it is
        reached by path: `check-rules-anatomy` and `bench-retrieval` cannot be
        written as an `import` statement at all.
        """
        rd.main([str(_REPO)])
        out = capsys.readouterr().out
        expected = {
            "scripts/common.py -> skills/nitpicker/scripts/findings.py",
            "scripts/validate-rules.py -> skills/nitpicker/scripts/check-rules-anatomy.py",
            "scripts/bench-recall.py -> scripts/bench-retrieval.py",
        }
        for edge in expected:
            assert edge in out
        # Counted, not just contained: an edge that stops resolving disappears
        # from the graph silently, and only the total notices.
        assert out.count("[string-path load]") == len(expected)

    def test_every_module_load_resolves(self):
        assert rd.build(_REPO).errors == []


# ── violations are caught, whichever shape they arrive in ─────────────────────


class TestViolations:
    def test_inner_ring_importing_outer_ring_is_a_violation(self, tmp_path):
        _tree(
            tmp_path,
            {
                "skills/x/scripts/inner.py": "import helper\n",
                "scripts/helper.py": "x = 1\n",
            },
        )
        bad = rd.violations(rd.build(tmp_path))
        assert len(bad) == 1
        assert "must not depend on internal" in bad[0]

    def test_inner_ring_reaching_outer_ring_by_string_path_is_also_a_violation(self, tmp_path):
        """The whole point. This edge is invisible to `import`-based analysis,
        so a tool that missed it would call this tree clean."""
        _tree(
            tmp_path,
            {
                "skills/x/scripts/inner.py": _PATH_LOAD.format(target="../../../scripts/helper.py"),
                "scripts/helper.py": "x = 1\n",
            },
        )
        g = rd.build(tmp_path)
        assert any(e.kind == "path" for e in g.edges), "the string-path edge was not resolved"
        assert len(rd.violations(g)) == 1

    def test_check_flag_turns_a_violation_into_exit_1(self, tmp_path, capsys):
        _tree(
            tmp_path,
            {
                "skills/x/scripts/inner.py": "import helper\n",
                "scripts/helper.py": "x = 1\n",
            },
        )
        assert rd.main([str(tmp_path), "--check"]) == 1
        assert "Ring violations" in capsys.readouterr().err

    def test_outward_ok_inward_direction_is_legal(self, tmp_path):
        _tree(
            tmp_path,
            {
                "skills/x/scripts/inner.py": "x = 1\n",
                "scripts/helper.py": _PATH_LOAD.format(target="skills/x/scripts/inner.py"),
            },
        )
        g = rd.build(tmp_path)
        assert [e.kind for e in g.edges] == ["path"]
        assert rd.violations(g) == []


# ── loads the tool cannot resolve are errors, never silence ───────────────────


class TestUnresolvable:
    def test_a_computed_path_outside_the_modules_own_directory_is_an_error(self, tmp_path):
        _tree(
            tmp_path,
            {
                "scripts/helper.py": (
                    "import importlib.util, os\n"
                    "from pathlib import Path\n"
                    "_s = importlib.util.spec_from_file_location('t', Path(os.environ['X']))\n"
                ),
                "skills/x/scripts/inner.py": "x = 1\n",
            },
        )
        errors = rd.build(tmp_path).errors
        assert len(errors) == 1 and "not statically resolvable" in errors[0]

    def test_a_name_assigned_twice_in_one_scope_is_an_error(self, tmp_path):
        _tree(
            tmp_path,
            {
                "scripts/helper.py": (
                    "import importlib.util\n"
                    "from pathlib import Path\n"
                    "_T = Path('a.py')\n"
                    "_T = Path('b.py')\n"
                    "_s = importlib.util.spec_from_file_location('t', _T)\n"
                ),
                "skills/x/scripts/inner.py": "x = 1\n",
            },
        )
        errors = rd.build(tmp_path).errors
        assert len(errors) == 1 and "assigned more than once" in errors[0]

    def test_a_literal_path_naming_no_file_is_an_error(self, tmp_path):
        _tree(
            tmp_path,
            {
                "scripts/helper.py": _PATH_LOAD.format(target="nope/missing.py"),
                "skills/x/scripts/inner.py": "x = 1\n",
            },
        )
        errors = rd.build(tmp_path).errors
        assert len(errors) == 1 and "resolves to no file on disk" in errors[0]

    def test_an_unresolvable_load_fails_check_even_with_no_violation(self, tmp_path, capsys):
        _tree(
            tmp_path,
            {
                "scripts/helper.py": _PATH_LOAD.format(target="nope/missing.py"),
                "skills/x/scripts/inner.py": "x = 1\n",
            },
        )
        assert rd.main([str(tmp_path), "--check"]) == 1
        assert "Unresolvable module loads" in capsys.readouterr().err

    def test_an_unparseable_module_is_reported_rather_than_skipped(self, tmp_path):
        _tree(
            tmp_path,
            {
                "skills/x/scripts/inner.py": "def broken(:\n",
                "scripts/helper.py": "x = 1\n",
            },
        )
        errors = rd.build(tmp_path).errors
        assert len(errors) == 1 and "cannot parse" in errors[0]


# ── scope handling ────────────────────────────────────────────────────────────


class TestScoping:
    def test_a_sibling_load_is_intra_ring_not_a_violation(self, tmp_path):
        """`mcp_server._load_bundled` builds its path from its own directory. It
        cannot cross a ring, so it is recorded without a target file."""
        _tree(
            tmp_path,
            {
                "skills/x/scripts/inner.py": (
                    "import importlib.util\n"
                    "from pathlib import Path\n"
                    "def load(stem):\n"
                    "    path = Path(__file__).resolve().parent / f'{stem}.py'\n"
                    "    return importlib.util.spec_from_file_location(stem, path)\n"
                ),
                "scripts/helper.py": "x = 1\n",
            },
        )
        g = rd.build(tmp_path)
        assert [e.kind for e in g.edges] == ["path-sibling"]
        assert rd.violations(g) == []

    def test_the_same_name_in_two_functions_does_not_read_as_ambiguous(self, tmp_path):
        """A module-flat scan of `mcp_server.py` reports `path` as assigned twice
        and resolves neither. Scopes are what keep both readable."""
        _tree(
            tmp_path,
            {
                "skills/x/scripts/inner.py": (
                    "import importlib.util\n"
                    "from pathlib import Path\n"
                    "def one(stem):\n"
                    "    path = Path(__file__).resolve().parent / f'{stem}.py'\n"
                    "    return importlib.util.spec_from_file_location(stem, path)\n"
                    "def two(mod):\n"
                    "    path = Path(getattr(mod, '__file__', '') or '')\n"
                    "    return path.is_file()\n"
                ),
                "scripts/helper.py": "x = 1\n",
            },
        )
        g = rd.build(tmp_path)
        assert g.errors == []
        assert [e.kind for e in g.edges] == ["path-sibling"]


# ── the agentic-tool contract ─────────────────────────────────────────────────


class TestCliContract:
    def test_help_is_stdout_exit_zero(self, capsys):
        with pytest.raises(SystemExit) as exc:
            rd.main(["--help"])
        assert exc.value.code == 0
        assert "ring rule" in capsys.readouterr().out

    def test_a_bad_root_is_exit_2(self, capsys, tmp_path):
        assert rd.main([str(tmp_path / "nope")]) == 2
        assert "not a directory" in capsys.readouterr().err

    def test_a_root_matching_no_ring_is_exit_2_not_a_clean_pass(self, capsys, tmp_path):
        """An empty result must never read as 'no violations'. A stale glob has
        to fail loudly or the gate quietly stops checking anything."""
        assert rd.main([str(tmp_path), "--check"]) == 2
        assert "globs are stale" in capsys.readouterr().err

    def test_entry_point_is_guarded(self):
        assert '__name__ == "__main__"' in _TOOL.read_text()


class TestResolveTargetEdges:
    """`_resolve_target` guesses the anchor by walking up from the loading
    module, so its refusals are what keep a wrong guess from becoming an edge."""

    def test_a_segment_chain_not_ending_in_py_resolves_to_nothing(self, tmp_path):
        assert rd._resolve_target(tmp_path, tmp_path / "scripts" / "h.py", ["a", "b"]) is None

    def test_no_segments_resolves_to_nothing(self, tmp_path):
        assert rd._resolve_target(tmp_path, tmp_path / "scripts" / "h.py", []) is None

    def test_a_match_outside_the_repository_root_is_refused(self, tmp_path):
        """`..` can walk a candidate back out of the tree. Naming a file the
        repo does not contain would put a fictional node in the graph."""
        root = tmp_path / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "h.py").write_text("x = 1\n")
        (tmp_path / "outside.py").write_text("x = 1\n")
        assert rd._resolve_target(root, root / "scripts" / "h.py", ["..", "outside.py"]) is None

    def test_the_upward_search_stops_at_the_root(self, tmp_path):
        """Without the bound, a file anywhere above the repo could satisfy the
        chain and be reported as an in-repo dependency."""
        root = tmp_path / "repo"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "h.py").write_text("x = 1\n")
        (tmp_path / "stray.py").write_text("x = 1\n")
        assert rd._resolve_target(root, root / "scripts" / "h.py", ["stray.py"]) is None


class TestDegenerateCalls:
    def test_spec_from_file_location_without_a_path_argument_is_an_error(self, tmp_path):
        _tree(
            tmp_path,
            {
                "scripts/helper.py": (
                    "import importlib.util\n_s = importlib.util.spec_from_file_location('t')\n"
                ),
                "skills/x/scripts/inner.py": "x = 1\n",
            },
        )
        errors = rd.build(tmp_path).errors
        assert len(errors) == 1 and "no path argument" in errors[0]

    def test_a_path_from_a_function_parameter_is_unresolvable_not_silent(self, tmp_path):
        _tree(
            tmp_path,
            {
                "scripts/helper.py": (
                    "import importlib.util\n"
                    "def load(p):\n"
                    "    return importlib.util.spec_from_file_location('t', p)\n"
                ),
                "skills/x/scripts/inner.py": "x = 1\n",
            },
        )
        errors = rd.build(tmp_path).errors
        assert len(errors) == 1 and "not statically resolvable" in errors[0]

    def test_a_module_loading_itself_is_not_an_edge(self, tmp_path):
        _tree(
            tmp_path,
            {
                "scripts/helper.py": _PATH_LOAD.format(target="scripts/helper.py"),
                "skills/x/scripts/inner.py": "x = 1\n",
            },
        )
        g = rd.build(tmp_path)
        assert g.edges == [] and g.errors == []


def test_an_edge_to_an_unknown_module_is_not_ranked():
    """`violations` ranks by ring. An endpoint outside every ring has no rank,
    and guessing one would invent a verdict."""
    g = rd.Graph(modules={"scripts/a.py": "internal"}, edges=[rd.Edge("scripts/a.py", "?", "path")])
    assert rd.violations(g) == []


def test_runs_as_a_script(capsys):
    """Covers the `__main__` body — the only wiring between the CLI and main()."""
    import runpy

    argv = sys.argv[:]
    sys.argv = [str(_TOOL), str(_REPO), "--check"]
    try:
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(_TOOL), run_name="__main__")
    finally:
        sys.argv = argv
    assert exc.value.code == 0
    assert "ring rule holds" in capsys.readouterr().out


def test_runner_contract():
    """Internal tooling runs under uv with a PEP-723 block, per use-uv-runner."""
    head = _TOOL.read_text().splitlines()
    assert head[0] == "#!/usr/bin/env -S uv run --quiet"
    assert "# /// script" in "\n".join(head[:10])


def test_module_is_importable_without_side_effects(capsys):
    """Loading the tool must not run it — the `__main__` guard is what keeps an
    import from walking the tree and printing a graph."""
    spec = importlib.util.spec_from_file_location("probe_ring_deps", _TOOL)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[spec.name] = module  # type: ignore[union-attr]
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
    finally:
        del sys.modules[spec.name]  # type: ignore[union-attr]
    assert capsys.readouterr().out == ""
