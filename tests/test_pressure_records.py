"""Every nitpicker command is pressure-tested, grandfathered, or fails this gate.

`.claude/rules/skill-lifecycle.md` says never skip a phase, and `/new-command`
makes RED and GREEN mandatory phases with exit artifacts — but nothing detected a
skipped one, so a command could ship having never been pressure-tested at all
(agent-loopholes, this session). This is the detector: a new command file must
arrive with a record in `pressure-records.json`, or be added to `grandfathered`,
which is a visible, reviewable line in a diff rather than a silent omission.

The registry is not a substitute for running the test. It records that one ran.
"""

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).parent.parent
_COMMANDS = _REPO / "skills" / "nitpicker" / "commands"
_REGISTRY = _REPO / "skills" / "nitpicker" / "evals" / "pressure-records.json"

_REQUIRED_FIELDS = (
    "command",
    "scenario",
    "pressure",
    "pressure_kind",
    "rationalizations",
    "red",
    "green",
    "date",
)


@pytest.fixture(scope="module")
def registry() -> dict:
    return json.loads(_REGISTRY.read_text(encoding="utf-8"))


def _command_stems() -> set[str]:
    """Dispatchable commands: `_`-prefixed files are shared references, not commands."""
    return {p.stem for p in _COMMANDS.glob("*.md") if not p.name.startswith("_")}


def test_every_command_is_recorded_or_grandfathered(registry):
    covered = set(registry["grandfathered"]) | {r["command"] for r in registry["records"]}
    missing = sorted(_command_stems() - covered)
    assert not missing, (
        f"no pressure record for {', '.join(missing)} — run /skill-tester against the "
        "command and add a record, or add the name to 'grandfathered' so the omission "
        "is visible in review"
    )


def test_the_registry_names_no_command_that_does_not_exist(registry):
    """A renamed or deleted command must not leave a record behind claiming coverage."""
    named = set(registry["grandfathered"]) | {r["command"] for r in registry["records"]}
    stale = sorted(named - _command_stems())
    assert not stale, f"pressure-records.json names commands that do not exist: {stale}"


def test_a_command_is_not_both_recorded_and_grandfathered(registry):
    both = sorted(set(registry["grandfathered"]) & {r["command"] for r in registry["records"]})
    assert not both, f"tested and grandfathered are exclusive; both claim: {both}"


def test_every_record_carries_every_field(registry):
    for record in registry["records"]:
        missing = [f for f in _REQUIRED_FIELDS if f not in record]
        assert not missing, f"record {record.get('command')!r} missing {missing}"
        assert record["pressure_kind"] in ("motivational", "epistemic")
        assert isinstance(record["rationalizations"], list)
        assert record["pressure"].strip(), "the pressure must be recorded verbatim, not summarised"


def test_the_gate_can_fail():
    """Control: the coverage check must reject an unrecorded command, not just pass."""
    covered = {"alpha"}
    stems = {"alpha", "beta"}
    assert sorted(stems - covered) == ["beta"]
