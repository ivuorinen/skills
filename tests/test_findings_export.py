"""Tests for skills/nitpicker/scripts/findings_export.py.

Each format has one consumer, and each test states the consumer's contract
rather than the renderer's shape: SARIF must not raise an alert on a fixed
finding, JUnit must fail CI on an open one, JSON must carry a summary a script
would otherwise recompute wrongly.
"""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"))
import findings_export as fx


def _row(**over) -> dict:
    base = {
        "id": "security-abc123",
        "status": "open",
        "auditor": "security",
        "severity": "high",
        "area": "src/auth.py:91",
        "title": "Tainted input reaches the query builder",
    }
    return base | over


def test_location_splits_a_path_with_a_line():
    assert fx._location("src/auth.py:91") == ("src/auth.py", 91)


def test_location_leaves_a_bare_area_alone():
    assert fx._location("src/auth.py") == ("src/auth.py", None)
    assert fx._location("the CI pipeline") == ("the CI pipeline", None)


def test_location_does_not_mistake_a_windows_drive_or_trailing_colon():
    assert fx._location("src/a.py:") == ("src/a.py:", None)


# ── SARIF ────────────────────────────────────────────────────────────────────


def test_sarif_maps_critical_and_high_to_error():
    for severity in ("critical", "high"):
        data = json.loads(fx.to_sarif([_row(severity=severity)]))
        assert data["runs"][0]["results"][0]["level"] == "error"


def test_sarif_maps_medium_to_warning_and_low_to_note():
    assert (
        json.loads(fx.to_sarif([_row(severity="medium")]))["runs"][0]["results"][0]["level"]
        == "warning"
    )
    assert (
        json.loads(fx.to_sarif([_row(severity="low")]))["runs"][0]["results"][0]["level"] == "note"
    )


def test_sarif_falls_back_to_warning_for_an_unknown_severity():
    data = json.loads(fx.to_sarif([_row(severity="")]))
    assert data["runs"][0]["results"][0]["level"] == "warning"


def test_sarif_excludes_resolved_findings(tmp_path):
    """A fixed finding raised as an alert is indistinguishable from a live one."""
    rows = [_row(), _row(id="x-1", status="fixed"), _row(id="x-2", status="invalid")]
    data = json.loads(fx.to_sarif(rows))
    assert [r["ruleId"] for r in data["runs"][0]["results"]] == ["security-abc123"]
    assert [r["id"] for r in data["runs"][0]["tool"]["driver"]["rules"]] == ["security-abc123"]


def test_sarif_gives_each_finding_its_own_rule():
    """Collapsing a category into one rule shows N defects as one recurring alert."""
    rows = [_row(), _row(id="security-def456", title="Second defect")]
    data = json.loads(fx.to_sarif(rows))
    assert len({r["id"] for r in data["runs"][0]["tool"]["driver"]["rules"]}) == 2


def test_sarif_carries_the_line_number_when_the_area_has_one():
    location = json.loads(fx.to_sarif([_row()]))["runs"][0]["results"][0]["locations"][0]
    assert location["physicalLocation"]["artifactLocation"]["uri"] == "src/auth.py"
    assert location["physicalLocation"]["region"]["startLine"] == 91


def test_sarif_omits_the_region_when_the_area_names_no_line():
    location = json.loads(fx.to_sarif([_row(area="src/auth.py")]))["runs"][0]["results"][0][
        "locations"
    ][0]
    assert "region" not in location["physicalLocation"]


def test_sarif_places_a_result_from_location_not_from_free_text_area():
    """audit-af9ecae8: the exporter read `area`, which is prose by design.

    `area` may be a file, a directory, a glob, or a subsystem name, so the URI
    it yielded often resolved to nothing in the repository — and a code-scanning
    consumer drops such a result rather than showing it imprecisely, so the
    finding vanished from the interface instead of landing imprecisely in it.
    `location` is always a path plus a range.
    """
    row = _row(area="context_pack diff mode", location="src/context_pack.py:406-450")
    physical = json.loads(fx.to_sarif([row]))["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]
    assert physical["artifactLocation"]["uri"] == "src/context_pack.py"
    assert physical["region"] == {"startLine": 406, "endLine": 450}


def test_sarif_emits_no_end_line_for_a_single_line_location():
    """SARIF reads a region with only `startLine` as that one line.

    An `endLine` equal to it would say nothing extra, and a consumer diffing
    regions across runs would see a change where none happened.
    """
    row = _row(area="a subsystem", location="src/one.py:7")
    region = json.loads(fx.to_sarif([row]))["runs"][0]["results"][0]["locations"][0][
        "physicalLocation"
    ]["region"]
    assert region == {"startLine": 7}


def test_sarif_falls_back_to_area_when_no_location_was_recorded():
    """Provenance is optional on a finding, so the `area` path has to keep working."""
    physical = json.loads(fx.to_sarif([_row(location="")]))["runs"][0]["results"][0]["locations"][
        0
    ]["physicalLocation"]
    assert physical["artifactLocation"]["uri"] == "src/auth.py"
    assert physical["region"] == {"startLine": 91}


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("a/b.py:12", ("a/b.py", 12, None)),  # single line: no redundant endLine
        ("a/b.py:12-40", ("a/b.py", 12, 40)),
        ("a/b.py:0", None),  # SARIF line numbers are 1-based
        ("a/b.py:12-4", ("a/b.py", 12, None)),  # inverted: keep the start, drop the end
        (f"a/b.py:1-{2**31}", ("a/b.py", 1, None)),  # end past the int32 ceiling
        (f"a/b.py:{2**31}", None),  # start past it leaves nothing usable
        ("a whole subsystem", None),
        ("", None),
    ],
)
def test_region_parses_only_a_usable_range(location, expected):
    assert fx._region(location) == expected


def test_sarif_over_an_empty_store_is_still_valid():
    data = json.loads(fx.to_sarif([]))
    assert data["version"] == "2.1.0"
    assert data["runs"][0]["results"] == []


def test_sarif_drops_an_empty_auditor_from_tags():
    rule = json.loads(fx.to_sarif([_row(auditor="")]))["runs"][0]["tool"]["driver"]["rules"][0]
    assert rule["properties"]["tags"] == []
    assert rule["name"] == "nitpicker"


# ── JSON ─────────────────────────────────────────────────────────────────────


def test_json_summary_counts_only_open_findings_by_severity():
    rows = [_row(), _row(id="b", severity="low"), _row(id="c", status="fixed", severity="critical")]
    data = json.loads(fx.to_json(rows))
    assert data["summary"] == {
        "total": 3,
        "open": 2,
        "open_by_severity": {"high": 1, "low": 1},
    }
    assert len(data["findings"]) == 3


def test_json_is_compact():
    assert "\n" not in fx.to_json([_row()])


# ── JUnit ────────────────────────────────────────────────────────────────────


def test_junit_fails_on_open_and_passes_on_resolved():
    rows = [_row(), _row(id="x-1", status="fixed")]
    tree = ET.fromstring(fx.to_junit(rows))
    assert tree.get("tests") == "2"
    assert tree.get("failures") == "1"
    cases = tree.findall(".//testcase")
    assert len(cases[0].findall("failure")) + len(cases[1].findall("failure")) == 1


def test_junit_groups_one_suite_per_auditor():
    rows = [_row(), _row(id="t-1", auditor="tests")]
    names = {s.get("name") for s in ET.fromstring(fx.to_junit(rows)).findall("testsuite")}
    assert names == {"security", "tests"}


def test_junit_labels_a_findings_missing_auditor_rather_than_dropping_it():
    tree = ET.fromstring(fx.to_junit([_row(auditor="")]))
    assert [s.get("name") for s in tree.findall("testsuite")] == ["unknown"]


def test_junit_escapes_xml_metacharacters_in_a_title():
    """Titles quote code, so `<`, `&` and `"` reach this renderer routinely."""
    row = _row(title='fails when x < 1 && flag="on"', area="a<b>.py")
    tree = ET.fromstring(fx.to_junit([row]))
    (case,) = tree.findall(".//testcase")
    assert 'x < 1 && flag="on"' in (case.get("name") or "")
    assert [f.text for f in case.findall("failure")] == ["a<b>.py"]


def test_junit_over_an_empty_store_parses():
    tree = ET.fromstring(fx.to_junit([]))
    assert tree.get("tests") == "0"


def test_junit_strips_control_characters_xml_cannot_represent():
    """No escaping can encode a C0 control character; XML 1.0 forbids them outright.

    A title quoting a file with one stray control byte made the whole exported
    suite unparseable — and a CI reporter that cannot parse the suite drops
    every finding in it, not the one.
    """
    row = _row(title="bell \x07 vtab \x0b nul \x00 end", area="a\x08.py", auditor="sec\x01urity")
    xml = fx.to_junit([row])
    tree = ET.fromstring(xml)  # the assertion: it parses at all
    (case,) = tree.findall(".//testcase")
    assert "bell  vtab  nul  end" in (case.get("name") or "")
    assert [s.get("name") for s in tree.findall("testsuite")] == ["security"]


def test_junit_keeps_the_three_control_characters_xml_allows():
    row = _row(title="line\tone\nline two\r")
    (case,) = ET.fromstring(fx.to_junit([row])).findall(".//testcase")
    assert "\t" in (case.get("name") or "")


def test_sarif_drops_a_line_number_too_large_for_an_int32_consumer():
    """A 40-digit startLine is rejected or silently truncated downstream.

    Truncation puts the finding on an arbitrary line, and neither outcome is
    visible from this side — so the region is omitted where the loss is visible.
    """
    for area in ("a.py:" + "9" * 40, f"a.py:{2**31}"):
        physical = json.loads(fx.to_sarif([_row(area=area)]))["runs"][0]["results"][0]["locations"][
            0
        ]["physicalLocation"]
        assert "region" not in physical
        assert physical["artifactLocation"]["uri"] == "a.py"


def test_sarif_keeps_the_largest_line_an_int32_consumer_can_hold():
    physical = json.loads(fx.to_sarif([_row(area=f"a.py:{2**31 - 1}")]))["runs"][0]["results"][0][
        "locations"
    ][0]["physicalLocation"]
    assert physical["region"]["startLine"] == 2**31 - 1


# ── dispatch ─────────────────────────────────────────────────────────────────


def test_export_dispatches_every_declared_format():
    for fmt in fx.FORMATS:
        assert fx.export([_row()], fmt)


def test_the_store_core_never_pulls_in_its_own_renderer():
    """Direction: the renderer depends on the store's row shape, never the reverse.

    `findings.py` is imported as a library by `mcp_server` and shelled out to by
    the PostToolUse validation hook. A module-scope `import findings_export`
    made every one of those callers load a renderer they never use and fail
    without it; moving it to parser-build time only narrowed that to every CLI
    invocation, since `choices=` is evaluated whichever subcommand runs.

    Asserted in a subprocess because `sys.modules` is process-wide: this test
    file imports the renderer itself, so an in-process check would pass
    vacuously.
    """
    scripts = Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"
    probe = (
        f"import sys; sys.path.insert(0, {str(scripts)!r});"
        "import findings;"
        "findings.main(['validate', '--root', '/nonexistent']);"
        "print('findings_export' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == "False"


def test_cli_export_rejects_an_unknown_format_at_the_usage_exit_code(tmp_path, capsys):
    """Dropping argparse's `choices=` must not weaken the rejection.

    `export`'s own ExportError names the accepted set, which argparse's message
    does too — so the caller sees the same information at the same exit code.
    """
    sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "nitpicker" / "scripts"))
    import findings

    store = tmp_path / "findings"
    store.mkdir()
    assert findings.main(["export", "--root", str(store), "--format", "xml"]) == 2
    assert "must be one of sarif, json, junit" in capsys.readouterr().err


def test_export_rejects_an_unknown_format_naming_the_set():
    with pytest.raises(fx.ExportError, match="sarif, json, junit"):
        fx.export([], "csv")
