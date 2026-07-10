"""Tests for scripts/check-stdlib-only.py."""

import importlib.util
from pathlib import Path

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


def test_first_party_sibling_allowed(tmp_path: Path) -> None:
    _tool(tmp_path, "common.py", "X = 1\n")
    _tool(tmp_path, "uses_sibling.py", "import common\n")
    assert find_violations(tmp_path) == []


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


def test_actual_tree_runner_contract_intact() -> None:
    # Regression guard: every shipped tool keeps the python3 shebang with no
    # PEP 723 block, and every internal runnable script keeps the uv shebang.
    assert find_runner_violations(REPO_ROOT) == []
