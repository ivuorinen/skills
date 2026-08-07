"""Tests for scripts/check-stdlib-only.py."""

import ast
import importlib.util
import runpy
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "scripts" / "check-stdlib-only.py"
_spec = importlib.util.spec_from_file_location("check_stdlib_only", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

find_violations = _mod.find_violations
find_runner_violations = _mod.find_runner_violations
REPO_ROOT = _mod.REPO_ROOT


def _internal(root: Path, name: str, body: str) -> None:
    d = root / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def _tool(root: Path, name: str, body: str) -> None:
    d = root / "skills" / "nitpicker" / "scripts"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body, encoding="utf-8")


def test_stdlib_imports_pass(tmp_path: Path) -> None:
    _tool(tmp_path, "ok.py", "import json\nimport urllib.request\nfrom pathlib import Path\n")
    assert find_violations(tmp_path) == []


def test_third_party_import_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "bad.py", "import json\nimport requests\n")
    problems = find_violations(tmp_path)
    assert len(problems) == 1
    assert "requests" in problems[0]
    assert "bad.py" in problems[0]


def test_uncheckable_flags_bare_exec() -> None:
    assert _mod._uncheckable_calls(ast.parse("exec('x')\n")) == ["exec"]


def test_uncheckable_flags_attribute_exec() -> None:
    # `builtins.exec(...)` is an ast.Attribute call — the bare-Name check missed it.
    tree = ast.parse("import builtins\nbuiltins.exec('import requests')\n")
    assert _mod._uncheckable_calls(tree) == ["exec"]


def test_uncheckable_flags_getattr_eval() -> None:
    assert _mod._uncheckable_calls(ast.parse("getattr(builtins, 'eval')('1')\n")) == ["eval"]


def test_uncheckable_ignores_non_builtins_receiver() -> None:
    # worker.exec()/getattr(worker, "eval") target some other object, not Python's
    # builtins — not a hidden import, so the gate must not falsely flag them.
    assert _mod._uncheckable_calls(ast.parse("worker.exec('x')\n")) == []
    assert _mod._uncheckable_calls(ast.parse("getattr(worker, 'eval')('1')\n")) == []


def test_first_party_sibling_allowed(tmp_path: Path) -> None:
    _tool(tmp_path, "common.py", "X = 1\n")
    _tool(tmp_path, "uses_sibling.py", "import common\n")
    assert find_violations(tmp_path) == []


def test_aliased_import_module_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "bad.py", "import importlib\nimp = importlib.import_module\nimp('requests')\n")
    assert any("requests" in p for p in find_violations(tmp_path))


def test_getattr_import_module_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "bad.py", "import importlib\ngetattr(importlib, 'import_module')('requests')\n")
    assert any("requests" in p for p in find_violations(tmp_path))


def test_importfrom_alias_import_module_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "bad.py", "from importlib import import_module as imp\nimp('requests')\n")
    assert any("requests" in p for p in find_violations(tmp_path))


def test_keyword_only_module_name_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "bad.py", "import importlib\nimportlib.import_module(name='requests')\n")
    assert any("requests" in p for p in find_violations(tmp_path))


def test_relative_import_ignored(tmp_path: Path) -> None:
    _tool(tmp_path, "rel.py", "from . import whatever\nfrom .mod import thing\n")
    assert find_violations(tmp_path) == []


def test_dynamic_string_import_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "dyn.py", "import importlib\nimportlib.import_module('requests')\n")
    problems = find_violations(tmp_path)
    assert len(problems) == 1
    assert "requests" in problems[0]


def test_dunder_import_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "dyn2.py", "__import__('yaml')\n")
    problems = find_violations(tmp_path)
    assert len(problems) == 1
    assert "yaml" in problems[0]


def test_non_utf8_reported_not_crashed(tmp_path: Path) -> None:
    d = tmp_path / "skills" / "nitpicker" / "scripts"
    d.mkdir(parents=True)
    (d / "latin1.py").write_bytes(b"# comment with \xe9\nimport json\n")
    problems = find_violations(tmp_path)  # must not raise UnicodeDecodeError
    assert len(problems) == 1
    assert "cannot parse" in problems[0]


def test_actual_shipped_tools_are_stdlib_only() -> None:
    # Regression guard on the real tree: the shipped tools must never gain a
    # third-party import (would break on consumer machines without uv).
    assert find_violations(REPO_ROOT) == []


def test_runner_shipped_correct_shebang_ok(tmp_path: Path) -> None:
    _tool(tmp_path, "ok.py", "#!/usr/bin/env python3\nimport json\n")
    assert find_runner_violations(tmp_path) == []


def test_runner_shipped_uv_shebang_flagged(tmp_path: Path) -> None:
    # A shipped tool carrying the internal uv shebang breaks under plain python3.
    _tool(tmp_path, "bad.py", "#!/usr/bin/env -S uv run --quiet\nimport json\n")
    assert any("bad.py" in p and "python3" in p for p in find_runner_violations(tmp_path))


def test_runner_shipped_pep723_block_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "meta.py", "#!/usr/bin/env python3\n# /// script\n# ///\nimport json\n")
    assert any("meta.py" in p and "/// script" in p for p in find_runner_violations(tmp_path))


def test_runner_internal_python3_shebang_flagged(tmp_path: Path) -> None:
    _internal(tmp_path, "tool.py", "#!/usr/bin/env python3\nimport json\n")
    assert any("scripts/tool.py" in p and "uv run" in p for p in find_runner_violations(tmp_path))


def test_runner_internal_shebangless_library_exempt(tmp_path: Path) -> None:
    _internal(tmp_path, "common.py", '"""lib."""\nX = 1\n')
    assert find_runner_violations(tmp_path) == []


def test_nested_shipped_tool_is_scanned(tmp_path: Path) -> None:
    # .pre-commit-config.yaml's pattern fires on nested shipped scripts, so the
    # glob here must reach them too — a non-recursive glob left them unchecked.
    d = tmp_path / "skills" / "x" / "scripts" / "lib"
    d.mkdir(parents=True)
    (d / "y.py").write_text("import requests\n", encoding="utf-8")
    problems = find_violations(tmp_path)
    assert len(problems) == 1
    assert "requests" in problems[0]


def test_nested_tool_importing_parent_dir_sibling_allowed(tmp_path: Path) -> None:
    _tool(tmp_path, "helper.py", "X = 1\n")
    nested = tmp_path / "skills" / "nitpicker" / "scripts" / "lib"
    nested.mkdir(parents=True)
    (nested / "y.py").write_text("import helper\n", encoding="utf-8")
    assert find_violations(tmp_path) == []


def test_exec_call_flagged(tmp_path: Path) -> None:
    # exec/eval can import anything from a string this check cannot read.
    _tool(tmp_path, "sneaky.py", "exec('import requests')\n")
    problems = find_violations(tmp_path)
    assert len(problems) == 1
    assert "exec()" in problems[0]


def test_eval_call_flagged(tmp_path: Path) -> None:
    _tool(tmp_path, "sneaky2.py", "x = eval('1 + 1')\n")
    assert any("eval()" in p for p in find_violations(tmp_path))


def test_main_checks_internal_scripts_when_no_shipped_tools(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # An empty shipped-tool glob must not short-circuit main(): the runner check
    # also covers internal tooling, and an empty glob is itself a failure.
    _internal(tmp_path, "tool.py", "#!/usr/bin/env python3\nimport json\n")
    monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path)
    assert _mod.main() == 1
    out = capsys.readouterr().out
    assert "uv run" in out
    assert "glob is stale" in out


def test_main_reports_ok_and_exits_zero_on_a_clean_tree(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _tool(tmp_path, "ok.py", "#!/usr/bin/env python3\nimport json\n")
    monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path)
    assert _mod.main() == 0
    assert "stdlib-only, runner contract intact" in capsys.readouterr().out


def test_main_exits_non_zero_and_names_the_non_stdlib_import(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    # The exit code is the only thing pre-commit and the CI Validate job observe.
    _tool(tmp_path, "bad.py", "#!/usr/bin/env python3\nimport requests\n")
    monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path)
    assert _mod.main() == 1
    out = capsys.readouterr().out
    assert "Non-stdlib imports in shipped skill tools:" in out
    assert "requests" in out
    assert "1 violation(s)." in out


def test_main_exits_non_zero_on_a_runner_contract_breach(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _tool(tmp_path, "bad.py", "#!/usr/bin/env -S uv run --quiet\nimport json\n")
    monkeypatch.setattr(_mod, "REPO_ROOT", tmp_path)
    assert _mod.main() == 1
    out = capsys.readouterr().out
    assert "Script-runner contract violations" in out
    assert "violation(s)." in out


def test_dynamic_import_with_a_computed_name_is_unresolvable(tmp_path: Path) -> None:
    # Documented limitation: only literal module names can be resolved statically.
    _tool(
        tmp_path,
        "dyn.py",
        "#!/usr/bin/env python3\nimport importlib\nname = 'requests'\n"
        "importlib.import_module(name)\n",
    )
    assert [p for p in find_violations(tmp_path) if "non-stdlib" in p] == []


def test_unparseable_shipped_tool_is_reported_not_skipped(tmp_path: Path) -> None:
    _tool(tmp_path, "broken.py", "#!/usr/bin/env python3\ndef (\n")
    assert any("cannot parse" in p for p in find_violations(tmp_path))


def test_unreadable_shipped_tool_is_reported_by_both_checks(tmp_path: Path) -> None:
    # A directory named like a module: read_text raises IsADirectoryError (an OSError).
    (tmp_path / "skills" / "nitpicker" / "scripts" / "wat.py").mkdir(parents=True)
    assert any("cannot parse" in p for p in find_violations(tmp_path))
    assert any("cannot read" in p for p in find_runner_violations(tmp_path))


def test_unreadable_internal_script_is_reported(tmp_path: Path) -> None:
    _tool(tmp_path, "ok.py", "#!/usr/bin/env python3\nimport json\n")
    (tmp_path / "scripts" / "wat.py").mkdir(parents=True)
    assert any("cannot read" in p for p in find_runner_violations(tmp_path))


def test_alias_tracking_ignores_non_name_assignment_targets(tmp_path: Path) -> None:
    """`d["k"] = import_module` binds no local name, so nothing is aliased and the
    later call is not treated as a dynamic import."""
    _tool(
        tmp_path,
        "sub.py",
        "#!/usr/bin/env python3\nimport importlib\nd = {}\n"
        'd["k"] = importlib.import_module\nd["k"]("requests")\n',
    )
    assert [p for p in find_violations(tmp_path) if "non-stdlib" in p] == []


def test_alias_tracking_ignores_unrelated_importlib_names(tmp_path: Path) -> None:
    """`from importlib import util` imports a name that is not an import function."""
    _tool(
        tmp_path,
        "u.py",
        "#!/usr/bin/env python3\nfrom importlib import util\nutil.find_spec('requests')\n",
    )
    assert [p for p in find_violations(tmp_path) if "non-stdlib" in p] == []


def test_call_expression_that_is_not_a_two_arg_getattr_is_not_an_import(tmp_path: Path) -> None:
    """Only `getattr(x, "import_module")(...)` counts; a one-arg getattr must not
    index args[1], and an unrelated call expression must not be treated as one."""
    _tool(
        tmp_path,
        "g.py",
        # Chained calls, so the call's *func* is itself an ast.Call — the branch
        # that indexes args[1] and must not do so when the arity is wrong.
        "#!/usr/bin/env python3\nimport importlib\n"
        "getattr(importlib)('requests')\n"
        "other(importlib, 'import_module')('requests')\n",
    )
    assert [p for p in find_violations(tmp_path) if "non-stdlib" in p] == []


def test_keyword_only_dynamic_import_without_a_name_kwarg(tmp_path: Path) -> None:
    """`import_module(package="x")` carries no module name — the keyword scan must
    exhaust without resolving one, rather than mis-reading the first keyword."""
    _tool(
        tmp_path,
        "kw.py",
        "#!/usr/bin/env python3\nimport importlib\nimportlib.import_module(package='.rel')\n",
    )
    assert [p for p in find_violations(tmp_path) if "non-stdlib" in p] == []


def test_name_kwarg_found_after_another_keyword(tmp_path: Path) -> None:
    """The scan must keep looking past a non-`name` keyword, not stop at the first."""
    _tool(
        tmp_path,
        "kw2.py",
        "#!/usr/bin/env python3\nimport importlib\n"
        "importlib.import_module(package='p', name='requests')\n",
    )
    assert any("non-stdlib import 'requests'" in p for p in find_violations(tmp_path))


def test_module_runs_as_a_script(monkeypatch) -> None:
    """Covers the `if __name__ == '__main__'` body — the only wiring to main()."""
    monkeypatch.setattr(_mod, "REPO_ROOT", REPO_ROOT)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(_TOOL), run_name="__main__")
    assert exc.value.code == 0


def test_actual_tree_runner_contract_intact() -> None:
    # Regression guard: every shipped tool keeps the python3 shebang with no
    # PEP 723 block, and every internal runnable script keeps the uv shebang.
    assert find_runner_violations(REPO_ROOT) == []
