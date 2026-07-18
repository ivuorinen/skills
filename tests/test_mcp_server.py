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


def _call(mod, name, arguments):
    (resp,) = _rpc(
        mod,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )
    return resp["result"]


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
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "nope", "arguments": {}},
        },
    )
    assert resp["result"]["isError"] is True


def test_notification_gets_no_response():
    mod = _load()
    assert _rpc(mod, {"jsonrpc": "2.0", "method": "notifications/initialized"}) == []


def test_non_dict_frame_is_ignored_not_fatal():
    # A batch (list) or scalar frame must not crash the serve loop; the
    # following valid request still gets answered.
    mod = _load()
    inp = io.StringIO('[1, 2, 3]\n42\n{"jsonrpc": "2.0", "id": 7, "method": "initialize"}\n')
    out = io.StringIO()
    mod.serve(inp, out)
    responses = [json.loads(line) for line in out.getvalue().splitlines() if line]
    assert len(responses) == 1 and responses[0]["id"] == 7


def test_non_dict_params_does_not_kill_loop():
    # A frame with array/string params is legal JSON-RPC; it must not crash the
    # serve loop and the following valid request must still be answered.
    mod = _load()
    inp = io.StringIO(
        '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": [1, 2]}\n'
        '{"jsonrpc": "2.0", "id": 3, "method": "tools/list"}\n'
    )
    out = io.StringIO()
    mod.serve(inp, out)
    responses = {json.loads(line)["id"]: json.loads(line) for line in out.getvalue().splitlines()}
    assert set(responses) == {2, 3}
    assert "result" in responses[3]  # the valid request after the bad one still answered


def test_ping_returns_empty_result():
    mod = _load()
    (resp,) = _rpc(mod, {"jsonrpc": "2.0", "id": 5, "method": "ping"})
    assert resp["result"] == {}


def test_new_finding_rejects_bad_severity(tmp_path):
    mod = _load()
    result = _call(
        mod,
        "new_finding",
        {
            "project_dir": str(tmp_path),
            "auditor": "review",
            "severity": "banana",
            "category": "correctness",
            "area": "src/x.py",
            "title": "Bad",
        },
    )
    assert result["isError"] is True
    # nothing was written — the store stays clean
    listed = _call(mod, "list_findings", {"project_dir": str(tmp_path)})
    assert json.loads(listed["content"][0]["text"]) == []


def test_list_findings_limit_zero_returns_none(tmp_path):
    _seed(tmp_path)
    mod = _load()
    result = _call(mod, "list_findings", {"project_dir": str(tmp_path), "limit": 0})
    assert json.loads(result["content"][0]["text"]) == []


def test_serve_writes_only_frames_to_real_stdout():
    # The load-bearing property: nothing leaks to the process stdout.
    mod = _load()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _rpc(mod, {"jsonrpc": "2.0", "id": 9, "method": "tools/list", "params": {}})
    assert buf.getvalue() == ""


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


def test_skill_meta_tools_registered():
    mod = _load()
    names = {
        t["name"]
        for t in _rpc(mod, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})[0][
            "result"
        ]["tools"]
    }
    assert {"list_skills", "read_skill", "read_command", "list_commands"} <= names


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
        store,
        auditor="review",
        severity="high",
        category="correctness",
        area="src/a.py",
        title="Boom",
        body="## Problem\nx\n## Evidence\ny\n## Impact\nz\n## Fix\nw\n",
    )
    return store


def test_list_findings_open_and_filter(tmp_path):
    _seed(tmp_path)
    mod = _load()
    result = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "open"})
    rows = json.loads(result["content"][0]["text"])
    assert len(rows) == 1 and rows[0]["auditor"] == "review"
    empty = _call(mod, "list_findings", {"project_dir": str(tmp_path), "auditor": "security"})
    assert json.loads(empty["content"][0]["text"]) == []


def test_findings_index_and_validate(tmp_path):
    _seed(tmp_path)
    mod = _load()
    idx = _call(mod, "findings_index", {"project_dir": str(tmp_path)})
    assert "Audit Findings Index" in idx["content"][0]["text"]
    val = _call(mod, "validate_store", {"project_dir": str(tmp_path)})
    assert val["isError"] is False


def test_mutate_round_trip_and_stdout_clean(tmp_path):
    mod = _load()
    created = _call(
        mod,
        "new_finding",
        {
            "project_dir": str(tmp_path),
            "auditor": "review",
            "severity": "high",
            "category": "correctness",
            "area": "src/x.py",
            "title": "Kaboom",
            "problem": "p",
            "evidence": "e",
            "impact": "i",
            "fix": "f",
        },
    )
    fid = json.loads(created["content"][0]["text"])["id"]

    listed = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "open"})
    assert any(r["id"] == fid for r in json.loads(listed["content"][0]["text"]))

    # resolving must not leak to real stdout (writes files + refreshes index)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        resolved = _call(
            mod,
            "resolve_finding",
            {"project_dir": str(tmp_path), "id": fid, "status": "fixed", "note": "done"},
        )
    assert buf.getvalue() == ""
    assert resolved["isError"] is False

    after = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "open"})
    assert json.loads(after["content"][0]["text"]) == []
    ledger = _call(mod, "list_findings", {"project_dir": str(tmp_path), "status": "fixed"})
    assert any(r["id"] == fid for r in json.loads(ledger["content"][0]["text"]))
