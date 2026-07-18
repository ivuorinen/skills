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
    if limit is not None:
        rows = rows[: max(0, int(limit))]
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
            "severity": {"type": "string", "enum": list(findings.SEVERITIES)},
            "category": {"type": "string", "enum": list(findings.CATEGORIES)},
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
    # inputSchema enums are advisory — the server does not validate args against
    # them, so enforce the vocab here (parity with the CLI's argparse choices)
    # before findings.new_finding writes a file that validate_store would reject.
    if args["severity"] not in findings.SEVERITIES:
        raise ValueError(f"severity must be one of {findings.SEVERITIES}, got {args['severity']!r}")
    if args["category"] not in findings.CATEGORIES:
        raise ValueError(f"category must be one of {findings.CATEGORIES}, got {args['category']!r}")
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


def _handle(method: str, params: dict):
    if method == "ping":
        return {}  # MCP liveness check — empty result
    if method == "initialize":
        return {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        }
    if method == "tools/list":
        return {"tools": [{k: t[k] for k in ("name", "description", "inputSchema")} for t in TOOLS]}
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
        if not isinstance(req, dict):
            continue  # ignore batches/scalars — MCP stdio sends one object per line
        rid = req.get("id")
        if rid is None:
            continue  # a notification needs no response
        params = req.get("params")
        if not isinstance(params, dict):
            params = {}  # JSON-RPC allows array/omitted params; our methods want an object
        try:
            result = _handle(req.get("method", ""), params)
            resp = {"jsonrpc": "2.0", "id": rid, "result": result}
        except MethodError as e:
            resp = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": str(e)}}
        except Exception as e:  # noqa: BLE001 — one bad frame must never kill the loop
            resp = {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"},
            }
        stdout.write(json.dumps(resp) + "\n")
        stdout.flush()


def main() -> int:
    serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
