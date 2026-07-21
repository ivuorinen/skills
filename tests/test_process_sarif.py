"""Tests for skills/nitpicker/scripts/process-sarif.py."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts" / "process-sarif.py"
_spec = importlib.util.spec_from_file_location("process_sarif", _TOOL)
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

_normalize_severity = _mod._normalize_severity
_extract_rules = _mod._extract_rules
_extract_findings = _mod._extract_findings
_parse_sarif = _mod._parse_sarif
_deduplicate = _mod._deduplicate


def _sarif(runs: list) -> dict:
    return {"version": "2.1.0", "$schema": "...", "runs": runs}


def _run(
    tool_name: str = "test-tool", rules: list | None = None, results: list | None = None
) -> dict:
    return {
        "tool": {"driver": {"name": tool_name, "rules": rules or []}},
        "results": results or [],
    }


def _result(
    rule_id: str = "rule-001",
    level: str = "warning",
    message: str = "A finding",
    uri: str = "src/foo.py",
    start_line: int = 42,
    properties: dict | None = None,
) -> dict:
    return {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {"uri": uri},
                    "region": {"startLine": start_line, "startColumn": 1},
                }
            }
        ],
        **({"properties": properties} if properties else {}),
    }


# ── _normalize_severity ────────────────────────────────────────────────────────


class TestNormalizeSeverity:
    def test_tool_severity_critical(self):
        assert _normalize_severity(None, None, "CRITICAL") == "Critical"

    def test_tool_severity_high(self):
        assert _normalize_severity(None, None, "HIGH") == "High"

    def test_tool_severity_error(self):
        assert _normalize_severity(None, None, "ERROR") == "High"

    def test_tool_severity_medium(self):
        assert _normalize_severity(None, None, "MEDIUM") == "Medium"

    def test_tool_severity_moderate(self):
        assert _normalize_severity(None, None, "MODERATE") == "Medium"

    def test_tool_severity_warning(self):
        assert _normalize_severity(None, None, "WARNING") == "Medium"

    def test_tool_severity_low(self):
        assert _normalize_severity(None, None, "LOW") == "Low"

    def test_tool_severity_info(self):
        assert _normalize_severity(None, None, "INFO") == "Low"

    def test_tool_severity_advisory(self):
        assert _normalize_severity(None, None, "ADVISORY") == "Advisory"

    def test_tool_severity_hint(self):
        assert _normalize_severity(None, None, "HINT") == "Advisory"

    def test_cvss_critical(self):
        assert _normalize_severity(None, "9.5", None) == "Critical"

    def test_cvss_high(self):
        assert _normalize_severity(None, "7.0", None) == "High"

    def test_cvss_medium(self):
        assert _normalize_severity(None, "5.0", None) == "Medium"

    def test_cvss_low(self):
        assert _normalize_severity(None, "2.0", None) == "Low"

    def test_cvss_zero_maps_to_low(self):
        # score == 0.0 → explicit CVSS score, maps to Low (not SARIF level)
        assert _normalize_severity("error", "0.0", None) == "Low"

    def test_cvss_invalid_string_falls_through(self):
        assert _normalize_severity("warning", "not-a-number", None) == "Medium"

    def test_sarif_level_error(self):
        assert _normalize_severity("error", None, None) == "High"

    def test_sarif_level_warning(self):
        assert _normalize_severity("warning", None, None) == "Medium"

    def test_sarif_level_note(self):
        assert _normalize_severity("note", None, None) == "Low"

    def test_sarif_level_none_string(self):
        assert _normalize_severity("none", None, None) == "Low"

    def test_all_none_defaults_to_low(self):
        assert _normalize_severity(None, None, None) == "Low"

    def test_unknown_tool_severity_falls_through_to_cvss(self):
        assert _normalize_severity(None, "8.0", "UNKNOWN_SEVERITY") == "High"


# ── _extract_rules ─────────────────────────────────────────────────────────────


class TestExtractRules:
    def test_empty_run(self):
        rules = _extract_rules({"tool": {"driver": {"name": "t", "rules": []}}})
        assert rules == {}

    def test_rules_from_driver(self):
        run = _run("semgrep", rules=[{"id": "r1", "name": "Rule1", "helpUri": "http://x"}])
        rules = _extract_rules(run)
        assert "r1" in rules
        assert rules["r1"]["name"] == "Rule1"
        assert rules["r1"]["help_uri"] == "http://x"

    def test_rules_from_extensions(self):
        run = {
            "tool": {
                "driver": {"name": "t", "rules": []},
                "extensions": [{"rules": [{"id": "ext-r1", "name": "ExtRule"}]}],
            },
            "results": [],
        }
        rules = _extract_rules(run)
        assert "ext-r1" in rules

    def test_security_severity_in_properties(self):
        run = _run("t", rules=[{"id": "r1", "properties": {"security-severity": "8.5"}}])
        rules = _extract_rules(run)
        assert rules["r1"]["security_severity"] == "8.5"

    def test_short_description_extracted(self):
        run = _run("t", rules=[{"id": "r1", "shortDescription": {"text": "Short desc"}}])
        rules = _extract_rules(run)
        assert rules["r1"]["short_description"] == "Short desc"


# ── _extract_findings ──────────────────────────────────────────────────────────


class TestExtractFindings:
    def test_basic_finding(self):
        run = _run("semgrep", results=[_result("r1", "warning", "Found issue", "src/a.py", 10)])
        findings = _extract_findings(run, "scan.sarif")
        assert len(findings) == 1
        f = findings[0]
        assert f["rule_id"] == "r1"
        assert f["uri"] == "src/a.py"
        assert f["start_line"] == 10
        assert f["severity"] == "Medium"
        assert f["source_file"] == "scan.sarif"

    def test_finding_without_location(self):
        result = {
            "ruleId": "cve-001",
            "level": "error",
            "message": {"text": "Vuln"},
            "locations": [],
        }
        run = _run("grype", results=[result])
        findings = _extract_findings(run, "grype.sarif")
        assert findings[0]["uri"] == ""
        assert findings[0]["start_line"] == 0

    def test_string_message(self):
        result = {"ruleId": "r1", "level": "warning", "message": "plain string", "locations": []}
        run = _run("t", results=[result])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["message"] == "plain string"

    def test_cve_from_taxa(self):
        result = {
            "ruleId": "r1",
            "level": "error",
            "message": {"text": "Vulnerable package"},
            "locations": [],
            "taxa": [{"id": "CVE-2024-1234"}, {"id": "CWE-78"}],
        }
        run = _run("grype", results=[result])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["cve_or_rule"] == "CVE-2024-1234"

    def test_non_cve_taxa_uses_rule_id(self):
        result = {
            "ruleId": "r1",
            "level": "warning",
            "message": {"text": "x"},
            "locations": [],
            "taxa": [{"id": "CWE-78"}],
        }
        run = _run("t", results=[result])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["cve_or_rule"] == "r1"

    def test_tool_severity_from_properties(self):
        result = _result("r1", "note", properties={"severity": "HIGH"})
        run = _run("t", results=[result])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["severity"] == "High"

    def test_fingerprint_uses_message_when_no_uri(self):
        r1 = {
            "ruleId": "CVE-001",
            "level": "error",
            "message": {"text": "pkg-a@1.0"},
            "locations": [],
        }
        r2 = {
            "ruleId": "CVE-001",
            "level": "error",
            "message": {"text": "pkg-b@2.0"},
            "locations": [],
        }
        run = _run("grype", results=[r1, r2])
        findings = _extract_findings(run, "x.sarif")
        # Different messages → different fingerprints → no dedup
        assert findings[0]["fingerprint"] != findings[1]["fingerprint"]

    def test_fingerprint_same_tool_rule_location(self):
        r = _result("r1", "warning", "msg", "src/a.py", 5)
        run = _run("semgrep", results=[r, r])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["fingerprint"] == findings[1]["fingerprint"]

    def test_fingerprint_different_column_different_key(self):
        def _loc(col):
            return [
                {
                    "physicalLocation": {
                        "artifactLocation": {"uri": "f.py"},
                        "region": {"startLine": 5, "startColumn": col},
                    }
                }
            ]

        r1 = {"ruleId": "r1", "level": "warning", "message": {"text": "x"}, "locations": _loc(1)}
        r2 = {"ruleId": "r1", "level": "warning", "message": {"text": "x"}, "locations": _loc(10)}
        run = _run("semgrep", results=[r1, r2])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["fingerprint"] != findings[1]["fingerprint"]

    def test_empty_results(self):
        run = _run("semgrep", results=[])
        findings = _extract_findings(run, "x.sarif")
        assert findings == []

    def test_null_taxa_and_locations_no_crash(self):
        result = {
            "ruleId": "r1",
            "level": "error",
            "message": {"text": "x"},
            "locations": None,
            "taxa": None,
        }
        run = _run("t", results=[result])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["cve_or_rule"] == "r1"
        assert findings[0]["start_line"] == 0

    def test_string_start_line_coerced_to_int(self):
        r = _result()
        r["locations"][0]["physicalLocation"]["region"]["startLine"] = "12"
        r["locations"][0]["physicalLocation"]["region"]["startColumn"] = "junk"
        run = _run("t", results=[r])
        findings = _extract_findings(run, "x.sarif")
        assert findings[0]["start_line"] == 12
        assert findings[0]["start_column"] == 0

    def test_string_and_int_start_lines_sort_together(self, tmp_path, capsys, monkeypatch):
        r1 = _result("r1", "warning", "a", "f.py", 5)
        r2 = _result("r2", "warning", "b", "f.py", 3)
        r2["locations"][0]["physicalLocation"]["region"]["startLine"] = "3"
        f = tmp_path / "mixed.sarif"
        f.write_text(json.dumps(_sarif([_run("t", results=[r1, r2])])), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        _mod.main()
        data = json.loads(capsys.readouterr().out)
        assert [x["start_line"] for x in data["findings"]] == [3, 5]


# ── _parse_sarif ───────────────────────────────────────────────────────────────


class TestParseSarif:
    def test_valid_sarif_file(self, tmp_path):
        data = _sarif([_run("semgrep", results=[_result()])])
        f = tmp_path / "scan.sarif"
        f.write_text(json.dumps(data), encoding="utf-8")
        findings = _parse_sarif(f)
        assert len(findings) == 1

    def test_invalid_json_exits_1(self, tmp_path):
        f = tmp_path / "bad.sarif"
        f.write_text("not json", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            _parse_sarif(f)
        assert exc.value.code == 1

    def test_wrong_version_warns(self, tmp_path, capsys):
        data = {"version": "1.0.0", "runs": []}
        f = tmp_path / "old.sarif"
        f.write_text(json.dumps(data), encoding="utf-8")
        _parse_sarif(f)
        assert "not fully supported" in capsys.readouterr().err

    def test_top_level_array_exits_1(self, tmp_path, capsys):
        f = tmp_path / "arr.sarif"
        f.write_text("[]", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            _parse_sarif(f)
        assert exc.value.code == 1
        assert "[error]" in capsys.readouterr().err

    def test_null_runs_returns_empty(self, tmp_path):
        f = tmp_path / "null-runs.sarif"
        f.write_text(json.dumps({"version": "2.1.0", "runs": None}), encoding="utf-8")
        assert _parse_sarif(f) == []

    def test_multiple_runs(self, tmp_path):
        data = _sarif(
            [
                _run("tool-a", results=[_result("r1")]),
                _run("tool-b", results=[_result("r2")]),
            ]
        )
        f = tmp_path / "multi.sarif"
        f.write_text(json.dumps(data), encoding="utf-8")
        findings = _parse_sarif(f)
        assert len(findings) == 2

    def test_empty_runs(self, tmp_path):
        f = tmp_path / "empty.sarif"
        f.write_text(json.dumps(_sarif([])), encoding="utf-8")
        assert _parse_sarif(f) == []


# ── _deduplicate ───────────────────────────────────────────────────────────────


class TestDeduplicate:
    def test_no_duplicates(self):
        findings = [
            {"fingerprint": "aaa", "data": 1},
            {"fingerprint": "bbb", "data": 2},
        ]
        unique, removed = _deduplicate(findings)
        assert len(unique) == 2
        assert removed == 0

    def test_with_duplicates(self):
        findings = [
            {"fingerprint": "aaa", "data": 1},
            {"fingerprint": "aaa", "data": 1},
            {"fingerprint": "bbb", "data": 2},
        ]
        unique, removed = _deduplicate(findings)
        assert len(unique) == 2
        assert removed == 1

    def test_all_duplicates(self):
        findings = [{"fingerprint": "x"}, {"fingerprint": "x"}, {"fingerprint": "x"}]
        unique, removed = _deduplicate(findings)
        assert len(unique) == 1
        assert removed == 2

    def test_empty_list(self):
        unique, removed = _deduplicate([])
        assert unique == []
        assert removed == 0

    def test_location_less_distinct_messages_not_deduped(self):
        findings = [
            {"fingerprint": "aa", "rule_id": "CVE-001", "uri": "", "message": "pkg-a"},
            {"fingerprint": "bb", "rule_id": "CVE-001", "uri": "", "message": "pkg-b"},
        ]
        unique, removed = _deduplicate(findings)
        assert len(unique) == 2
        assert removed == 0


# ── main ──────────────────────────────────────────────────────────────────────


class TestMain:
    def _write_sarif(self, path: Path, runs: list | None = None) -> None:
        path.write_text(json.dumps(_sarif(runs or [])), encoding="utf-8")

    def test_no_args_exits_2(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog"])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 2

    def test_file_not_found_exits_1(self, tmp_path, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["prog", str(tmp_path / "missing.sarif")])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1

    def test_valid_sarif_outputs_json(self, tmp_path, capsys, monkeypatch):
        f = tmp_path / "scan.sarif"
        self._write_sarif(f, [_run("semgrep", results=[_result()])])
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        _mod.main()
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert "meta" in data
        assert "by_severity" in data
        assert "by_tool" in data
        assert "findings" in data

    def test_output_severity_counts(self, tmp_path, capsys, monkeypatch):
        f = tmp_path / "scan.sarif"
        self._write_sarif(
            f,
            [
                _run(
                    "t",
                    results=[
                        _result("r1", "error"),
                        _result("r2", "warning"),
                    ],
                )
            ],
        )
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        _mod.main()
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["meta"]["total_raw"] == 2
        assert data["meta"]["severity_counts"]["High"] == 1
        assert data["meta"]["severity_counts"]["Medium"] == 1

    def test_deduplication_in_output(self, tmp_path, capsys, monkeypatch):
        r = _result("r1", "warning", "msg", "f.py", 5)
        f = tmp_path / "scan.sarif"
        self._write_sarif(f, [_run("t", results=[r, r])])
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        _mod.main()
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["meta"]["total_raw"] == 2
        assert data["meta"]["unique"] == 1
        assert data["meta"]["duplicates_removed"] == 1

    def test_multiple_files(self, tmp_path, capsys, monkeypatch):
        f1 = tmp_path / "a.sarif"
        f2 = tmp_path / "b.sarif"
        self._write_sarif(f1, [_run("tool-a", results=[_result("r1")])])
        self._write_sarif(f2, [_run("tool-b", results=[_result("r2")])])
        monkeypatch.setattr(sys, "argv", ["prog", str(f1), str(f2)])
        _mod.main()
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["meta"]["total_raw"] == 2
        assert len(data["meta"]["source_files"]) == 2

    def test_findings_sorted_by_severity(self, tmp_path, capsys, monkeypatch):
        f = tmp_path / "scan.sarif"
        self._write_sarif(
            f,
            [
                _run(
                    "t",
                    results=[
                        _result("low", "note"),
                        _result("high", "error"),
                    ],
                )
            ],
        )
        monkeypatch.setattr(sys, "argv", ["prog", str(f)])
        _mod.main()
        out, _ = capsys.readouterr()
        data = json.loads(out)
        assert data["findings"][0]["severity"] == "High"
        assert data["findings"][1]["severity"] == "Low"

    def test_second_file_not_found_exits_1(self, tmp_path, monkeypatch):
        f1 = tmp_path / "ok.sarif"
        self._write_sarif(f1)
        monkeypatch.setattr(sys, "argv", ["prog", str(f1), str(tmp_path / "missing.sarif")])
        with pytest.raises(SystemExit) as exc:
            _mod.main()
        assert exc.value.code == 1


# --- Regression tests for audit fixes (2026-07-09) ---


def test_null_physical_location_does_not_crash():
    """physicalLocation:null (or a non-dict location) must not abort the run."""
    run = _run(
        results=[
            {"ruleId": "r", "message": {"text": "m"}, "locations": [{"physicalLocation": None}]}
        ]
    )
    got = _extract_findings(run, "x.sarif")
    assert len(got) == 1 and got[0]["uri"] == ""
    run2 = _run(results=[{"ruleId": "r", "message": {"text": "m"}, "locations": [None]}])
    assert len(_extract_findings(run2, "x.sarif")) == 1


def test_cvss_score_not_buried_by_coarse_tool_severity():
    # A WARNING tool string must not downgrade an explicit CVSS 9.8.
    assert _normalize_severity("warning", "9.8", "WARNING") == "Critical"
    # ...and an explicit tool Critical must not be dragged down by a low CVSS.
    assert _normalize_severity("note", "2.0", "CRITICAL") == "Critical"


def test_location_less_findings_with_distinct_cves_not_deduped():
    results = [
        {"ruleId": "vuln", "message": {"text": ""}, "taxa": [{"id": "CVE-2021-1111"}]},
        {"ruleId": "vuln", "message": {"text": ""}, "taxa": [{"id": "CVE-2022-2222"}]},
    ]
    got = _extract_findings(_run(results=results), "grype.sarif")
    unique, removed = _deduplicate(got)
    assert removed == 0 and len(unique) == 2


# --- Regression tests for audit fix (2026-07-09): malformed SARIF must not
#     crash the batch; a bad node is skipped, not fatal. ---


@pytest.mark.parametrize(
    "sev",
    [5, [9.0], {"x": 1}, None, "CRITICAL"],
)
def test_normalize_severity_tolerates_nonstring_signals(sev):
    # Free-form SARIF properties may carry non-string severity / non-numeric
    # security-severity; neither may raise.
    assert _normalize_severity("warning", sev, sev) in _mod._SEVERITY_ORDER


@pytest.mark.parametrize(
    "run",
    [
        {"tool": None, "results": []},
        "notadict",
        {"tool": {"driver": {"rules": ["notadict"]}}, "results": []},
        {"tool": {"driver": {"name": "t"}}, "results": ["notadict"]},
        {"tool": {"driver": {"name": "t"}}, "results": [{"ruleId": "x", "taxa": ["notadict"]}]},
    ],
)
def test_extract_findings_skips_malformed_nodes(run):
    # Must return a list without raising, whatever the node types are.
    assert isinstance(_extract_findings(run, "bad.sarif"), list)


def test_parse_sarif_survives_nonconforming_result(tmp_path):
    # A single bad result must not abort the whole file.
    sarif = _sarif(
        [
            {
                "tool": {"driver": {"name": "t", "rules": []}},
                "results": [
                    {"ruleId": "x", "level": "warning", "properties": {"severity": 5}},
                    {"ruleId": "y", "level": "error", "message": {"text": "ok"}},
                ],
            }
        ]
    )
    p = tmp_path / "in.sarif"
    p.write_text(json.dumps(sarif), encoding="utf-8")
    findings = _parse_sarif(p)
    assert len(findings) == 2  # both survive; neither crashes the batch


# --- Regression tests for audit fixes (2026-07-09, batch 2) ---


def test_rule_index_resolves_rule_metadata():
    # A result referencing its rule via ruleIndex (no ruleId) must recover the
    # rule id, name, and CVSS severity from driver.rules[ruleIndex].
    run = _run(
        "semgrep",
        rules=[{"id": "r1", "name": "Rule1", "properties": {"security-severity": "9.5"}}],
        results=[{"ruleIndex": 0, "level": "note", "message": {"text": "m"}, "locations": []}],
    )
    got = _extract_findings(run, "x.sarif")
    assert got[0]["rule_id"] == "r1"
    assert got[0]["rule_name"] == "Rule1"
    assert got[0]["severity"] == "Critical"


def test_out_of_bounds_rule_index_ignored():
    run = _run(
        "t",
        rules=[{"id": "r1"}],
        results=[{"ruleIndex": 9, "level": "note", "message": {"text": "m"}, "locations": []}],
    )
    got = _extract_findings(run, "x.sarif")
    assert got[0]["rule_id"] == ""  # bad index leaves rule_id empty, no crash


def test_null_uri_sorts_without_crash(tmp_path, capsys, monkeypatch):
    # artifactLocation.uri present but null must coerce to "" so the final sort
    # (which compares uri strings) does not raise TypeError.
    r_null = {
        "ruleId": "r1",
        "level": "warning",
        "message": {"text": "m"},
        "locations": [
            {"physicalLocation": {"artifactLocation": {"uri": None}, "region": {"startLine": 1}}}
        ],
    }
    r_ok = _result("r2", "warning", "n", "a.py", 2)
    f = tmp_path / "n.sarif"
    f.write_text(json.dumps(_sarif([_run("t", results=[r_null, r_ok])])), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["prog", str(f)])
    _mod.main()
    data = json.loads(capsys.readouterr().out)
    assert any(x["uri"] == "" for x in data["findings"])


def test_nonstring_taxon_id_does_not_crash():
    result = {
        "ruleId": "r1",
        "level": "warning",
        "message": {"text": "m"},
        "locations": [],
        "taxa": [{"id": 12345}],
    }
    got = _extract_findings(_run("t", results=[result]), "x.sarif")
    assert got[0]["cve_or_rule"] == "r1"


def test_bad_file_skipped_good_findings_emitted(tmp_path, capsys, monkeypatch):
    good = tmp_path / "good.sarif"
    good.write_text(json.dumps(_sarif([_run("t", results=[_result()])])), encoding="utf-8")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["prog", str(good), str(broken)])
    with pytest.raises(SystemExit) as exc:
        _mod.main()
    assert exc.value.code == 1  # at least one file failed → non-zero exit
    data = json.loads(capsys.readouterr().out)
    assert data["meta"]["total_raw"] == 1  # good findings still emitted
    assert len(data["findings"]) == 1


def test_unmapped_tool_severity_fails_safe_to_high():
    # BLOCKER/MAJOR now mapped; a genuinely unknown token fails safe to High rather
    # than silently taking the coarse SARIF level.
    assert _normalize_severity("warning", None, "BLOCKER") == "Critical"
    assert _normalize_severity("warning", None, "MAJOR") == "Medium"
    assert _normalize_severity("warning", None, "totally-unknown") == "High"
    assert _normalize_severity("warning", None, None) == "Medium"  # no tool severity


def test_deeply_nested_sarif_degrades_instead_of_recursionerror(tmp_path):
    p = tmp_path / "deep.sarif"
    p.write_text("[" * 60000 + "]" * 60000, encoding="utf-8")
    with pytest.raises(SystemExit):  # caught RecursionError -> exit, not an uncaught crash
        _parse_sarif(p)


def test_locationless_findings_with_shared_prefix_not_deduped():
    prefix = "x" * 100
    r1 = _result(rule_id="", uri="", message=prefix + "-alpha")
    r2 = _result(rule_id="", uri="", message=prefix + "-beta")
    out = _extract_findings(_run(results=[r1, r2]), "s.sarif")
    unique, removed = _deduplicate(out)
    assert removed == 0
    assert len(unique) == 2
