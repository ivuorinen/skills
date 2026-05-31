"""Tests for skills/security-auditor/process-sarif.py."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_TOOL = Path(__file__).parent.parent / "skills" / "security-auditor" / "process-sarif.py"
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

    def test_wrong_version_warns(self, tmp_path):
        data = {"version": "1.0.0", "runs": []}
        f = tmp_path / "old.sarif"
        f.write_text(json.dumps(data), encoding="utf-8")
        _parse_sarif(f)

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
