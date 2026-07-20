# Nitpicker MCP Tools Implementation Plan

**Status:** Implemented in 444a84c — the unchecked `- [ ]` boxes below are the
original task list, not outstanding work. Repo-meta tools were dropped during
implementation and are not shipped. This document is a historical record and
has drifted from the shipped surface: the ten tool names were later prefixed
`np_` (`np_list_skills`, `np_new_finding`, …), and registration moved off the
plugin-root `.mcp.json` described below to the `mcpServers` block in
`.claude-plugin/plugin.json` plus `.claude/mcp.json` for project scope.
`skills/nitpicker/SKILL.md` is the authority for the shipped surface.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a stdlib-only stdio MCP server inside the nitpicker plugin that exposes 10 tools for listing/reading the plugin's skills and for reading/managing a project's audit-findings store.

**Architecture:** A hand-rolled JSON-RPC-2.0-over-stdio loop (`mcp_server.py`) wraps two backing modules: the existing `findings.py` (unchanged, called as a library) and a new `skill_catalog.py`. Skill/command tools resolve against the plugin root derived from `__file__`; findings tools resolve against a project root supplied per call (`project_dir` arg → `CLAUDE_PROJECT_DIR` env → `find_repo_root(cwd)` → cwd). The server is registered via a plugin-root `.mcp.json` so `/plugins` installs it automatically.

**Tech Stack:** Python 3.11+ standard library only (`json`, `os`, `sys`, `re`, `argparse`, `pathlib`, `ast` in tests). No `mcp` SDK. pytest for tests (internal tooling, uv-run).

## Global Constraints

- **Stdlib-only shipped tools.** `skills/nitpicker/scripts/skill_catalog.py` and `skills/nitpicker/scripts/mcp_server.py` import only the standard library plus sibling modules in the same `scripts/` dir (`findings`, `skill_catalog`). Enforced by `scripts/check-stdlib-only.py`.
- **Shebang.** Both new shipped files start with exactly `#!/usr/bin/env python3` and carry no `# /// script` block.
- **Python floor:** 3.11+.
- **`findings.py` is not modified** by this plan — it is imported and called.
- **Plugin root** = `Path(__file__).resolve().parents[3]` from a file in `skills/nitpicker/scripts/`.
- **Project root resolution order** (findings tools, per call): `project_dir` arg → `CLAUDE_PROJECT_DIR` env → `findings.find_repo_root(Path.cwd())` → `Path.cwd()`. Store = `<project_root>/docs/audit/findings` (i.e. `<project_root> / findings.DEFAULT_ROOT`).
- **Untrusted input:** tool args are model-controlled. `read_skill`/`read_command` resolve names only by exact match against the enumerated set — never build a path from raw input.
- **Non-interactive mutate contract:** `new_finding`/`resolve_finding` have no consent prompt (D1); git is the safety net. State this in the module docstring.
- **Commits:** conventional commits; `feat:` for the capability (release-please bumps the version — do not hand-edit version files).
- **Tests** live under `tests/`, run with `uv run --quiet pytest`, and load shipped modules via `importlib.util.spec_from_file_location` (matching `tests/test_findings.py`).

---

## File Structure

- **Create** `skills/nitpicker/scripts/skill_catalog.py` — enumerate/read plugin skills; parse the nitpicker Commands table. Module API + CLI.
- **Create** `skills/nitpicker/scripts/mcp_server.py` — JSON-RPC stdio loop, tool registry, 10 handlers.
- **Create** `.mcp.json` (repo/plugin root) — server registration.
- **Create** `tests/test_skill_catalog.py` — unit tests for the catalog module.
- **Create** `tests/test_mcp_server.py` — transport + handler + stdout-cleanliness tests.
- **Modify** `skills/nitpicker/SKILL.md` — add an "MCP server" section.
- **Modify** `README.md` — add a short MCP note/row.

---

## Task 1: `skill_catalog.py` — skill/command listing & reading

**Files:**

- Create: `skills/nitpicker/scripts/skill_catalog.py`
- Test: `tests/test_skill_catalog.py`

**Interfaces:**

- Consumes: `findings.parse_frontmatter(text) -> (dict, str)` (sibling module).
- Produces:
  - `plugin_root() -> Path`
  - `list_skills(root: Path | None = None) -> list[dict]` — each `{"name","description","path","commands"?}`; `commands` present only for the `nitpicker` skill.
  - `read_skill(name: str, root: Path | None = None) -> str` — raises `KeyError` on unknown name.
  - `list_commands(root: Path | None = None) -> list[dict]` — each `{"name","aliases","purpose"}`.
  - `read_command(command: str, root: Path | None = None) -> str` — raises `KeyError` on unknown command.

- [ ] **Step 1: Write the failing test**

Create `tests/test_skill_catalog.py`:

```python
"""Tests for skills/nitpicker/scripts/skill_catalog.py."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "skill_catalog",
    Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "skill_catalog.py",
)
sc = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(sc)  # type: ignore[union-attr]


def test_plugin_root_is_repo_root():
    # skill_catalog.py lives at <root>/skills/nitpicker/scripts/, so parents[3] is <root>.
    assert (sc.plugin_root() / "skills" / "nitpicker" / "SKILL.md").is_file()


def test_list_skills_includes_nitpicker_with_commands():
    skills = sc.list_skills()
    names = {s["name"] for s in skills}
    assert "nitpicker" in names
    nit = next(s for s in skills if s["name"] == "nitpicker")
    assert nit["description"]
    assert "review" in nit["commands"]


def test_read_skill_returns_frontmatter_text():
    text = sc.read_skill("nitpicker")
    assert "name: nitpicker" in text


def test_read_skill_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        sc.read_skill("does-not-exist")


def test_list_commands_parses_name_alias_purpose():
    cmds = sc.list_commands()
    by_name = {c["name"]: c for c in cmds}
    assert "review" in by_name
    assert "adversarial-reviewer" in by_name["review"]["aliases"]
    assert by_name["review"]["purpose"]


def test_read_command_known_and_traversal_rejected():
    import pytest

    assert "# /nitpicker review" in sc.read_command("review")
    with pytest.raises(KeyError):
        sc.read_command("../../../../etc/passwd")
    with pytest.raises(KeyError):
        sc.read_command("_conventions")  # underscore files are not public commands
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --quiet pytest tests/test_skill_catalog.py -v`
Expected: FAIL — `skill_catalog.py` does not exist (import error).

- [ ] **Step 3: Write the implementation**

Create `skills/nitpicker/scripts/skill_catalog.py`:

```python
#!/usr/bin/env python3
"""List and read the plugin's bundled skills and the nitpicker commands.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required.

The plugin root is derived from this file's location
(`<root>/skills/nitpicker/scripts/skill_catalog.py`), so listing works no
matter the process cwd — which matters when the MCP server runs as an
installed plugin whose cwd is unspecified. Names are resolved only against the
enumerated skill/command set, never by building a path from raw input.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from findings import parse_frontmatter  # noqa: E402  (sibling shipped module)

_CMD_ROW = re.compile(r"^\|\s*`([a-z0-9][a-z0-9-]*)`\s*\|\s*(.+?)\s*\|$")
_ALIAS = re.compile(r"alias(?:es)?:\s*([^)]+)")
_CODE = re.compile(r"`([a-z0-9][a-z0-9-]*)`")


def plugin_root() -> Path:
    """Repo/plugin root = the parent of skills/nitpicker/scripts/."""
    return Path(__file__).resolve().parents[3]


def _skill_files(root: Path) -> list[Path]:
    return sorted(root.glob("skills/*/SKILL.md")) + sorted(
        root.glob(".claude/skills/*/SKILL.md")
    )


def _nitpicker_dir(root: Path) -> Path:
    return root / "skills" / "nitpicker"


def list_skills(root: Path | None = None) -> list[dict]:
    root = root or plugin_root()
    out: list[dict] = []
    for path in _skill_files(root):
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        name = fm.get("name", path.parent.name)
        entry = {
            "name": name,
            "description": fm.get("description", ""),
            "path": path.relative_to(root).as_posix(),
        }
        if name == "nitpicker":
            entry["commands"] = [c["name"] for c in list_commands(root=root)]
        out.append(entry)
    return out


def read_skill(name: str, root: Path | None = None) -> str:
    root = root or plugin_root()
    for path in _skill_files(root):
        fm, _ = parse_frontmatter(path.read_text(encoding="utf-8"))
        if fm.get("name", path.parent.name) == name:
            return path.read_text(encoding="utf-8")
    raise KeyError(name)


def list_commands(root: Path | None = None) -> list[dict]:
    """Parse the nitpicker SKILL.md Commands tables → name, aliases, purpose."""
    root = root or plugin_root()
    body = (_nitpicker_dir(root) / "SKILL.md").read_text(encoding="utf-8")
    out: list[dict] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _CMD_ROW.match(line.strip())
        if not m or m.group(1) == "command":
            continue
        name, purpose = m.group(1), m.group(2)
        am = _ALIAS.search(purpose)
        aliases = _CODE.findall(am.group(1)) if am else []
        out.append({"name": name, "aliases": aliases, "purpose": purpose})
    return out


def read_command(command: str, root: Path | None = None) -> str:
    root = root or plugin_root()
    cmd_dir = _nitpicker_dir(root) / "commands"
    valid = {p.stem for p in cmd_dir.glob("*.md") if not p.name.startswith("_")}
    if command not in valid:
        raise KeyError(command)
    return (cmd_dir / f"{command}.md").read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list skills")
    p_rs = sub.add_parser("read", help="print a skill's SKILL.md")
    p_rs.add_argument("name")
    sub.add_parser("commands", help="list nitpicker commands")
    p_rc = sub.add_parser("read-command", help="print a command file")
    p_rc.add_argument("command")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for s in list_skills():
            print(f"{s['name']:20} {s['description'][:70]}")
    elif args.cmd == "read":
        print(read_skill(args.name), end="")
    elif args.cmd == "commands":
        for c in list_commands():
            extra = f"  (aliases: {', '.join(c['aliases'])})" if c["aliases"] else ""
            print(f"{c['name']:20}{extra}")
    elif args.cmd == "read-command":
        print(read_command(args.command), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --quiet pytest tests/test_skill_catalog.py -v`
Expected: PASS (all 6 tests).

- [ ] **Step 5: Verify the stdlib gate and CLI**

Run: `python3 scripts/check-stdlib-only.py`
Expected: no violation for `skill_catalog.py` (its only non-stdlib import root, `findings`, is a sibling).
Run: `python3 skills/nitpicker/scripts/skill_catalog.py list`
Expected: prints a line including `nitpicker`.

- [ ] **Step 6: Commit**

```bash
git add skills/nitpicker/scripts/skill_catalog.py tests/test_skill_catalog.py
git commit -m "feat: add skill_catalog stdlib module for the nitpicker MCP server"
```

---

## Task 2: `mcp_server.py` — JSON-RPC transport core

**Files:**

- Create: `skills/nitpicker/scripts/mcp_server.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**

- Produces:
  - `serve(stdin, stdout) -> None` — reads JSON-RPC request lines from `stdin`, writes response lines to `stdout`.
  - `TOOLS: list[dict]` — registry; each `{"name","description","inputSchema","handler"}`. Grown by later tasks via the `tool(...)` decorator.
  - `tool(name, description, schema)` — decorator registering a handler `fn(args: dict) -> str`.
  - `_text_result(text, is_error=False) -> dict` — MCP tool-result envelope.
- Consumes: nothing yet (handlers arrive in Tasks 3–5).

- [ ] **Step 1: Write the failing test**

Create `tests/test_mcp_server.py`:

```python
"""Tests for skills/nitpicker/scripts/mcp_server.py."""

import contextlib
import importlib.util
import io
import json
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "mcp_server",
        Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "mcp_server.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _rpc(mod, *requests):
    inp = io.StringIO("\n".join(json.dumps(r) for r in requests) + "\n")
    out = io.StringIO()
    mod.serve(inp, out)
    return [json.loads(line) for line in out.getvalue().splitlines() if line]


def test_initialize_handshake():
    mod = _load()
    (resp,) = _rpc(mod, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert resp["id"] == 1
    assert resp["result"]["serverInfo"]["name"] == "nitpicker"
    assert "protocolVersion" in resp["result"]


def test_tools_list_shape():
    mod = _load()
    (resp,) = _rpc(mod, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tools = resp["result"]["tools"]
    assert isinstance(tools, list)
    for t in tools:
        assert set(t) == {"name", "description", "inputSchema"}


def test_unknown_tool_is_error_result():
    mod = _load()
    (resp,) = _rpc(
        mod,
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "nope", "arguments": {}}},
    )
    assert resp["result"]["isError"] is True


def test_notification_gets_no_response():
    mod = _load()
    assert _rpc(mod, {"jsonrpc": "2.0", "method": "notifications/initialized"}) == []


def test_serve_writes_only_frames_to_real_stdout():
    # The load-bearing property: nothing leaks to the process stdout.
    mod = _load()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _rpc(mod, {"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}})
    assert buf.getvalue() == ""
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --quiet pytest tests/test_mcp_server.py -v`
Expected: FAIL — `mcp_server.py` does not exist.

- [ ] **Step 3: Write the implementation**

Create `skills/nitpicker/scripts/mcp_server.py`:

```python
#!/usr/bin/env python3
"""Nitpicker MCP server — stdio JSON-RPC exposing skills + findings tools.

Ships inside the nitpicker skill: stdlib-only, Python 3.11+, no uv required, no
`mcp` SDK. Implements the three methods a tool server needs: `initialize`,
`tools/list`, `tools/call`.

Roots by scope:
  * skill/command tools use the plugin root derived from this file's location;
  * findings tools use a project root resolved per call:
    `project_dir` arg -> CLAUDE_PROJECT_DIR env -> find_repo_root(cwd) -> cwd.

Mutate tools (`new_finding`, `resolve_finding`) are intentionally NON-interactive:
unlike the /nitpicker command flow they run without a consent prompt. Git is the
safety net — every mutation is a reviewable, revertible working-tree change and
nothing is pushed.

stdout carries ONLY JSON-RPC frames; backing functions must never print to it
(they write warnings to stderr). `tests/test_mcp_server.py` pins this.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings  # noqa: E402  (sibling shipped module)
import skill_catalog  # noqa: E402  (sibling shipped module)

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "nitpicker", "version": "1.0.0"}

TOOLS: list[dict] = []


class MethodError(Exception):
    """Raised for an unknown JSON-RPC method (mapped to error code -32601)."""


def tool(name: str, description: str, schema: dict):
    def register(fn):
        TOOLS.append(
            {"name": name, "description": description, "inputSchema": schema, "handler": fn}
        )
        return fn

    return register


def _text_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _handle(method: str, params: dict):
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    if method == "tools/list":
        return {
            "tools": [
                {k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS
            ]
        }
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        for t in TOOLS:
            if t["name"] == name:
                try:
                    return _text_result(t["handler"](args))
                except Exception as e:  # noqa: BLE001 — surface to the model, don't crash
                    return _text_result(f"{type(e).__name__}: {e}", is_error=True)
        return _text_result(f"unknown tool: {name}", is_error=True)
    raise MethodError(f"unknown method: {method}")


def serve(stdin, stdout) -> None:
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = req.get("id")
        if rid is None:
            continue  # a notification needs no response
        try:
            result = _handle(req.get("method"), req.get("params") or {})
            resp = {"jsonrpc": "2.0", "id": rid, "result": result}
        except MethodError as e:
            resp = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": str(e)}}
        stdout.write(json.dumps(resp) + "\n")
        stdout.flush()


def main() -> int:
    serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --quiet pytest tests/test_mcp_server.py -v`
Expected: PASS (5 tests). `test_tools_list_shape` passes trivially over an empty `TOOLS`.

- [ ] **Step 5: Verify the stdlib gate**

Run: `python3 scripts/check-stdlib-only.py`
Expected: no violation (`findings`, `skill_catalog` are siblings).

- [ ] **Step 6: Commit**

```bash
git add skills/nitpicker/scripts/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add nitpicker MCP server JSON-RPC transport core"
```

---

## Task 3: Skills & meta tool handlers

**Files:**

- Modify: `skills/nitpicker/scripts/mcp_server.py` (append 4 handlers)
- Test: `tests/test_mcp_server.py` (add cases)

**Interfaces:**

- Consumes: `skill_catalog.list_skills/read_skill/list_commands/read_command`; `tool(...)`, `_rpc` test helper.
- Produces tools: `list_skills`, `read_skill`, `read_command`, `list_commands`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mcp_server.py`:

```python
def _call(mod, name, arguments):
    (resp,) = _rpc(
        mod,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": name, "arguments": arguments}},
    )
    return resp["result"]


def test_list_skills_tool():
    mod = _load()
    result = _call(mod, "list_skills", {})
    assert result["isError"] is False
    data = json.loads(result["content"][0]["text"])
    assert any(s["name"] == "nitpicker" for s in data)


def test_read_command_tool_and_traversal():
    mod = _load()
    ok = _call(mod, "read_command", {"command": "review"})
    assert ok["isError"] is False and "/nitpicker review" in ok["content"][0]["text"]
    bad = _call(mod, "read_command", {"command": "../../etc/passwd"})
    assert bad["isError"] is True


def test_list_commands_tool_registered():
    mod = _load()
    names = {t["name"] for t in _rpc(
        mod, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    )[0]["result"]["tools"]}
    assert {"list_skills", "read_skill", "read_command", "list_commands"} <= names
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --quiet pytest tests/test_mcp_server.py -k "skills or command" -v`
Expected: FAIL — tools not registered (unknown tool → isError, and the `<=` names assertion fails).

- [ ] **Step 3: Write the implementation**

In `skills/nitpicker/scripts/mcp_server.py`, immediately **after** the `_text_result` definition and **before** `_handle`, add:

```python
# ── skill / command tools (plugin-scoped) ────────────────────────────────────
_NO_ARGS = {"type": "object", "properties": {}, "additionalProperties": False}


@tool("list_skills", "List the plugin's bundled skills (name, description, commands).", _NO_ARGS)
def _list_skills(args: dict) -> str:
    return json.dumps(skill_catalog.list_skills(), indent=2)


@tool(
    "read_skill",
    "Return a bundled skill's SKILL.md text by exact skill name.",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": False,
    },
)
def _read_skill(args: dict) -> str:
    return skill_catalog.read_skill(args["name"])


@tool(
    "read_command",
    "Return a nitpicker command file's text by exact command name.",
    {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
        "additionalProperties": False,
    },
)
def _read_command(args: dict) -> str:
    return skill_catalog.read_command(args["command"])


@tool("list_commands", "List nitpicker commands with aliases and purpose.", _NO_ARGS)
def _list_commands(args: dict) -> str:
    return json.dumps(skill_catalog.list_commands(), indent=2)
```

`read_skill`/`read_command` raise `KeyError` on an unknown or traversal name; `_handle` catches it and returns an `isError` result.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --quiet pytest tests/test_mcp_server.py -v`
Expected: PASS (all, including the new cases).

- [ ] **Step 5: Commit**

```bash
git add skills/nitpicker/scripts/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add skill and command MCP tools to the nitpicker server"
```

---

## Task 4: Findings read tool handlers

**Files:**

- Modify: `skills/nitpicker/scripts/mcp_server.py` (project-root helpers + 4 handlers)
- Test: `tests/test_mcp_server.py` (add cases)

**Interfaces:**

- Consumes: `findings.iter_open(store)`, `findings.read_ledger(store)`, `findings.show_finding(store, id)`, `findings.build_index(store)`, `findings.validate_store(store)`, `findings.find_repo_root`, `findings.DEFAULT_ROOT`, `findings.new_finding` (used by tests to seed).
- Produces tools: `list_findings`, `show_finding`, `findings_index`, `validate_store`; helpers `_project_root(args)`, `_store(args)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mcp_server.py`:

```python
def _load_findings():
    spec = importlib.util.spec_from_file_location(
        "findings",
        Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "findings.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _seed(tmp_path):
    f = _load_findings()
    store = tmp_path / "docs" / "audit" / "findings"
    f.new_finding(
        store, auditor="review", severity="high", category="correctness",
        area="src/a.py", title="Boom", body="## Problem\nx\n## Evidence\ny\n## Impact\nz\n## Fix\nw\n",
    )
    return store


def test_list_findings_open_and_filter(tmp_path):
    _seed(tmp_path)
    mod = _load()
    result = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "open"})
    rows = json.loads(result["content"][0]["text"])
    assert len(rows) == 1 and rows[0]["auditor"] == "review"
    # A non-matching auditor filter yields nothing.
    empty = _call(mod, "list_findings", {"project_dir": str(tmp_path), "auditor": "security"})
    assert json.loads(empty["content"][0]["text"]) == []


def test_findings_index_and_validate(tmp_path):
    _seed(tmp_path)
    mod = _load()
    idx = _call(mod, "findings_index", {"project_dir": str(tmp_path)})
    assert "Audit Findings Index" in idx["content"][0]["text"]
    val = _call(mod, "validate_store", {"project_dir": str(tmp_path)})
    assert val["isError"] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --quiet pytest tests/test_mcp_server.py -k findings -v`
Expected: FAIL — `list_findings`/`findings_index`/`validate_store` not registered (unknown tool → isError).

- [ ] **Step 3: Write the implementation**

In `skills/nitpicker/scripts/mcp_server.py`, add project-root helpers **after** the skill tools and **before** `_handle`:

```python
# ── project-root resolution (findings tools) ─────────────────────────────────
def _project_root(args: dict) -> Path:
    pd = args.get("project_dir")
    if pd:
        return Path(pd)
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return findings.find_repo_root(Path.cwd()) or Path.cwd()


def _store(args: dict) -> Path:
    return _project_root(args) / findings.DEFAULT_ROOT


_PROJECT_DIR_PROP = {"project_dir": {"type": "string"}}


# ── findings read tools (project-scoped) ─────────────────────────────────────
@tool(
    "list_findings",
    "List findings (open files + resolved ledger), filtered and capped.",
    {
        "type": "object",
        "properties": {
            **_PROJECT_DIR_PROP,
            "auditor": {"type": "string"},
            "severity": {"type": "string"},
            "status": {"type": "string", "enum": ["open", "fixed", "invalid"]},
            "limit": {"type": "integer"},
        },
        "additionalProperties": False,
    },
)
def _list_findings(args: dict) -> str:
    store = _store(args)
    status = args.get("status")
    rows: list[dict] = []
    if status in (None, "open"):
        for path, fm, title in findings.iter_open(store):
            rows.append(
                {
                    "id": fm.get("id", path.stem),
                    "status": "open",
                    "auditor": fm.get("auditor", ""),
                    "severity": fm.get("severity", ""),
                    "area": fm.get("area", ""),
                    "title": title,
                }
            )
    if status in (None, "fixed", "invalid"):
        for rec in findings.read_ledger(store):
            if status and rec.get("status") != status:
                continue
            rows.append(
                {
                    "id": rec.get("id", ""),
                    "status": rec.get("status", ""),
                    "auditor": rec.get("auditor", ""),
                    "severity": rec.get("severity", ""),
                    "area": rec.get("area", ""),
                    "title": rec.get("title", ""),
                }
            )
    if args.get("auditor"):
        rows = [r for r in rows if r["auditor"] == args["auditor"]]
    if args.get("severity"):
        rows = [r for r in rows if r["severity"] == args["severity"]]
    limit = args.get("limit")
    if limit:
        rows = rows[: int(limit)]
    return json.dumps(rows, indent=2)


@tool(
    "show_finding",
    "Print one finding (open file or resolved ledger record) by id.",
    {
        "type": "object",
        "properties": {**_PROJECT_DIR_PROP, "id": {"type": "string"}},
        "required": ["id"],
        "additionalProperties": False,
    },
)
def _show_finding(args: dict) -> str:
    return findings.show_finding(_store(args), args["id"])


@tool(
    "findings_index",
    "Return the generated findings INDEX.md content.",
    {"type": "object", "properties": {**_PROJECT_DIR_PROP}, "additionalProperties": False},
)
def _findings_index(args: dict) -> str:
    return findings.build_index(_store(args))


@tool(
    "validate_store",
    "Structurally validate the findings store; returns 'OK' or the errors.",
    {"type": "object", "properties": {**_PROJECT_DIR_PROP}, "additionalProperties": False},
)
def _validate_store(args: dict) -> str:
    errors = findings.validate_store(_store(args))
    return "OK  findings store consistent." if not errors else "\n".join(errors)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --quiet pytest tests/test_mcp_server.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add skills/nitpicker/scripts/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add findings read MCP tools to the nitpicker server"
```

---

## Task 5: Findings mutate tool handlers

**Files:**

- Modify: `skills/nitpicker/scripts/mcp_server.py` (2 handlers + body assembly)
- Test: `tests/test_mcp_server.py` (round-trip + stdout cleanliness on mutate)

**Interfaces:**

- Consumes: `findings.new_finding`, `findings.resolve_finding`, `findings.write_index`; `_store`, `tool`.
- Produces tools: `new_finding`, `resolve_finding`; helper `_assemble_body(args)`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mcp_server.py`:

```python
def test_mutate_round_trip_and_stdout_clean(tmp_path):
    mod = _load()
    # new_finding
    created = _call(
        mod, "new_finding",
        {
            "project_dir": str(tmp_path), "auditor": "review", "severity": "high",
            "category": "correctness", "area": "src/x.py", "title": "Kaboom",
            "problem": "p", "evidence": "e", "impact": "i", "fix": "f",
        },
    )
    fid = json.loads(created["content"][0]["text"])["id"]

    # it shows up as open
    listed = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "open"})
    assert any(r["id"] == fid for r in json.loads(listed["content"][0]["text"]))

    # resolving it must not leak to real stdout (writes files + refreshes index)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        resolved = _call(
            mod, "resolve_finding",
            {"project_dir": str(tmp_path), "id": fid, "status": "fixed", "note": "done"},
        )
    assert buf.getvalue() == ""
    assert resolved["isError"] is False

    # now it's resolved, not open
    after = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "open"})
    assert json.loads(after["content"][0]["text"]) == []
    ledger = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "fixed"})
    assert any(r["id"] == fid for r in json.loads(ledger["content"][0]["text"]))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --quiet pytest tests/test_mcp_server.py -k mutate -v`
Expected: FAIL — `new_finding`/`resolve_finding` not registered.

- [ ] **Step 3: Write the implementation**

In `skills/nitpicker/scripts/mcp_server.py`, add after the findings read tools and before `_handle`:

```python
# ── findings mutate tools (project-scoped, non-interactive; git is the net) ───
def _assemble_body(args: dict) -> str:
    return (
        f"## Problem\n{args.get('problem', '')}\n\n"
        f"## Evidence\n{args.get('evidence', '')}\n\n"
        f"## Impact\n{args.get('impact', '')}\n\n"
        f"## Fix\n{args.get('fix', '')}\n"
    )


@tool(
    "new_finding",
    "Create an open finding. Body is assembled from problem/evidence/impact/fix.",
    {
        "type": "object",
        "properties": {
            **_PROJECT_DIR_PROP,
            "auditor": {"type": "string"},
            "severity": {"type": "string"},
            "category": {"type": "string"},
            "area": {"type": "string"},
            "title": {"type": "string"},
            "problem": {"type": "string"},
            "evidence": {"type": "string"},
            "impact": {"type": "string"},
            "fix": {"type": "string"},
        },
        "required": ["auditor", "severity", "category", "area", "title"],
        "additionalProperties": False,
    },
)
def _new_finding(args: dict) -> str:
    store = _store(args)
    path = findings.new_finding(
        store,
        auditor=args["auditor"],
        severity=args["severity"],
        category=args["category"],
        area=args["area"],
        title=args["title"],
        body=_assemble_body(args),
    )
    findings.write_index(store)
    return json.dumps({"id": path.stem, "path": str(path)})


@tool(
    "resolve_finding",
    "Resolve a finding (status fixed|invalid): appends the ledger, deletes the open file.",
    {
        "type": "object",
        "properties": {
            **_PROJECT_DIR_PROP,
            "id": {"type": "string"},
            "status": {"type": "string", "enum": ["fixed", "invalid"]},
            "note": {"type": "string"},
        },
        "required": ["id", "status"],
        "additionalProperties": False,
    },
)
def _resolve_finding(args: dict) -> str:
    store = _store(args)
    findings.resolve_finding(store, args["id"], args["status"], args.get("note", ""))
    findings.write_index(store)
    return json.dumps({"id": args["id"], "status": args["status"]})
```

- [ ] **Step 4: Run the full server test suite**

Run: `uv run --quiet pytest tests/test_mcp_server.py -v`
Expected: PASS (all, including the round-trip and its stdout-cleanliness assertion).

- [ ] **Step 5: Confirm all 10 tools are registered**

Run: `python3 -c "import importlib.util,pathlib; s=importlib.util.spec_from_file_location('m', pathlib.Path('skills/nitpicker/scripts/mcp_server.py')); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(sorted(t['name'] for t in m.TOOLS))"`
Expected: `['findings_index', 'list_commands', 'list_findings', 'list_skills', 'new_finding', 'read_command', 'read_skill', 'resolve_finding', 'show_finding', 'validate_store']`

- [ ] **Step 6: Commit**

```bash
git add skills/nitpicker/scripts/mcp_server.py tests/test_mcp_server.py
git commit -m "feat: add findings mutate MCP tools to the nitpicker server"
```

---

## Task 6: Registration + docs

**Files:**

- Create: `.mcp.json` (repo/plugin root)
- Modify: `skills/nitpicker/SKILL.md`
- Modify: `README.md`

**Interfaces:** none (config + prose).

- [ ] **Step 1: Create `.mcp.json` at the repo root**

```json
{
  "mcpServers": {
    "nitpicker": {
      "type": "stdio",
      "command": "python3",
      "args": ["${CLAUDE_PLUGIN_ROOT}/skills/nitpicker/scripts/mcp_server.py"],
      "env": {
        "CLAUDE_PROJECT_DIR": "${CLAUDE_PROJECT_DIR}"
      }
    }
  }
}
```

- [ ] **Step 2: Verify JSON validity**

Run: `python3 -c "import json; json.load(open('.mcp.json'))"`
Expected: no output, exit 0.

- [ ] **Step 3: Empirically verify the two Claude Code unknowns**

Install the plugin from the local marketplace (`/plugins`), then in a *different* project ask the agent to call `list_skills` and `list_findings`.

- If `${CLAUDE_PLUGIN_ROOT}` does **not** interpolate in `args`, the server won't launch — replace the arg with the relative path `./skills/nitpicker/scripts/mcp_server.py` and re-test.
- `list_findings` correctness must **not** depend on `${CLAUDE_PROJECT_DIR}` interpolating in `env`: confirm it still resolves the right store when the agent passes `project_dir` explicitly. Record both outcomes in the PR description.

(These are runtime checks against Claude Code behaviour, not pytest — the docs don't specify either. Correctness is covered by the `project_dir` arg regardless.)

- [ ] **Step 4: Add the MCP section to `skills/nitpicker/SKILL.md`**

Add a `## MCP server` section (place it after the `## Dispatch` section) with this content:

```markdown
## MCP server

Installing this plugin also registers a stdio MCP server (`nitpicker`) via the
plugin-root `.mcp.json`. It exposes 10 tools: `list_skills`, `read_skill`,
`read_command`, `list_commands` (plugin-scoped introspection); and
`list_findings`, `show_finding`, `findings_index`, `validate_store`,
`new_finding`, `resolve_finding` (scoped to the audited project — pass
`project_dir`, or rely on `CLAUDE_PROJECT_DIR`/cwd).

The mutate tools (`new_finding`, `resolve_finding`) run **without** the
interactive consent prompts of the `/nitpicker` command flow; git is the safety
net (every change is reviewable and revertible, nothing is pushed). The server
is stdlib-only Python 3.11+ and is not portable to Copilot/pi.
```

- [ ] **Step 5: Add a README note**

In `README.md`, under the section that describes the skill's tooling, add:

```markdown
### MCP server

Installing the plugin registers a stdlib-only stdio MCP server exposing skill
introspection (`list_skills`, `read_skill`, `read_command`, `list_commands`) and
findings management (`list_findings`, `show_finding`, `findings_index`,
`validate_store`, `new_finding`, `resolve_finding`). See the "MCP server"
section of `skills/nitpicker/SKILL.md`.
```

- [ ] **Step 6: Run the full gate**

Run: `make check`
Expected: PASS — validators, stdlib gate, ruff, pytest, JSON validation all green.

- [ ] **Step 7: Commit**

```bash
git add .mcp.json skills/nitpicker/SKILL.md README.md
git commit -m "feat: register nitpicker MCP server and document its tools"
```

---

## Self-Review

**Spec coverage:**

- Placement/form (stdlib JSON-RPC under `skills/nitpicker/scripts/`) → Task 2.
- `skill_catalog.py` new module (enumerate, frontmatter, command table, name validation) → Task 1.
- 10-tool surface → Tasks 3 (4 skill/meta), 4 (4 findings read), 5 (2 mutate).
- Root resolution (plugin via `__file__`; project via `project_dir`→env→cwd, per call) → Tasks 1 (`plugin_root`) + 4 (`_project_root`).
- Registration (plugin `.mcp.json`, `${CLAUDE_PLUGIN_ROOT}`, env, unknowns) → Task 6.
- Security (no path from raw input; import isolation) → Task 1 (`read_command`/`read_skill` validate against enumerated set; `sys.path.insert`), Task 3 (traversal test).
- H1 body assembly → Task 5. M1 merge/filter → Task 4. M3 stdout-cleanliness test → Tasks 2 + 5. C1 traversal test → Tasks 1 + 3. L1 limit → Task 4.
- D1 non-interactive mutate contract documented → module docstring (Task 2) + SKILL.md (Task 6).
- Docs (SKILL.md section, README, docstring) → Tasks 2 + 6.
- Validation gates (`make check`) → Task 6.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; every command has expected output.

**Type consistency:** `_store(args)`/`_project_root(args)` defined in Task 4 and reused in Task 5. `tool(...)`, `_text_result`, `serve`, `TOOLS`, `_rpc`, `_call`, `_load` defined once and reused. `findings.new_finding` keyword args match `findings.py:535` (`auditor, severity, category, area, title, body`). `findings.resolve_finding` positional args match `findings.py:584` (`root, fid, status, notes`). `findings.DEFAULT_ROOT` / `find_repo_root` / `iter_open` / `read_ledger` / `build_index` / `validate_store` / `show_finding` / `write_index` / `parse_frontmatter` all exist in `findings.py`.

**Deferred (not in scope, per spec):** `fetch-pr-comments`/`process-sarif` wrappers; `baseline`/`migrate`/`migrate-resolved` tools.
